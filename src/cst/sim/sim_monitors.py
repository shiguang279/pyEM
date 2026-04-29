# 这个文件没有实际用处，存放了 CST VBA 代码的一些注释。

class CSTMonitors:
    """
    职责：处理所有与仿真监控器（电场、远场）相关的配置。
    """
    
    def __init__(self, vba):
        self.vba = vba

    def add_monitors_efield(self, freq: float = 8.0) -> None:
        """添加单点电场 (E-field) 监控器

        Args:
            freq (float): 监控频率 (GHz)
        """
        vba_e = f'''
With Monitor
    .Reset
    .Name "e-field (f={freq})"
    .Domain "Frequency"
    .FieldType "Efield"
    .MonitorValue "{freq}"
    .UseSubvolume "False"
    .Create
End With
'''
        self.vba.to_cst_history(vba_e, f"E-field Monitor @ {freq} GHz")

    def add_monitors_farfield(self, freq: float = 8.0) -> None:
        """添加单点远场 (Farfield) 监控器

        Args:
            freq (float): 监控频率 (GHz)
        """
        vba_far = f'''
With Monitor
    .Reset
    .Name "farfield (f={freq})"
    .Domain "Frequency"
    .FieldType "Farfield"
    .MonitorValue "{freq}"
    .ExportFarfieldSource "False"
    .UseSubvolume "False"
    .EnableNearfieldCalculation "True"
    .Create
End With
'''
        self.vba.to_cst_history(vba_far, f"Farfield Monitor @ {freq} GHz")

    def add_monitors_efield_step(self, freq_start: float, freq_end: float, freq_step: float) -> None:
        """批量添加电场监控器 (线性步长)

        Args:
            freq_start (float): 起始频率
            freq_end (float): 终止频率
            freq_step (float): 步长
        """
        vba_e = f'''
With Monitor
    .Reset
    .Domain "Frequency"
    .FieldType "Efield"
    .UseSubvolume "False"
    .Coordinates "Structure"
    .SetSubvolume "-30", "30", "-30", "30", "-3", "1.56"
    .SetSubvolumeOffset "0.0", "0.0", "0.0", "0.0", "0.0", "0.0"
    .SetSubvolumeInflateWithOffset "False"
    .CreateUsingLinearStep "{freq_start}", "{freq_end}", "{freq_step}"
End With
'''
        self.vba.to_cst_history(vba_e, f"E-field Monitor {freq_start} - {freq_end} GHz")

    def add_monitors_farfield_step(self, freq_start: float, freq_end: float, freq_step: float) -> None:
        """批量添加远场监控器 (线性步长)

        Args:
            freq_start (float): 起始频率
            freq_end (float): 终止频率
            freq_step (float): 步长
        """
        vba_far = f'''
With Monitor
    .Reset
    .Domain "Frequency"
    .FieldType "Farfield"
    .ExportFarfieldSource "False"
    .UseSubvolume "False"
    .Coordinates "Structure"
    .SetSubvolume "-30", "30", "-30", "30", "-3", "1.56"
    .SetSubvolumeOffset "10", "10", "10", "10", "10", "10"
    .SetSubvolumeInflateWithOffset "False"
    .SetSubvolumeOffsetType "FractionOfWavelength"
    .EnableNearfieldCalculation "True"
    .CreateUsingLinearStep "{freq_start}", "{freq_end}", "{freq_step}"
End With
'''
        self.vba.to_cst_history(vba_far, f"Farfield Monitor {freq_start} - {freq_end} GHz")