"""
sim_boundary.py 负责 CST 项目的边界条件与基础环境配置。
"""

from typing import Dict, Any

# 这个文件没有实际用处，存放了 CST VBA 代码的一些注释。

class CSTBoundary:
    """
    职责：处理单位、背景材料、PML 参数及具体边界条件（开放/周期）。
    """
    
    def __init__(self, vba):
        self.vba = vba

    def set_units(self) -> None:
        """设置 CST 项目中的物理单位系统"""
        vba_units = '''
With Units
    .SetUnit "Length", "mm"
    .SetUnit "Frequency", "GHz"
    .SetUnit "Time", "ns"
    .SetResultUnit "frequency", "frequency", ""
End With
'''
        self.vba.to_cst_history(vba_units, "Set Units")

    def set_background(self) -> None:
        """设置背景材料属性（真空）"""
        vba_bg = '''
With Background
    .ResetBackground
    .XminSpace "0"
    .XmaxSpace "0"
    .YminSpace "0"
    .YmaxSpace "0"
    .ZminSpace "0"
    .ZmaxSpace "0"
    .ApplyInAllDirections "True"
End With

With Material
    .Reset
    .Type "Normal"
    .Epsilon "1.0"
    .Mu "1.0"
    .ChangeBackgroundMaterial
End With
'''
        self.vba.to_cst_history(vba_bg, "Define Background")

    def set_pml(self, freq_low: float) -> None:
        """配置 PML (完美匹配层) 参数"""
        vba_pml = f'''
With Boundary
    .ReflectionLevel "0.0001"
    .MinimumDistanceType "Fraction"
    .MinimumDistancePerWavelengthNewMeshEngine "4"
    .MinimumDistanceReferenceFrequencyType "User"
    .FrequencyForMinimumDistance "{freq_low}"
    .SetAbsoluteDistance "0.0"
End With
'''
        self.vba.to_cst_history(vba_pml, "Set PML Parameters")

    def apply_boundary_type(self, b_type: str, params: dict) -> None:
        """
        根据类型应用具体的边界条件
        Args:
            b_type: 'open' 或 'unit_cell'
            params: 参数字典
        """
        if b_type == 'unit_cell':
            self._set_unit_cell(params)
        else:
            # 默认走开放边界逻辑，但允许通过 params 自定义对称性
            self._set_open_boundary(params)

    def _set_open_boundary(self, params: Dict[str, Any]) -> None:
        """
        设置开放边界
        这里封装了你提供的 With Boundary 代码，并支持参数化
        """
        # 1. 从参数中获取设置，如果没有则使用默认值
        # 默认全向开放
        x_min = params.get('x_min', 'expanded open')
        x_max = params.get('x_max', 'expanded open')
        y_min = params.get('y_min', 'expanded open')
        y_max = params.get('y_max', 'expanded open')
        z_min = params.get('z_min', 'expanded open')
        z_max = params.get('z_max', 'expanded open')
        
        # 对称性设置 (默认 X 为 magnetic，其他为 none，符合微带天线常见设置)
        x_sym = params.get('x_symmetry', 'magnetic')
        y_sym = params.get('y_symmetry', 'none')
        z_sym = params.get('z_symmetry', 'none')

        # 2. 构建 VBA 代码
        # 注意：这里保留了你提供的完整结构，包括 Thermal 设置
        vba_bc = f'''
With Boundary
    .Xmin "{x_min}"
    .Xmax "{x_max}"
    .Ymin "{y_min}"
    .Ymax "{y_max}"
    .Zmin "{z_min}"
    .Zmax "{z_max}"
    .Xsymmetry "{x_sym}"
    .Ysymmetry "{y_sym}"
    .Zsymmetry "{z_sym}"
    .XminThermal "isothermal"
    .XmaxThermal "isothermal"
    .YminThermal "isothermal"
    .YmaxThermal "isothermal"
    .ZminThermal "isothermal"
    .ZmaxThermal "isothermal"
    .XsymmetryThermal "none"
    .YsymmetryThermal "none"
    .ZsymmetryThermal "none"
    .ApplyInAllDirections "True"
    .XminTemperature ""
    .XminTemperatureType "None"
    .XmaxTemperature ""
    .XmaxTemperatureType "None"
    .YminTemperature ""
    .YminTemperatureType "None"
    .YmaxTemperature ""
    .YmaxTemperatureType "None"
    .ZminTemperature ""
    .ZminTemperatureType "None"
    .ZmaxTemperature ""
    .ZmaxTemperatureType "None"
End With
'''
        self.vba.to_cst_history(vba_bc, "Set Open Boundary")

    def _set_unit_cell(self, params: dict) -> None:
        """设置周期边界 (Floquet)"""
        theta = params.get('theta', 0)
        phi = params.get('phi', 0)
        modes = params.get('modes', 2)
        
        # 1. 设置 X/Y 为 Unit Cell
        vba_bc = f'''
With Boundary
    .Xmin "unit cell"
    .Xmax "unit cell"
    .Ymin "unit cell"
    .Ymax "unit cell"
    .Zmin "expanded open"
    .Zmax "expanded open"
End With
'''
        self.vba.to_cst_history(vba_bc, "Set Unit Cell BC")

        # 2. 设置 Floquet 端口
        vba_floquet = f'''
With FloquetPort
    .Reset
    .SetDialogTheta "{theta}"
    .SetDialogPhi "{phi}"
    .Port "Zmax"
    .SetNumberOfModesConsidered "{modes}"
    .Port "Zmin"
    .SetNumberOfModesConsidered "{modes}"
End With
'''
        self.vba.to_cst_history(vba_floquet, "Set Floquet Ports")