# -*- coding: utf-8 -*-
from typing import List, Tuple, Union, Dict, Any
from src.cst.vba import CSTVBA
from src.utils.logger import logger 
from src.core.structure import IBuilder

class CSTStructureBuilder(IBuilder):
    """
    CST 几何结构构建器 (底层 VBA 缓冲模式)

    该类严格遵循“单一职责原则”，仅作为 VBA 代码的传输管道和缓冲池。
    所有的几何结构生成（包括复杂阵列的绝对坐标计算、颜色策略）均由上层 Structure 类完成。
    本类仅负责将拼接好的最终 VBA 字符串批量发送给 CST。
    """

    def __init__(self, vba: CSTVBA, component: str = "Antenna"):
        """
        初始化构建器实例。

        Args:
            vba_client: CST VBA 接口连接实例，用于执行代码。
            component (str): 目标 CST 组件名称。默认为 "Antenna"。
        """
        self.vba = vba
        self.component = component
        # --- 核心缓存区 ---
        # 存储所有待执行的 VBA 代码片段
        self._vba_cache: List[str] = []
        # 用于存储所有将要创建的物体名称
        self._objects_to_cleanup: List[str] = []
        
        # 初始化组件环境
        self._init_component()
        logger.info(f"构建器初始化完成。组件: {self.component}")

    def _init_component(self) -> None:
        """
        内部方法：生成创建或重置组件的 VBA 代码。
        """
        vba_code = f'''
            Component.New "{self.component}"
            '''
        self.add_op(vba_code, "Initialize Component")
    
    def _to_vba_str(self, val) -> str:
        """
        将输入值转换为 VBA 脚本中可直接使用的字符串。
        
        Args:
            val: 可以是数值 (int/float) 或变量名 (str)。
        
        Returns:
            str: 如果是数值，返回格式化后的字符串 (如 "10.000000")；
                 如果是字符串，返回变量名 (如 "my_length")。
        """
        if isinstance(val, str):
            return val
        return f"{float(val):.6f}"

    def add_op(self, code: str, description: str = "") -> None:
        """
        将 VBA 代码片段加入缓存池。

        这是该类最核心的方法。Geometry 类在完成所有坐标计算和逻辑拼接后，
        将生成的最终 VBA 字符串通过此方法注入。

        Args:
            code (str): 格式的 VBA 代码块。
            description (str): 代码块的描述信息，用于调试日志。
        """
        self._vba_cache.append(code + "\n")
        if description:
            logger.info(f"缓存中添加 VBA 代码: {description}")
    
    # ==================================================================================
    # 参数设置方法
    # ==================================================================================
    
    def set_parameters(self, params_data: Dict[str, Any], cst_app: Any) -> bool:
        """
        执行方法：将内存中的参数写入 CST 软件
        注意：通常在建模开始前调用，用于在 CST 界面显示参数
        
        Args:
            params_data (Dict[str, Any]): 参数字典，键为参数名，值为参数值。
            cst_app: CSTApp 实例或 Project 实例
            
        Returns:
            bool: 执行成功返回 True
        """
        if not params_data:
            return True
            
        print(f">>> 正在将 {len(params_data)} 个参数设置到 CST...")
        
        try:
            # 兼容处理：如果传入的是 App，取 project；如果是 project，直接用
            project = cst_app.project if hasattr(cst_app, 'project') else cst_app
            
            for name, value in params_data.items():
                value_str = str(value)
                description = f"Parameter {name}"
                
                try:
                    # 调用 CST API
                    project.model3d.StoreParameterWithDescription(
                        name, value_str, description
                    )
                except Exception as e:
                    print(f"  写入 CST 失败 '{name}': {e}")
                    return False
            
            print(f">>> CST 参数设置完成。")
            return True
            
        except Exception as e:
            print(f"同步参数到 CST 时发生致命错误: {e}")
            return False

    # ==================================================================================
    # 基础几何原语生成器 (Generators)
    # ==================================================================================

    def create_brick(self, name: str, material: str,
                     Xrange: Union[list, tuple],
                     Yrange: Union[list, tuple],
                     Zrange: Union[list, tuple]) -> None:
        """
        生成长方体的 VBA 代码字符串 (CST VBA 风格)。

        Args:
            name (str): 实体名称。
            material (str): 材质名称。
            Xrange (Union[list, tuple]): X轴范围 [min, max]。
            Yrange (Union[list, tuple]): Y轴范围 [min, max]。
            Zrange (Union[list, tuple]): Z轴范围 [min, max]。
        """
        code = f'''
With Brick
    .Reset
    .Name "{name}"
    .Component "{self.component}"
    .Material "{material}"
    .Xrange "{self._to_vba_str(Xrange[0])}", "{self._to_vba_str(Xrange[1])}"
    .Yrange "{self._to_vba_str(Yrange[0])}", "{self._to_vba_str(Yrange[1])}"
    .Zrange "{self._to_vba_str(Zrange[0])}", "{self._to_vba_str(Zrange[1])}"
    .Create
End With
'''
        # 将该物体名加入全局清理列表
        self._objects_to_cleanup.append(name)
        self.add_op(code, f"Create Brick: {name}")

    def create_cylinder(self, name: str, material: str, r_out: Union[float, str], r_in: Union[float, str],
                       pos_1: Union[float, str], pos_2: Union[float, str], 
                       range_val: Union[list, tuple], axis: str = "z") -> None:
        """
        生成圆柱体的 VBA 代码字符串 (支持 X, Y, Z 任意轴向)。
        
        CST VBA 属性映射规则:

        --------------------------------------------------------------------------------
        | Axis 设置 | 范围 | 圆心 1 | 圆心 2 |
        --------------------------------------------------------------------------------
        |   "x"     |     .Xrange       |      .Ycenter         |      .Zcenter         |
        |   "y"     |     .Yrange       |      .Xcenter         |      .Zcenter         |
        |   "z"     |     .Zrange       |      .Xcenter         |      .Ycenter         |
        --------------------------------------------------------------------------------

        参数说明:
            pos_1, pos_2: 截面圆心的两个坐标值 (根据上表对应 X/Y/Z)。
            range_val: 圆柱沿轴向的长度范围 [min, max]。
            axis: 圆柱生长轴向，必须是 "x", "y", 或 "z"。
        """
        # 1. 根据轴向确定 VBA 属性名
        axis = axis.lower()
        if axis == "x":
            attr_range = ".Xrange"
            attr_c1 = ".Ycenter"
            attr_c2 = ".Zcenter"
        elif axis == "y":
            attr_range = ".Yrange"
            attr_c1 = ".Xcenter"
            attr_c2 = ".Zcenter"
        elif axis == "z":
            attr_range = ".Zrange"
            attr_c1 = ".Xcenter"
            attr_c2 = ".Ycenter"
        else:
            raise ValueError(f"Invalid axis '{axis}'. Must be 'x', 'y', or 'z'.")

        # 2. 生成 VBA 代码
        code = f'''
With Cylinder
    .Reset
    .Name "{name}"
    .Component "{self.component}"
    .Material "{material}"
    .OuterRadius "{self._to_vba_str(r_out)}"
    .Innerradius "{self._to_vba_str(r_in)}"
    .Axis "{axis}"
    {attr_range} "{self._to_vba_str(range_val[0])}", "{self._to_vba_str(range_val[1])}"
    {attr_c1} "{self._to_vba_str(pos_1)}"
    {attr_c2} "{self._to_vba_str(pos_2)}"
    .Segments "0"
    .Create
End With
'''
        self._objects_to_cleanup.append(name)
        self.add_op(code, f"Create Cylinder: {name}")

    def create_polygon_profile(self, name: str, vertices_3d: List[Tuple[Union[float, str], Union[float, str], Union[float, str]]]) -> None:
        """
        生成多边形轮廓（Polygon3D）的 VBA 代码字符串。
        
        这一步仅创建 2D/3D 曲线轮廓，不进行实体化。
        
        Args:
            name (str): 轮廓名称。
            vertices_3d (List[Tuple]): 三维顶点坐标列表 [(x, y, z), ...]。
                直接传入物理坐标系下的三维点。
        """
        if not vertices_3d:
            return
            
        curve_name = f"curve_{name}"
        poly_name = f"profile_{name}"
        
        vba_parts = [
            f'With Polygon3D',
            f' .Reset',
            f' .Name "{poly_name}"',
            f' .Curve "{curve_name}"'
        ]
        
        # 添加顶点：直接解包三维坐标
        for x, y, z in vertices_3d:
            vba_parts.append(f' .Point "{self._to_vba_str(x)}", "{self._to_vba_str(y)}", "{self._to_vba_str(z)}"')
            
        # 闭合多边形：连接回第一个点
        if vertices_3d:
            first_x, first_y, first_z = vertices_3d[0]
            vba_parts.append(f' .Point "{self._to_vba_str(first_x)}", "{self._to_vba_str(first_y)}", "{self._to_vba_str(first_z)}"')
            
        vba_parts.extend([' .Create', 'End With'])
        
        code = "\n".join(vba_parts)
        self.add_op(code, f"create_polygon_profile: {name}")

    def extrude_curve(self, name: str, material: str, profile_name: str, curve_name: str, thickness: Union[float, str]) -> None:
        """
        生成拉伸曲线（ExtrudeCurve）的 VBA 代码字符串。
        
        将已存在的轮廓拉伸为 3D 实体。
        """
        code = f'''
With ExtrudeCurve
    .Reset
    .Name "{name}"
    .Component "{self.component}"
    .Material "{material}"
    .Thickness "{self._to_vba_str(thickness)}"
    .DeleteProfile "True"
    .Curve "{curve_name}:{profile_name}"
    .Create
End With
'''     
        self._objects_to_cleanup.append(name)
        self.add_op(code, f"extrude_curve: {name}")

    def create_polygon3D(self, name: str, material: str, vertices_3d: List[Tuple[Union[float, str], Union[float, str], Union[float, str]]], 
                       thickness: Union[float, str]) -> None:
        """
        生成多边形拉伸体的 VBA 代码字符串。

        该方法通过组合“创建多边形轮廓 (Polygon3D)”和“拉伸 (ExtrudeCurve)”两个步骤，
        生成用于在 CST 中创建 3D 实体的完整 VBA 脚本。

        Args:
            name (str): 实体名称。
            material (str): 材质名称。
            vertices_3d (List[Tuple]): 三维顶点坐标列表 [(x, y, z), ...]。
                定义多边形截面的三维坐标点。
            thickness (Union[float, str]): 拉伸厚度。
                CST 会自动沿轮廓的法向方向进行拉伸。
        """
        curve_name = f"curve_{name}"
        poly_name = f"profile_{name}"
        
        # 1. 生成轮廓代码 (直接传入三维点)
        self.create_polygon_profile(name, vertices_3d)
        
        # 2. 生成拉伸代码
        self.extrude_curve(name, material, poly_name, curve_name, thickness)
        
        self.add_op("", f"create_polygon3D: {name}")

    def set_color(self, name: str, color: Tuple[int, int, int]) -> str:
        """
        生成设置实体颜色的 VBA 代码。

        Args:
            name (str): 实体名称。
            color (Tuple[int, int, int]): RGB 颜色元组 (0-255)。
        """
        r, g, b = color
        code = f'''
Solid.SetUseIndividualColor "{self.component}:{name}", 1
Solid.ChangeIndividualColor "{self.component}:{name}", {r}, {g}, {b}
'''
        self.add_op(code, f"set_color: {name}")
    
    def pick_face(self, name: str, face_id: int) -> str:
        """
        生成通过 ID 拾取面的 VBA 代码字符串。

        该方法用于在 CST 中通过 VBA 脚本选中指定的面。

        Args:
            name (str) : 实体名。
            face_id (int): 面的 ID。
        """
        code = f'''
Pick.PickFaceFromId "{self.component}:{name}", "{face_id}"
'''
        self.add_op(code, f"pick_face: {name}")  
    
    def extrude_pick_face(self, name: str, height: Union[float, str], material: str) -> str:
        """
        生成基于拾取面（Pick）的拉伸体 VBA 代码字符串。

        该方法使用 CST 的 Extrude 命令，针对当前拾取的面进行拉伸操作。

        Args:
            name (str): 实体名称。
            material (str): 材质名称（例如 "PEC"）。
            height (Union[float, str]): 拉伸高度。
                可以是具体的数值（float），也可以是变量名（str，例如 "metal_thickness"）。
        """
        code = f'''
With Extrude
    .Reset
    .Name "{name}"
    .Component "{self.component}"
    .Material "{material}"
    .Mode "Picks"
    .Height "{self._to_vba_str(height)}"
    .Twist "0.0"
    .Taper "0.0"
    .UsePicksForHeight "False"
    .DeleteBaseFaceSolid "False"
    .ClearPickedFace "True"
    .Create
End With
''' 
        self._objects_to_cleanup.append(name)
        self.add_op(code, f"extrude_pick_face: {name}")

    # ==================================================================================
    # 布尔运算与其他操作
    # 这些操作同样只生成字符串，依赖调用者传入正确的实体全名。
    # ==================================================================================

    def subtract(self, blank_name: str, tool_name: str) -> str:
        """
        生成布尔减法的 VBA 代码字符串。

        Args:
            blank_name (str): 被减物体的名)。
            tool_name (str): 工具物体的名称。
            delete_tool (bool): 是否删除工具物体。默认为 True。
        """
        code = f'''
            Solid.Subtract "{self.component}:{blank_name}", "{self.component}{tool_name}"
            '''
        self.add_op(code, f"subtract {tool_name} from {blank_name}")

    def add(self, blank_name: str, tool_name: str) -> str:
        """
        生成布尔加法的 VBA 代码字符串。

        Args:
            blank_name (str): 主物体全名。
            tool_name (str): 添加物体全名。
        """
        code = f'''
            Solid.Add "{self.component}:{blank_name}", "{self.component}:{tool_name}"
            '''
        self.add_op(code, f"subtract {tool_name} to {blank_name}")

    # ==================================================================================
    # 执行接口
    # ==================================================================================

    def execute(self) -> None:
        """
        统一执行：将缓存池中所有的 VBA 代码一次性发送给 CST 执行。

        优势：
        1. 极大减少 Python 与 CST 之间的进程间通信 (IPC) 次数。
        2. 对于包含数千个单元的阵列，构建速度提升显著（相比逐条发送）。
        3. 保证操作的原子性，减少界面卡顿。
        """
        if not self._vba_cache:
            logger.warning("VBA 缓存为空，无需执行。")
            return
        
        # 构建全局清理脚本
        # On Error Resume Next 发生错误时，忽略该错误，并继续执行下一行代码。
        # On Error GoTo 0 禁用错误处理程序。
        cleanup_script = "On Error Resume Next\n"
        # 遍历所有记录的物体名，生成删除语句
        for obj_name in self._objects_to_cleanup:
            cleanup_script += f'Solid.Delete "{self.component}:{obj_name}"\n'
        cleanup_script += "On Error GoTo 0\n\n"

        # 拼接所有代码：清理脚本 + 建模脚本
        full_script = cleanup_script + "\n".join(self._vba_cache)
        
        # 一次性发送给 CST
        self.vba.to_cst_history(full_script, "Batch Execute Geometry")
        
        logger.info(f"批量构建完成。共发送 {len(self._vba_cache)} 条指令。")

    def clear(self) -> None:
        """
        清空缓存池，以便进行下一次独立的构建任务。
        """
        self._vba_cache.clear()
        self._objects_to_cleanup.clear()
        logger.debug("VBA 缓存已清空。")