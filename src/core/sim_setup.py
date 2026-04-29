# -*- coding: utf-8 -*-
"""
仿真设置基类模块 (SimSetup)

该模块定义了仿真任务的基础配置结构，负责管理仿真参数、文件路径、
导出选项以及仿真模式的设定。它是所有具体仿真设置类的抽象基类。
"""

import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from src.core.sim_runner import SimulationMode, RunMode
from src.utils.logger import logger

if TYPE_CHECKING:
    from .designer import Designer


class SimSetup(ABC):
    """
    仿真设置抽象基类。

    该类充当仿真配置的容器和上下文管理器。子类必须实现 `setup` 方法
    来定义具体的仿真逻辑。

    核心职责:
        1. 定义仿真所需的物理参数（频率、尺寸等）。
        2. 实例化并持有 Designer（自动建模策略）。
        3. 定义结果导出选项（S参数、增益、VSWR等）。
        4. 管理工程文件路径和输出目录。
    """

    # 上下文单例，用于全局获取当前激活的配置实例
    _current_setup: Optional['SimSetup'] = None
    
    # 存储 Designer 实例，用于后续的建模流程
    designer: Optional['Designer'] = None
    
    # 导出配置列表
    export_options: List[str]

    def __init__(self, default_output_dir: str = "output") -> None:
        """
        初始化仿真设置类。

        Args:
            default_output_dir (str): 默认输出目录名称。
        """
        # 1. 初始化参数池
        self.sim_params: Dict[str, Any] = {}
        self.sweep_params: Dict[str, Any] = {}
        
        # 2. 初始化导出选项
        self.export_options: List[str] = [] 
        self.file_path: Optional[str] = None
        self.run_mode = RunMode.SAVE_AND_RUN
        self.simulation_mode = SimulationMode.DESIGN
        self.output_dir: Optional[str] = None
        
        # 设置输出目录
        self.set_output_dir(default_output_dir)

        # 3. 注册当前实例到全局上下文
        SimSetup._current_setup = self
        
        logger.info(f"Starting Setup: {self.__class__.__name__}")
        
        # 4. 执行参数定义与 Designer 实例化 (由子类实现)
        self.setup()
        
        # 5. 强制校验导出配置
        # 如果不是纯设计模式，必须有导出选项
        if self.simulation_mode != SimulationMode.DESIGN:
            self._validate_export_options()

    @classmethod
    def get_current(cls) -> 'SimSetup':
        """
        获取当前正在运行的 Setup 实例。

        Returns:
            SimSetup: 当前激活的实例。

        Raises:
            RuntimeError: 如果当前没有激活的实例。
        """
        if cls._current_setup is None:
            raise RuntimeError("当前没有激活的仿真设置。")
        return cls._current_setup

    @abstractmethod
    def setup(self) -> None:
        """
        [抽象方法] 核心配置入口。

        子类必须实现此方法，并在其中执行以下操作：
        1. 调用 self.set_params() 定义参数。
        2. 调用 self.set_export_options() 定义导出内容。
        3. (可选) 实例化 Designer: self.designer = MyDesigner(...)
        """
        pass

    def _validate_export_options(self) -> None:
        """
        [内部方法] 校验导出选项的合法性。

        强制要求：必须显式设置导出选项，不能为空。
        
        Raises:
            RuntimeError: 如果未设置导出选项。
        """
        if not self.export_options:
            raise RuntimeError(
                "配置错误：未设置导出选项 (export_options)。"
                "请在 setup() 方法中调用 self.set_export_options(...)。"
            )
            
        logger.debug(f"导出选项校验通过: {self.export_options}")

    def set_params(self, **kwargs) -> None:
        """
        设置仿真参数。

        Args:
            **kwargs: 任意数量的关键字参数，键为参数名，值为参数值。
        """
        self.sim_params.update(kwargs)
        # 同时设置为实例属性，方便代码阅读（如 self.frequency）
        for k, v in kwargs.items():
            setattr(self, k, v)
            
        logger.debug(f"设置参数: {list(kwargs.keys())}")

    def set_sweep_params(self, **kwargs) -> None:
        """
        设置扫描参数。

        该方法支持两种参数传入模式，框架会自动识别：
        1. 直接样本模式 (List[Dict]): 传入已经生成的样本列表（如 LHS 采样结果）。
        2. 全排列模式 (Dict[List]): 传入参数的取值范围，框架将自动生成笛卡尔积。

        Args:
            **kwargs: 
                - 模式 A: 单个关键字参数 `samples`，值为 List[Dict]。
                  例如: `samples=[{"W": 1, "L": 2}, {"W": 2, "L": 3}]`
                - 模式 B: 多个关键字参数，值为 List[Any]。
                  例如: `W=[1, 2], L=[3, 4]`

        Raises:
            ValueError: 参数为空，或直接样本模式下传入了多余参数。
            TypeError: 全排列模式下，参数值不是列表或元组。
        """
        # --- 1. 基础校验 ---
        if not kwargs:
            raise ValueError("set_sweep_params 接收到的参数为空。")
        
        # --- 2. 模式识别与分发 ---
        # 获取第一个参数的 key 和 value 用于类型判断
        first_key = next(iter(kwargs))
        first_val = kwargs[first_key]
        
        # 判断是否为“直接样本模式”
        # 条件：值是列表，且列表的第一个元素是字典
        is_direct_list_mode = (
            isinstance(first_val, list) and 
            len(first_val) > 0 and 
            isinstance(first_val[0], dict)
        )

        if is_direct_list_mode:
            # ==========================================
            # 模式 A: 直接样本列表 (例如 LHS 采样结果)
            # ==========================================
            if len(kwargs) != 1:
                raise ValueError("直接样本模式下，只能传入一个名为 'samples' 的参数。")
            
            # 直接将列表赋值给 sweep_params
            self.sweep_params = first_val 
            self.simulation_mode = SimulationMode.PARAMETRIC_MODELING
            
            logger.info(f"已注册直接样本列表，共 {len(first_val)} 个任务。")
            
        else:
            # ==========================================
            # 模式 B: 全排列字典模式 (原有逻辑)
            # ==========================================
            processed_kwargs: Dict[str, List[Any]] = {} 
            
            for key, val in kwargs.items():
                # 类型检查
                if not isinstance(val, (list, tuple)):
                    raise TypeError(f"扫描参数 '{key}' 的值必须是列表或元组，当前为: {type(val)}")
                
                if len(val) == 0:
                    raise ValueError(f"扫描参数 '{key}' 的值为空列表。请至少提供一个扫描点。")
                
                # 浮点数精度处理 (保留3位小数)
                cleaned_val = [round(x, 3) if isinstance(x, float) else x for x in val]
                processed_kwargs[key] = cleaned_val

            self.simulation_mode = SimulationMode.PARAMETRIC_MODELING
            self.sweep_params = processed_kwargs # 存储为字典
            
            # 更新 sim_params 的初始值（取每个参数列表的第一个值）
            # 这保证了 sim_params 始终是标量，供 Designer 建模使用
            for key, val_list in processed_kwargs.items():
                self.sim_params[key] = val_list[0]
                
            logger.info(f"已注册扫描参数字典: {list(processed_kwargs.keys())}")

    def set_export_options(self, *options: str) -> None:
        """
        设置结果导出选项。

        Args:
            *options: 导出类型字符串。
                      支持: "s_parameters", "s_floquet", "realized_gain", "farfield"

        Example:
            self.set_export_options("s_parameters", "s_floquet")
        """
        # 更新支持列表
        valid_options = {"s_parameters", "s_floquet"}
        
        # 验证选项的有效性
        for opt in options:
            if opt not in valid_options:
                logger.warning(f"未知的导出选项: {opt}。当前仅支持: {valid_options}")
        
        # 过滤掉无效选项后赋值
        self.export_options = [opt for opt in options if opt in valid_options]
        
        logger.info(f"已配置导出选项: {self.export_options}")
    
    def set_output_dir(self, output_dir: str) -> None:
        """
        设置结果输出目录路径。

        Args:
            output_dir (str): 输出目录的绝对或相对路径。如果不存在将被创建。
        """
        try:
            os.makedirs(output_dir, exist_ok=True)
            self.output_dir = output_dir
            logger.info(f"已设置输出目录: {self.output_dir}")
        except OSError as e:
            logger.warning(f"无法创建输出目录 '{output_dir}': {e}. output_dir 属性将保持为 None。")

    def get_designer(self) -> Optional['Designer']:
        """
        获取当前配置指定的 Designer 实例。
        
        Runner 将直接拿这个实例注入到 Flow 中。

        Returns:
            Optional['Designer']: Designer 实例，如果未设置则返回 None。
        """
        return self.designer
    
    def set_project_file(self, file_path: str) -> None:
        """
        设置关联的工程文件路径。

        在参数扫描模式下，Runner 将打开此文件作为模板进行修改和仿真。

        Args:
            file_path (str): 文件的绝对或相对路径。

        Raises:
            FileNotFoundError: 如果指定的文件不存在。
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"指定的工程文件不存在: {file_path}")
        
        # 保存绝对路径，防止后续工作目录切换导致路径失效
        self.file_path = os.path.abspath(file_path)
        logger.info(f"已关联工程文件: {self.file_path}")

    def to_dict(self) -> Dict[str, Any]:
        """
        将配置对象序列化为字典。

        该方法主要用于多进程环境，将配置信息传递给子进程。
        它只包含基本数据类型，排除了不可序列化的对象（如 Designer）。

        Returns:
            Dict[str, Any]: 包含所有关键配置的字典。
        """
        return {
            "sim_params": self.sim_params,
            "sweep_params": self.sweep_params,
            "export_options": self.export_options,
            "file_path": self.file_path,
            "output_dir": self.output_dir,
            "simulation_mode": self.simulation_mode,
            "run_mode": self.run_mode
        }