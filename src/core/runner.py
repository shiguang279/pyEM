# -*- coding: utf-8 -*-
import os
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, Optional, Type, List, Callable
from src.utils.logger import logger

class RunMode(Enum):
    """
    仿真运行模式枚举 (定义任务的基本执行方式)
    """
    SAVE_ONLY = "save_only"        # 仅保存项目文件
    SAVE_AND_RUN = "save_and_run"  # 保存工程并求解

class SimulationMode(Enum):
    """
    仿真类型枚举 (定义任务的业务逻辑类型)
    """
    DESIGN = "design"              # GUI交互式设计模式 (通常为单任务)

    # 参数化建模，支持并行，仅改变参数数值，保持模型拓扑结构不变。
    PARAMETRIC_MODELING = "parametric_modeling" 

    # 拓扑建模，涉及迭代仿真，支持并行。侧重于结构的拓扑变化与重构。
    TOPOLOGY_MODELING = "topology_modeling"


# 全局注册表：存储 软件名 -> Runner类 的映射
RUNNER_REGISTRY: Dict[str, Type['SimRunner']] = {}

def register_runner(software_name: str, runner_class: Type['SimRunner']) -> None:
    """注册仿真运行器到全局注册表。"""
    RUNNER_REGISTRY[software_name.upper()] = runner_class
    logger.debug(f"Runner registered: {software_name}")

class SimRunner(ABC):
    """
    仿真运行器抽象基类。

    【核心职责】
    1. 生命周期管理：通过上下文管理器管理软件进程（启动/关闭）。
    2. 流程编排：
       - 创建 SimFlow 并注入参数。
       - 根据 RunMode 决定是仅保存还是保存并求解。
    """

    def __init__(self, output_dir: str = "output", run_mode: RunMode = RunMode.SAVE_AND_RUN, simulation_mode: SimulationMode = SimulationMode.DESIGN):
        """
        初始化运行器。
        Args:
            output_dir (str): 仿真结果输出目录。
            run_mode (RunMode): 运行模式枚举 (任务执行方式)。
            simulation_mode (SimulationMode): 仿真类型枚举 (任务业务逻辑)。
        """
        self.output_dir = output_dir
        self.run_mode: RunMode = run_mode
        self.simulation_mode: SimulationMode = simulation_mode 
        # 用于标识是否使用动态注入的 Setup 实例
        self._dynamic_setup_instance_for_runner = None
        self.setup_dict = None
        self.design_env_instance = None
        self.current_project = None
    
    @classmethod
    def start_design_environment(cls):
        """
        类方法：启动底层的仿真软件环境。
        """
        raise NotImplementedError("子类必须实现 start_design_environment 方法以启动软件环境。")

    def set_shared_design_env(self, design_env_instance):
        """
        设置共享的 DesignEnvironment。
        这是实现“主进程单例”的关键入口。
        """
        self.design_env_instance = design_env_instance
        logger.debug(f"Runner 已绑定共享的 DesignEnvironment 实例 (PID: {getattr(design_env_instance, 'pid', 'Unknown')})")

    def set_dynamic_setup_instance(self, setup_instance):
        """
        为当前 Runner 实例动态注入 Setup 实例。
        调用此方法后，_execute_simulation_flow 将优先使用此实例。
        """
        self._dynamic_setup_instance_for_runner = setup_instance
    
    @abstractmethod
    def close_project(self) -> None:
        """
        抽象方法：由子类实现。
        仅关闭当前 Project，不关闭底层的 DesignEnvironment。
        """
        pass

    @abstractmethod
    def run(self, setup_dict: Dict = None, params: Optional[Dict[str, Any]] = None, project_file: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        抽象方法：子类必须实现具体的仿真运行逻辑。
        
        Args:
            params: 仿真参数字典。
            project_file: 项目文件路径，用于保存结果。
        """
        pass

    def get_software_name(self) -> str:
        """获取软件名称用于日志（子类实现）。"""
        return "Unknown"

    @abstractmethod
    def create_project(self, design_env_instance):
        """
        抽象方法：创建并返回一个项目。
        """
        pass

    @abstractmethod
    def open_project(self, design_env_instance, project_file):
        """
        抽象方法：打开一个项目。
        """
        pass
