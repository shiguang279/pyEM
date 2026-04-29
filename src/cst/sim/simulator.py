"""
模块：simulator.py
这个文件夹没有实际用处，存放了 CST VBA 代码的一些注释。
描述：CST 仿真核心执行器，负责组合各个子模块并执行仿真流程。
"""

from ..vba import CSTVBA
from .sim_boundary import CSTBoundary
from .sim_mesh import CSTMesh
from .sim_solver import CSTSolver
from .sim_hardware import CSTHardware
from ...utils.logger import logger

# 这个文件没有实际用处，存放了 CST VBA 代码的一些注释。

class CSTSimulator:
    """
    CST 仿真执行器
    
    职责：
        通过依赖注入，统一管理 Boundary, Mesh, Solver, Hardware 模块，
        提供高层级的仿真设置接口。
    """
    
    def __init__(self, vba: CSTVBA):
        # 组合各个子模块
        self.boundary = CSTBoundary(vba)
        self.mesh = CSTMesh(vba)
        self.solver = CSTSolver(vba)
        self.hardware = CSTHardware(vba)
        
        # 保留 vba 引用用于日志或通用操作
        self.vba = vba

    def set_simulation(self, f_min: float, f_max: float, f_step: float = 0.1, 
                       solver_type: str = 'TD', gpu: bool = False,
                       boundary_type: str = 'open', boundary_params: dict = None) -> None:
        """执行 CST 仿真流程设置，负责底层的 VBA 指令执行。

        该方法按顺序调用各个子模块，完成从环境、边界、网格到求解器的配置。

        Args:
            f_min (float): 仿真起始频率 (单位: GHz)
            f_max (float): 仿真截止频率 (单位: GHz)
            f_step (float): 频率采样步长，默认为 0.1 GHz
            solver_type (str): 'FD' (频域) 或 'TD' (时域，默认)
            gpu (bool): 是否启用 GPU 硬件加速，默认为 False
            boundary_type (str): 边界类型 ('open' 或 'unit_cell')，默认为 'open'
            boundary_params (dict): 边界相关参数字典 (如 theta, phi)，默认为 None
        """
        logger.info(f"[{self.__class__.__name__}] 开始 CST 仿真设置...")
        
        # 1. 基础环境设置
        self.boundary.set_units()  # 设置单位系统 (mm, GHz)
        self.boundary.set_pml(f_min)  # 设置 PML 边界参数
        self.boundary.set_background()  # 设置背景材料
        
        # 2. 边界条件设置 (支持动态切换)
        if boundary_params is None:
            boundary_params = {}
        self.boundary.apply_boundary_type(boundary_type, boundary_params)
        
        # 3. 网格设置
        self.mesh.set_mesh()  # 初始化网格设置 (依赖前面的边界和频率)
        
        # 4. 求解器与硬件设置
        self.solver.set_frequency(f_min, f_max, f_step)  # 定义频率范围
        self.solver.set_solver_type(solver_type)  # 设置求解器类型
        
        # 5. 硬件加速配置
        self.hardware.set_solver_cpu()  # 启用 CPU 多线程
        
        if gpu and solver_type.upper() == 'TD':
            self.hardware.set_solver_gpu()
            logger.info(" [GPU] Acceleration enabled for Time Domain solver.")
        elif gpu and solver_type.upper() == 'FD':
            # 频域求解器通常不支持 GPU 加速
            logger.warning(" [GPU] Acceleration skipped: FD solver relies on CPU.")
            logger.warning(" [GPU] Support depends on software version; currently disabled.")
            logger.warning(" [CPU] Proceeding with CPU parallelization only.")
            
        logger.info(f"[{self.__class__.__name__}] CST 仿真设置完成。")