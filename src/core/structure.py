# -*- coding: utf-8 -*-
"""
文件名：core/structure.py
职责：
    1. 单体几何的直接构建：通过中心点+尺寸的方式快速建模。
    2. 单元蓝图的录制：记录操作序列以供阵列复用。
逻辑：
    通过 `_is_recording` 标志位切换模式。
    - 默认模式 (False): 直接调用 Builder 生成几何 (单体模式)。
    - 录制模式 (True): 仅将操作参数存入列表，不生成几何 (蓝图模式)。
"""

from typing import List, Dict, Any, Tuple, Optional, Union, Protocol, runtime_checkable
import copy
from ..utils.logger import logger


# ==============================================================================
# 类型定义：Builder 协议
# ==============================================================================
@runtime_checkable
class IBuilder(Protocol):
    """
    几何构建器接口协议。
    
    定义了底层仿真软件（如 CST、HFSS）必须实现的几何操作方法集。
    这是一个“鸭子类型”接口，强制要求任何接入框架的软件构建器必须提供这些方法。

    Structure 类依赖于此接口。Structure 将用户的建模意图翻译为通用指令，
    并通过此接口将指令传递给具体的软件实现（例如 `CSTBuilder`）。
    这种设计实现了“高层业务逻辑”与“底层具体实现”的完全解耦。

    【包含方法】
    - 基础图元：长方体 (brick)、圆柱体 (cylinder)、多边形拉伸 (polygon3D)。
    - 拾取与操作：拾取面 (pick_face)、拉伸面 (extrude_pick_face)。
    - 布尔运算：加法 (add)、减法 (subtract)。
    - 状态管理：`execute` (提交缓存指令)、`clear` (清空缓存)。
    """

    def create_brick(self, name: str, material: str,
                     Xrange: Union[list, tuple],
                     Yrange: Union[list, tuple],
                     Zrange: Union[list, tuple]) -> None: ...

    def create_cylinder(self, name: str, material: str, 
                        r_out: Union[float, str], r_in: Union[float, str],
                        pos_1: Union[float, str], pos_2: Union[float, str],
                        range_val: Union[list, tuple],
                        color: Optional[tuple] = None, axis: str = "z") -> None: ...

    def create_polygon3D(self, name: str, material: str, vertices_3d: List[Tuple[Union[float, str], Union[float, str], Union[float, str]]], 
                       thickness: Union[float, str]) -> None: ...

    def pick_face(self, source_name: str, face_id: int) -> None: ...
    def extrude_pick_face(self, name: str, height: Union[float, str], material: str) -> None: ...
    
    def add(self, blank_name: str, tool_name: str) -> None: ...
    def subtract(self, blank_name: str, tool_name: str, delete_tool: bool) -> None: ...
    def add_op(self, code: str, description: str) -> None: ...
    def set_color(self, name: str, color: tuple) -> None: ...
    def execute(self) -> None: ...
    def clear(self) -> None: ...


class Structure:
    """
    几何结构定义类。

    负责几何操作的调度，核心功能包含两部分：
    1. 单体几何构建 (Direct Modeling)：直接调用底层 API 生成具体的几何实体操作代码。
    2. 单元蓝图录制 (Blueprint Recording)：记录几何操作序列，但不立即生成几何，用于后续的阵列复用。

    该类通过 `_is_recording` 标志位实现了一个简单的状态机，根据当前状态决定操作的去向：
    - 默认状态 (非录制模式)：
        所有 `create_xxx` 请求通过 `_route` 路由至对应的 `_execute_xxx` 方法，最终调用 `IBuilder` 生成几何。
    - 录制状态 (蓝图模式)：
        当调用 `start_unit_definition` 开启录制后，所有操作参数仅被序列化存储在 `_operations` 列表中，不生成几何。
        调用 `end_unit_definition` 后，将这些操作序列作为一个“单元蓝图”存入 `_unit_blueprints`。

    1. 与 IBuilder 的关系：
       Structure 持有一个 IBuilder 实例（如 CSTBuilder 或 HFSSBuilder）。
       它不直接调用软件 API，而是将具体的几何结构指令委托给 Builder 执行。
       这种解耦使得 Structure 的业务逻辑（如“画一个长方体”）可以独立于底层仿真软件（CST 或 HFSS）。
    2. 与 SimWorkflow 的关系：
       Structure 通常是 SimWorkflow 的一部分（`self.structure`）。
       用户通过 Workflow 访问 Structure 来定义几何，而 Structure 内部的 Builder 则由 Workflow 管理。

    - _is_recording (bool): 核心开关。控制当前是“执行操作”还是“录制操作”。
    - _operations (List[Dict]): 临时存储区。在录制模式下，暂存所有操作的参数字典。
    - _unit_blueprints (Dict[str, List[Dict]]): 蓝图库。存储已定义的单元名称及其对应的操作序列。
    - _builder (IBuilder): 底层构建引擎。负责最终的 API 调用。

    - 生命周期管理：`start_unit_definition`, `end_unit_definition` (控制录制状态)。
    - 几何原语：`create_brick`, `create_cylinder` 等 (对外接口)。
    - 路由逻辑：`_route` (核心分发器，决定是存参数还是执行)。
    - 执行器：`_execute_xxx` (私有方法，调用 Builder 的具体实现)。
    """

    def __init__(self, builder: Optional[IBuilder], component: str = "Antenna"):
        """
        初始化结构管理器。
        
        Args:
            builder: 底层几何构建器实例 (需符合 IBuilder 协议)。
            component: 组件名称，用于区分不同的几何结构。
        """
        self.component = component
        self._builder = builder
        
        # --- 状态管理 ---
        self._is_recording = False  # 模式切换开关
        self._operations: List[Dict[str, Any]] = [] # 临时存储录制的操作
        self._unit_blueprints: Dict[str, List[Dict[str, Any]]] = {} # 存储已定义的单元蓝图
        self._unit_name: str = "" # 当前录制的单元名称

        logger.info(f"[Structure] 初始化完成。组件: {component}")

    # ==================================================================================
    # 生命周期管理：定义单元 (开启蓝图录制模式)
    # ==================================================================================

    def start_unit_definition(self, unit_name: str) -> None:
        """
        开始定义复合单元（进入蓝图录制模式）。
        在此模式下，所有几何操作仅记录参数，不执行底层建模。
        
        Args:
            unit_name: 单元的唯一标识名。
        """
        self._is_recording = True
        self._operations = []
        self._unit_name = unit_name
        logger.info(f"  -> 开始录制单元蓝图: {unit_name}")

    def end_unit_definition(self) -> None:
        """
        结束定义当前单元，保存蓝图（退出蓝图录制模式）。
        """
        if not self._is_recording:
            logger.warning("  -> 警告：当前未处于录制模式。")
            return
            
        # 深拷贝保存蓝图，防止后续操作污染
        self._unit_blueprints[self._unit_name] = copy.deepcopy(self._operations)
        self._is_recording = False
        logger.info(f"  -> 单元蓝图 '{self._unit_name}' 定义完成，包含 {len(self._operations)} 个操作。")

    def get_blueprint(self, unit_name: str) -> List[Dict[str, Any]]:
        """
        获取指定单元的蓝图序列，供 ArrayStructure 使用。
        
        Args:
            unit_name: 单元的唯一标识名。
            
        Returns:
            List[Dict]: 操作蓝图序列。
        """
        return self._unit_blueprints.get(unit_name, [])

    # ==================================================================================
    # 核心几何原语 (智能路由)
    # ==================================================================================
    
    def _route(self, operation_type: str, **kwargs) -> None:
        """
        通用路由逻辑。
        - 录制模式：存入 _operations 列表。
        - 执行模式：调用 _execute_xxx 方法。
        
        Args:
            operation_type: 操作类型 (例如 'brick', 'cylinder')。
            kwargs: 操作的具体参数。
        """
        if self._is_recording:
            self._operations.append({
                "type": operation_type,
                **kwargs
            })
        else:
            if not self._builder:
                logger.error(f"[Structure] 错误: 未处于录制模式且没有 Builder，无法执行 {operation_type}")
                return
            
            executor = getattr(self, f"_execute_{operation_type}", None)
            if executor:
                executor(**kwargs)
            else:
                logger.error(f"[Structure] 错误: 找不到执行方法 _execute_{operation_type}")

    def create_brick(self, name: str, material: str,
                     Xrange: Union[list, tuple],
                     Yrange: Union[list, tuple],
                     Zrange: Union[list, tuple],
                     color: Optional[tuple] = None) -> None:
        """
        长方体构建。
        """
        self._route("brick", name=name, material=material, 
                    Xrange=Xrange, Yrange=Yrange, Zrange=Zrange, 
                    color=color)

    def create_cylinder(self, name: str, material: str, 
                        r_out: Union[float, str], r_in: Union[float, str],
                        pos_1: Union[float, str], pos_2: Union[float, str],
                        range_val: Union[list, tuple],
                        color: Optional[tuple] = None, axis: str = "z") -> None:
        """
        圆柱体构建（智能路由 - 支持任意轴向）。

        CST VBA 属性映射规则 (坐标对应关系):

        ---------------------------------------------------------
        | Axis 设置 | 范围 | 圆心 1 | 圆心 2 |
        ---------------------------------------------------------
        |   "x"     |     .Xrange       |      .Ycenter      |      .Zcenter      |
        |   "y"     |     .Yrange       |      .Xcenter      |      .Zcenter      |
        |   "z"     |     .Zrange       |      .Xcenter      |      .Ycenter      |
        ---------------------------------------------------------

        参数说明:
            pos_1: 截面圆心的第一个坐标值 (对应上表中的 Center 1)。
            pos_2: 截面圆心的第二个坐标值 (对应上表中的 Center 2)。
            range_val: 圆柱沿轴向的长度范围 [min, max]。
            axis: 圆柱生长轴向 ("x", "y", "z")，默认为 "z"。
        """
        self._route("cylinder", name=name, material=material, r_out=r_out, r_in=r_in, 
                    pos_1=pos_1, pos_2=pos_2, range_val=range_val, color=color, axis=axis)
        
    def create_polygon3D(self, name: str, material: str, 
                         vertices_3d: List[Tuple[Union[float, str], Union[float, str], Union[float, str]]], 
                         thickness: Union[float, str], 
                         color: Optional[tuple] = None) -> None:
        """
        多边形拉伸体构建（智能路由）。
        """
        self._route("polygon3D", name, material, vertices_3d, thickness, color=color)

    # ==================================================================================
    # 执行方法
    # ==================================================================================

    def _execute_brick(self, name, material, Xrange, Yrange, Zrange, color):
        """
        执行长方体构建。
        """
        self._builder.create_brick(
            name=name, 
            material=material, 
            Xrange=Xrange, 
            Yrange=Yrange, 
            Zrange=Zrange
        )
        
        if color:
            self._builder.set_color(name, color)

    def _execute_cylinder(self, name, material, r_out, r_in, pos_1, pos_2, range_val, color, axis="z"):
        """
        执行圆柱体构建 (支持任意轴向)。

        CST VBA 属性映射规则 (坐标对应关系):

        ---------------------------------------------------------
        | Axis 设置 | 范围 | 圆心 1 | 圆心 2 |
        ---------------------------------------------------------
        |   "x"     |     .Xrange       |      .Ycenter      |      .Zcenter      |
        |   "y"     |     .Yrange       |      .Xcenter      |      .Zcenter      |
        |   "z"     |     .Zrange       |      .Xcenter      |      .Ycenter      |
        ---------------------------------------------------------

        参数说明:
            pos_1: 截面圆心的第一个坐标值 (对应上表中的 Center 1)。
            pos_2: 截面圆心的第二个坐标值 (对应上表中的 Center 2)。
            range_val: 圆柱沿轴向的长度范围 [min, max]。
            axis: 圆柱生长轴向 ("x", "y", "z")。
        """
        self._builder.create_cylinder(
            name=name, 
            material=material, 
            r_out=r_out, 
            r_in=r_in, 
            pos_1=pos_1, 
            pos_2=pos_2, 
            range_val=range_val, 
            axis=axis
        )
        
        if color:
            self._builder.set_color(name, color)

    def _execute_polygon3D(self, name, material, vertices, Zrange, color):
        """
        执行多边形拉伸体构建。
        """
        self._builder.create_polygon3D(
            name=name, 
            material=material, 
            vertices=vertices, 
            Zrange=Zrange
        )
        
        if color:
            self._builder.set_color(name, color)
    
    def _convert_face_to_id(self, face_input: Union[int, str]) -> int:
        """
        将面方向字符串转换为对应的数字 ID (1-6)。
        
        注意：此处的映射逻辑 (1-6) 是 CST 特有的标准。
        如果未来接入 HFSS 或其他仿真软件，需重写此方法以适配其面 ID 定义。
        """
        if isinstance(face_input, int):
            if 1 <= face_input <= 6:
                return face_input
            raise ValueError(f"无效的面 ID: {face_input}. 必须是 1-6 之间的整数。")
        
        if isinstance(face_input, str):
            # CST 面 ID 映射：+z=顶部, -z=底部
            standard_map = {
                '+z': 1, 'top': 1, 
                '-z': 2, 'bottom': 2, 
                '-y': 3, 'left': 3, 
                '-x': 4, 'back': 4, 
                '+y': 5, 'right': 5, 
                '+x': 6, 'front': 6
            }
            
            key = face_input.lower()
            if key in standard_map:
                return standard_map[key]
            else:
                raise ValueError(f"无效的面方向: {face_input}. 请使用 '+z', 'left', 'front' 等或数字 ID。")
        
        raise TypeError(f"face_id 类型错误: {type(face_input)}")
    
    def pick_face(self, source_name: str, face_id: Union[int, str]) -> None:
        """
        拾取面操作（智能路由）。
        
        Args:
            source_name: 源实体名称。
            face_id (int | str): 目标面标识。
                - 支持整数 ID（直接映射底层求解器）。
                - 支持方向字符串（自动路由）。映射规则如下：
                    - Z轴: '+z' / 'top' -> 1,  '-z' / 'bottom' -> 2
                    - Y轴: '-y' / 'left' -> 3,  '+y' / 'right' -> 5
                    - X轴: '-x' / 'back' -> 4,  '+x' / 'front' -> 6
        """
        numeric_face_id = self._convert_face_to_id(face_id)
        self._route("pick_face", source_name=source_name, face_id=numeric_face_id)

    def extrude_face(self, name: str, source_name: str, face_id: Union[int, str],
                     height: float, material: str, color: Optional[tuple] = None) -> None:
        """
        面拉伸操作（智能路由）。
        
        Args:
            name: 新实体名称。
            source_name: 源实体名称。
            face_id (int | str): 目标面标识。
                - 支持整数 ID（直接映射底层求解器）。
                - 支持方向字符串（自动路由）。映射规则如下：
                    - Z轴: '+z' / 'top' -> 1,  '-z' / 'bottom' -> 2
                    - Y轴: '-y' / 'left' -> 3,  '+y' / 'right' -> 5
                    - X轴: '-x' / 'back' -> 4,  '+x' / 'front' -> 6
            height: 拉伸高度。
            material: 材料名称。
            color: 颜色。
        """
        numeric_face_id = self._convert_face_to_id(face_id)
        self._route("extrude_face", name=name, source_name=source_name, 
                    face_id=numeric_face_id, height=height, material=material, color=color)

    def add(self, blank_name: str, tool_name: str) -> None:
        """布尔加法（智能路由）。"""
        self._route("add", blank_name=blank_name, tool_name=tool_name)

    def add_multiple(self, main_name: str, *tool_names: str) -> None:
        """
        批量布尔加法：将多个物体依次合并到主物体中。
        
        Args:
            main_name (str): 主物体名称（最终保留的名字）。
            *tool_names (str): 一个或多个需要被合并的工具物体名称。
        """
        for tool_name in tool_names:
            self.add(main_name, tool_name)

    def subtract(self, blank_name: str, tool_name: str) -> None:
        """布尔减法（智能路由）。"""
        self._route("subtract", blank_name=blank_name, tool_name=tool_name)

    def _execute_pick_face(self, source_name, face_id):
        self._builder.pick_face(source_name, face_id)

    def _execute_extrude_face(self, name, source_name, face_id, height, material, color):
        if not self._builder: return

        # Builder 内部会自动添加操作记录
        self._builder.pick_face(source_name, face_id)
        self._builder.extrude_pick_face(name, height, material)
        
        if color:
            self._builder.set_color(name, color)

    def _execute_add(self, blank_name, tool_name):
        if not self._builder: return
        self._builder.add(blank_name, tool_name)

    def _execute_subtract(self, blank_name, tool_name):
        if not self._builder: return
        self._builder.subtract(blank_name, tool_name)

    # --- 执行与清理 ---
    def execute(self) -> None:
        """
        执行构建。
        调用 Builder 的 execute 方法将所有缓存的指令发送至软件。
        """
        if self._builder:
            logger.info(f">>> [{self.__class__.__name__}] 开始构建几何模型 ")
            self._builder.execute()
            logger.info(f">>> [{self.__class__.__name__}] 几何模型构建完成")
            self.clear()
        else:
            logger.warning(f"[{self.__class__.__name__}] 警告: 没有仿真软件构建器，仅录制了指令，未执行。")      

    def clear(self) -> None:
        """
        清空 Builder 缓存。
        """
        if self._builder:
            self._builder.clear()
        logger.info(f"[{self.__class__.__name__}] 设计的几何结构缓存已清空")