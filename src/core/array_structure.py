# -*- coding: utf-8 -*-
"""
模块：array_structure.py
描述：阵列结构生成器 (严格适配 Structure 录制协议)

核心逻辑：
    1. 获取单元蓝图 (Structure.get_blueprint)。
    2. 利用 ArrayLayout 计算每个单元的绝对位置 (Offset)。
    3. 遍历蓝图，将 Offset 叠加到坐标参数上。
    4. 调用 Structure 接口生成实体 (此时 Structure 处于执行模式)。
"""

from typing import List, Dict, Any, Union, Tuple
import numpy as np
from .structure import Structure
from .array_layout import ArrayLayout 
from src.utils.logger import logger

class ArrayStructure:
    """
    阵列结构生成器
    
    职责：
        作为“带偏移的播放器”。
        它不继承 Structure，而是依赖 Structure 实例来执行构建。
    """

    def __init__(self):
        """初始化阵列生成器。"""
        self._layout_engine = ArrayLayout()

    def create_array(self, 
                     structure: Structure, 
                     unit_name: str,
                     matrix: Union[List[List[Any]], np.ndarray],
                     pitch_u: Union[float, List[float]],
                     pitch_v: Union[float, List[float]],
                     plane: str = 'xy',
                     alignment: str = 'center',
                     symmetry: str = None) -> List[str]:
        """
        执行阵列生成。
        """
        # 1. 获取蓝图
        blueprint = structure.get_blueprint(unit_name)
        if not blueprint:
            raise ValueError(f"单元 '{unit_name}' 未定义或蓝图为空。")
        
        # 2. 计算布局
        instances = self._layout_engine.compute_layout(
            unit_name=unit_name,
            matrix=matrix, 
            pitch_u=pitch_u, 
            pitch_v=pitch_v,
            plane=plane,
            alignment=alignment,
            symmetry=symmetry
        )

        all_created_names = []

        # 3. 遍历每个单元位置
        for inst in instances:
            cell_name = inst['name']           
            offset = np.array(inst['position']) 
            
            # 名称映射表：用于布尔运算重定向
            name_mapping = {}

            # 4. 遍历蓝图，重放操作
            for op_idx, op in enumerate(blueprint):
                op_type = op['type']

                # --- 执行构建 ---
                try:
                    if op_type in ['add', 'subtract']:
                        # 对于布尔运算，不需要生成 unique_name，也不需要偏移坐标
                        # 只需要根据 name_mapping 替换操作数即可
                        if op_type == 'add':
                            self._build_add(structure, op, name_mapping)
                        elif op_type == 'subtract':
                            self._build_subtract(structure, op, name_mapping)
                    
                    else:
                        # 对于几何体，生成唯一名称并偏移坐标
                        original_name = op.get('name')
                        if not original_name:
                            raise KeyError(f"蓝图操作 '{op_type}' 缺少必要的 'name' 字段: {op}")

                        unique_name = f"{cell_name}_{original_name}_{op_idx}"
                        name_mapping[original_name] = unique_name

                        if op_type == 'brick':
                            self._build_brick(structure, op, unique_name, offset)
                        elif op_type == 'cylinder':
                            self._build_cylinder(structure, op, unique_name, offset)
                        elif op_type == 'polygon3D':
                            self._build_polygon3d(structure, op, unique_name, offset)  

                        all_created_names.append(unique_name)
                    
                except Exception as e:
                    logger.error(f"阵列生成错误 [{cell_name} - {op_type}]: {e}")
                    raise

        return all_created_names

    # ==================================================================================
    # 内部构建器：严格处理坐标偏移
    # ==================================================================================

    def _build_brick(self, structure: Structure, op: Dict, name: str, offset: np.ndarray):
        """
        构建长方体：Xrange/Yrange/Zrange 分别加上 offset[x/y/z]
        """
        dx, dy, dz = offset

        def safe_add(val, delta):
            """安全地处理数值或字符串表达式的偏移"""
            if isinstance(val, str):
                # 如果是字符串（如 "-W/2"），将其包装成数学表达式：(原表达式) + 偏移量
                # 加上括号是为了防止优先级错误，例如 "-W/2" 变成 "(-W/2) + 10.0"
                return f"({val}) + {delta}"
            else:
                # 如果是数字，直接相加
                return val + delta
        
        # 重新计算坐标范围
        # 1. X 轴
        new_xrange = [safe_add(op['Xrange'][0], dx), safe_add(op['Xrange'][1], dx)]
        
        # 2. Y 轴
        new_yrange = [safe_add(op['Yrange'][0], dy), safe_add(op['Yrange'][1], dy)]
        
        # 3. Z 轴 (同样使用 safe_add 以防万一)
        new_zrange = [safe_add(op['Zrange'][0], dz), safe_add(op['Zrange'][1], dz)]

        structure.create_brick(
            name=name,
            material=op['material'],
            Xrange=new_xrange,
            Yrange=new_yrange,
            Zrange=new_zrange,
            color=op.get('color')
        )

    def _build_cylinder(self, structure: Structure, op: Dict, name: str, offset: np.ndarray):
        """
        构建圆柱体：根据 axis 严格处理 pos_1, pos_2, range_val 的偏移
        
        逻辑分析 (基于 structure.py 的通用实现):
        - Axis='z': 圆柱沿 Z 轴。pos_1(X), pos_2(Y) 是圆心。range_val 是 Z 范围。
        - Axis='x': 圆柱沿 X 轴。pos_1(Y), pos_2(Z) 是圆心。range_val 是 X 范围。
        - Axis='y': 圆柱沿 Y 轴。pos_1(X), pos_2(Z) 是圆心。range_val 是 Y 范围。
        """
        dx, dy, dz = offset
        axis = op.get('axis', 'z').lower()
        
        new_pos_1 = op['pos_1']
        new_pos_2 = op['pos_2']
        new_range = list(op['range_val']) # 转为 list 以便修改

        if axis == 'z':
            # 沿 Z 轴生长
            # pos_1 是 X 坐标 -> + dx
            # pos_2 是 Y 坐标 -> + dy
            # range_val 是 Z 范围 -> + dz
            new_pos_1 += dx
            new_pos_2 += dy
            new_range[0] += dz
            new_range[1] += dz
            
        elif axis == 'x':
            # 沿 X 轴生长
            # pos_1 是 Y 坐标 -> + dy
            # pos_2 是 Z 坐标 -> + dz
            # range_val 是 X 范围 -> + dx
            new_pos_1 += dy
            new_pos_2 += dz
            new_range[0] += dx
            new_range[1] += dx
            
        elif axis == 'y':
            # 沿 Y 轴生长
            # pos_1 是 X 坐标 -> + dx
            # pos_2 是 Z 坐标 -> + dz
            # range_val 是 Y 范围 -> + dy
            new_pos_1 += dx
            new_pos_2 += dz
            new_range[0] += dy
            new_range[1] += dy
            
        else:
            # 默认处理或报错
            pass

        structure.create_cylinder(
            name=name,
            material=op['material'],
            r_out=op['r_out'],
            r_in=op['r_in'],
            pos_1=new_pos_1,
            pos_2=new_pos_2,
            range_val=new_range,
            color=op.get('color'),
            axis=axis
        )

    def _build_polygon3d(self, structure: Structure, op: Dict, name: str, offset: np.ndarray):
        """
        构建多边形：遍历 vertices_3d，每个顶点 (x,y,z) 加上 offset
        """
        dx, dy, dz = offset
        new_vertices = []
        
        for vx, vy, vz in op['vertices_3d']:
            new_vertices.append((vx + dx, vy + dy, vz + dz))
            
        structure.create_polygon3D(
            name=name,
            material=op['material'],
            vertices_3d=new_vertices,
            thickness=op['thickness'], # 厚度是标量，不需要偏移
            color=op.get('color')
        )

    def _build_add(self, structure: Structure, op: Dict, name_mapping: Dict[str, str]):
        """
        布尔加法：根据 name_mapping 重定向操作对象名称。
        """
        # 从映射表中获取当前实例中对应的物体新名称
        blank_new_name = name_mapping.get(op['blank_name'])
        tool_new_name = name_mapping.get(op['tool_name'])
        
        # 如果映射表中找不到对应的名称，说明蓝图录制或逻辑有误
        if not blank_new_name or not tool_new_name:
            raise KeyError(f"无法在 name_mapping 中找到布尔加法所需的物体: "
                           f"blank='{op['blank_name']}', tool='{op['tool_name']}'")
        
        # 传入重定向后的新名称
        structure.add(blank_name=blank_new_name, tool_name=tool_new_name)

    def _build_subtract(self, structure: Structure, op: Dict, name_mapping: Dict[str, str]):
        """
        布尔减法：根据 name_mapping 重定向操作对象名称。
        """
        blank_new_name = name_mapping.get(op['blank_name'])
        tool_new_name = name_mapping.get(op['tool_name'])
        
        if not blank_new_name or not tool_new_name:
            raise KeyError(f"无法在 name_mapping 中找到布尔减法所需的物体: "
                           f"blank='{op['blank_name']}', tool='{op['tool_name']}'")
        
        structure.subtract(blank_name=blank_new_name, tool_name=tool_new_name)