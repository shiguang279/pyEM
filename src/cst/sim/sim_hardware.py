# 这个文件没有实际用处，存放了 CST VBA 代码的一些注释。

class CSTHardware:
    """
    职责：处理所有与 CPU/GPU 硬件加速相关的配置。
    """
    
    def __init__(self, vba):
        self.vba = vba

    def set_solver_cpu(self, max_threads: int = 16, max_devices: int = 1) -> None:
        """配置 CPU 并行计算参数

        Args:
            max_threads (int): 最大线程数
            max_devices (int): 最大 CPU 设备数
        """
        vba_cpu = f'''
With Solver
    .UseParallelization "True"
    .MaximumNumberOfThreads "{max_threads}"
    .MaximumNumberOfCPUDevices "{max_devices}"
    .RemoteCalculation "False"
    .UseDistributedComputing "False"
    .MaxNumberOfDistributedComputingPorts "64"
    .DistributeMatrixCalculation "False"
    .MPIParallelization "False"
    .AutomaticMPI "False"
    .ConsiderOnly0D1DResultsForMPI "False"
End With

UseDistributedComputingForParameters "False"
MaxNumberOfDistributedComputingParameters "1"
UseDistributedComputingMemorySetting "False"
MinDistributedComputingMemoryLimit "0"
UseDistributedComputingSharedDirectory "False"
OnlyConsider0D1DResultsForDC "False"
'''
        self.vba.to_cst_history(vba_cpu, "CPU Parallelization Settings")

    def set_solver_gpu(self, gpu_count: int = 1) -> None:
        """
        启用并配置 GPU 硬件加速

        注意：CST 的 GPU 加速主要针对 NVIDIA 专业显卡（支持 CUDA），（游戏卡也可以），
        同时也支持部分 AMD 显卡（仅限特定求解器）。

        Args:
            gpu_count (int): 使用的 GPU 数量
        """
        vba_gpu = f'''
With Solver
    .HardwareAcceleration "True"
    .MaximumNumberOfGPUs "{gpu_count}"
End With
'''
        self.vba.to_cst_history(vba_gpu, "GPU Acceleration Settings")
