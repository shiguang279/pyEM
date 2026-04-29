# -*- coding: utf-8 -*-
# array_layout.py
from typing import List, Dict, Any, Tuple, Union
import numpy as np

class ArrayLayout:
    """
    阵列布局计算器

    核心职责：
        1. 计算坐标：根据矩阵索引和间距计算物理空间中的绝对位置。
        2. 处理变换：计算等比缩放因子和平面内旋转角度。
        3. 空间映射：处理不同平面（XY, YZ, XZ）的坐标转换。
        4. 数据输出：输出标准化的布局数据，供 ArrayStructure 消费。
    """

    def compute_layout(
        self,
        unit_name: str,
        matrix: Union[List[List[Any]], np.ndarray],
        pitch_u: Union[float, int, List[float], np.ndarray],
        pitch_v: Union[float, int, List[float], np.ndarray],
        plane: str = 'xy',
        alignment: str = 'center',
        symmetry: str = None
    ) -> List[Dict[str, Any]]:
        """
        计算阵列中所有单元的布局数据。

        Args:
            unit_name (str): 原型单元名称。
            matrix: 布局矩阵。元素可以是 0/1 或 {'scale': 1.5, 'rotate': 45}。
            pitch_u: U方向（列）的间距。
            pitch_v: V方向（行）的间距。
            plane: 阵列所在的物理平面 ('xy', 'yz', 'xz')。
            alignment: 对齐方式 ('center', 'bottom_left', 'bottom_center')。
            symmetry: 对称轴定义。

        Returns:
            List[Dict[str, Any]]: 包含每个单元信息的列表。
        """
        # 1. 基础参数处理
        matrix = np.array(matrix)
        rows, cols = matrix.shape
        instances: List[Dict[str, Any]] = []

        # 2. 间距标准化
        pitch_u_list = self._normalize_pitch(pitch_u, cols)
        pitch_v_list = self._normalize_pitch(pitch_v, rows)

        # 3. 计算累加坐标
        pos_u_abs = self._calculate_absolute_positions(pitch_u_list)
        pos_v_abs = self._calculate_absolute_positions(pitch_v_list)

        # 4. 计算对齐偏移
        offset_u, offset_v = self._calculate_alignment_offset(
            pos_u_abs, pos_v_abs, alignment
        )

        # 5. 确定物理轴映射
        # u=列方向, v=行方向, w=法线方向(厚度/旋转轴)
        plane_map = {
            'xy': {'u': 0, 'v': 1, 'w': 2}, # U->X, V->Y, 旋转轴->Z
            'yz': {'u': 1, 'v': 2, 'w': 0}, # U->Y, V->Z, 旋转轴->X
            'xz': {'u': 0, 'v': 2, 'w': 1}  # U->X, V->Z, 旋转轴->Y
        }
        current_plane = plane_map.get(plane.lower(), plane_map['xy'])

        # 6. 遍历矩阵生成单元数据
        for row_idx in range(rows):
            for col_idx in range(cols):
                cell_value = matrix[row_idx, col_idx]
                
                # 6.1 检查是否激活
                if not self._is_cell_active(cell_value):
                    continue

                # 6.2 解析单元属性
                # 获取等比缩放因子 (float) 和 平面内旋转角度 (float)
                scale_factor, rotation_angle = self._parse_cell_transform(cell_value)

                # 6.3 计算局部坐标
                u_local = pos_u_abs[col_idx] + offset_u
                v_local = pos_v_abs[row_idx] + offset_v
                w_local = 0.0

                # 6.4 映射到物理空间 (XYZ)
                x, y, z = 0.0, 0.0, 0.0
                if current_plane['u'] == 0: x = u_local
                elif current_plane['u'] == 1: y = u_local
                elif current_plane['u'] == 2: z = u_local

                if current_plane['v'] == 0: x = v_local
                elif current_plane['v'] == 1: y = v_local
                elif current_plane['v'] == 2: z = v_local

                if current_plane['w'] == 0: x = w_local
                elif current_plane['w'] == 1: y = w_local
                elif current_plane['w'] == 2: z = w_local

                position = (x, y, z)

                # 6.5 生成单元名称
                cell_name = f"Cell_R{row_idx}C{col_idx}"
                
                instances.append({
                    "name": cell_name,
                    "position": position,
                    "rotation": rotation_angle, # 【修改】这里现在是单个角度值 (float)
                    "scale": scale_factor,      # 等比缩放因子 (float)
                    "rot_axis": current_plane['w'], # 【新增】告知 Structure 绕哪个轴旋转 (0=x, 1=y, 2=z)
                    "source": unit_name,
                    "type": "original"
                })

                # 6.6 应用对称逻辑
                if symmetry:
                    self._apply_symmetry(
                        instances, cell_name, position, rotation_angle, scale_factor, unit_name, symmetry
                    )

        return instances

    # --- 辅助方法 ---

    def _normalize_pitch(self, pitch: Any, length: int) -> List[float]:
        """将间距参数标准化为列表。"""
        if np.isscalar(pitch):
            return [float(pitch)] * length
        
        pitch_list = np.asarray(pitch, dtype=float).tolist()
        if len(pitch_list) < length:
            pitch_list.extend([pitch_list[-1]] * (length - len(pitch_list)))
        return pitch_list

    def _calculate_absolute_positions(self, pitches: List[float]) -> List[float]:
        """计算累加位置: [0, p1, p1+p2, ...]"""
        positions = [0.0]
        for p in pitches[:-1]:
            positions.append(positions[-1] + p)
        return positions

    def _calculate_alignment_offset(self, pos_u: List[float], pos_v: List[float], mode: str) -> Tuple[float, float]:
        """根据对齐模式计算整体偏移量。"""
        if not pos_u: return 0.0, 0.0
        
        span_u = pos_u[-1] - pos_u[0]
        span_v = pos_v[-1] - pos_v[0]
        
        offset_u, offset_v = 0.0, 0.0

        if mode == 'center':
            offset_u = -span_u / 2.0
            offset_v = -span_v / 2.0
        elif mode == 'bottom_center':
            offset_u = -span_u / 2.0
            
        return offset_u, offset_v

    def _is_cell_active(self, data: Any) -> bool:
        """判断单元格是否激活。"""
        if isinstance(data, (int, float)):
            return data == 1
        return True

    def _parse_cell_transform(self, data: Any) -> Tuple[float, float]:
        """
        解析单元的变换参数。
        
        支持格式：
        1. 数字 (1): 默认缩放 1.0，旋转 0 度。
        2. 字典 ({'scale': 1.5, 'rotate': 45}): 
           - scale: 标量 (等比缩放)。
           - rotate: 标量 (平面内旋转角度，单位：度)。

        Returns:
            Tuple[float, float]: (scale_factor, rotation_angle_degrees)
        """
        if isinstance(data, (int, float, np.generic)):
            return 1.0, 0.0
        
        if isinstance(data, dict):
            # 获取缩放因子
            scale_val = data.get('scale', 1.0)
            if not isinstance(scale_val, (int, float)):
                scale_val = 1.0
                
            # 获取旋转角度 (标量)
            rotate_val = data.get('rotate', 0.0)
            if not isinstance(rotate_val, (int, float)):
                rotate_val = 0.0
            
            return float(scale_val), float(rotate_val)
            
        return 1.0, 0.0

    def _apply_symmetry(self, instances: List, cell_name: str, 
                       pos: Tuple, rot: float, scale: float, 
                       source: str, symmetry: str):
        """生成对称单元的副本。"""
        axes_to_mirror = []
        if 'x' in symmetry.lower(): axes_to_mirror.append(0)
        if 'y' in symmetry.lower(): axes_to_mirror.append(1)
        if 'z' in symmetry.lower(): axes_to_mirror.append(2)

        for axis_idx in axes_to_mirror:
            mirror_pos = list(pos)
            mirror_pos[axis_idx] *= -1 

            axis_name = ['x', 'y', 'z'][axis_idx]
            instances.append({
                "name": f"{cell_name}_Sym{axis_name.upper()}",
                "position": tuple(mirror_pos),
                "rotation": rot,
                "scale": scale,
                "source": source,
                "type": f"symmetry_{axis_name}"
            })