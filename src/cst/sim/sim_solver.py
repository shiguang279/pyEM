# 这个文件没有实际用处，存放了 CST VBA 代码的一些注释。

class CSTSolver:
    """
    职责：处理求解器类型切换和频率设置。
    """
    
    def __init__(self, vba):
        self.vba = vba

    def set_frequency(self, freq_low: float, freq_high: float, freq_step: float = 0.1) -> None:
        """配置求解器的频率扫描范围和采样点数

        Args:
            freq_low (float): 起始频率 (GHz)
            freq_high (float): 截止频率 (GHz)
            freq_step (float): 频率步长 (GHz)
        """
        num_samples = max(1, int((freq_high - freq_low) / freq_step + 1))
        vba = f'''
With Solver
    .FrequencyRange "{freq_low}", "{freq_high}"
    .FrequencySamples "{num_samples}"
End With
'''
        self.vba.to_cst_history(vba, "Define Frequency Range")

    def set_solver_type(self, solver_type: str = 'TD') -> None:
        """配置 CST 求解器类型 (频域 FD 或 时域 TD)"""
        solver_type = solver_type.upper()
        if solver_type == 'FD': 
            vba_fd = '''
With FDSolver
    .Reset
    .Stimulation "All", "All"
    .AutoNormImpedance "True"
    .NormingImpedance "50"
    .ModesOnly "False"
    .Start
End With
'''
            self.vba.to_cst_history(vba_fd, "Run Frequency Domain Solver")
            print(" Frequency Domain solver started")
        elif solver_type == 'TD':
            # 切换求解器类型为 "HF Time Domain"
            self.vba.to_cst_history('ChangeSolverType("HF Time Domain")', "Switch to HF Time Domain")
            
            vba_td = '''
With Solver
    .Reset
    .Method "Hexahedral"
    .CalculationType "TD-S"
    .StimulationPort "All"
    .StimulationMode "All"
    .SteadyStateLimit "-40"
    .MeshAdaption "False"
    .AutoNormImpedance "True"
    .NormingImpedance "50"
    .CalculateModesOnly "False"
    .SParaSymmetry "False"
    .StoreTDResultsInCache "True"
    .RunDiscretizerOnly "False"
    .FullDeembedding "False"
    .SuperimposePLWExcitation "False"
    .UseSensitivityAnalysis "False"
End With
'''
            self.vba.to_cst_history(vba_td, "Time Domain Solver")
        else:
            raise ValueError(f'Unknown solver type: "{solver_type}". \n'
                             'Currently, only "FD" (Frequency Domain) and "TD" (Time Domain) are implemented. \n'
                             'Other solver types are not yet supported.')

