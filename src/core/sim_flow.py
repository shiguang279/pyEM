# -*- coding: utf-8 -*-
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, TYPE_CHECKING
from src.utils.logger import logger
from .designer import Designer

if TYPE_CHECKING:
    from .structure import Structure, IBuilder

class SimFlow(ABC):
    """
    仿真工作流抽象基类。
    
    核心职责：
        1. 持有 Builder：通过构造函数接收，作为建模的底层基础。
        2. 管理注入流程：利用持有的 Builder 创建 Structure -> 注入 Designer。
    """

    def __init__(
        self, 
        builder: 'IBuilder',
        design_name: str, 
        output_dir: str = "output"
    ):
        """
        初始化仿真工作流。
        
        Args:
            builder (IBuilder): 底层构建器实例 (由外部 Runner 注入)。
            design_name (str): 设计名称/组件名。
            output_dir (str): 输出目录。
        """
        # 核心依赖：Builder 必须在初始化时提供
        if builder is None:
            raise ValueError("Builder 不能为空")
            
        self.builder = builder
        self.design_name = design_name
        self.output_dir = output_dir
        self.save_path: str = ""
        self.project_name: str = f"{design_name}"
        
        # 运行时组件 (初始为空)
        self.structure: Optional['Structure'] = None
        self._designer: Optional['Designer'] = None

    def inject_designer(self, designer: 'Designer') -> None:
        """
        [核心入口] 注入 Designer 并自动完成环境准备。
        
        流程：
            1. 校验 Designer 类型。
            2. 利用已持有的 self.builder 创建 Structure。
            3. 将 Structure 注入 Designer。
        """
        if not isinstance(designer, Designer):
            raise TypeError(f"类型错误: Designer 必须是 'Designer' 的子类实例。")
        
        logger.info(f"[{self.__class__.__name__}] 开始注入 Designer...")
        
        # 步骤 1: 创建 Structure (直接使用 self.builder)
        logger.info(f"[{self.__class__.__name__}] 正在准备 Structure 资源...")
        self.structure = self._create_structure(self.builder)
        
        # 步骤 2: 注入 Designer
        self._designer = designer
        # 给 Designer 传入 Structure
        self._designer.set_structure(self.structure)

        logger.info(f"[{self.__class__.__name__}] Designer 注入成功，自动建模模块已激活: {designer.__class__.__name__}")

    def _create_structure(self, builder: 'IBuilder') -> 'Structure':
        """
        工厂方法：利用 Builder 创建 Structure。
        
        Args:
            builder: 底层构建器。
        """
        from .structure import Structure
        # 传入 builder 和组件名
        return Structure(builder=builder, component=self.design_name)

    def sync_parameters_to_software(self, params, app_instance: Any = None) -> bool:
        """
        将 sim_params 同步到软件。
        """
        try:
            success = self._apply_parameters_to_software(params, app_instance)
            return success
        except Exception as e:
            logger.error(f"同步参数失败: {e}")
            return False

    @abstractmethod
    def _apply_parameters_to_software(self, params_data: Dict[str, Any], app_instance: Any) -> bool:
        """子类实现具体的参数应用逻辑（如 CST 的 storeParameter）。"""
        pass

    @abstractmethod
    def prepare_save_path(self, project_name: str) -> str:
        """子类实现具体的路径准备逻辑。"""
        pass

    @abstractmethod
    def execute_automated_modeling(self) -> None:
        """
        [自动建模] 执行几何构建。
        
        子类在此处调用 self._designer.execute_design()
        此时 Structure 已经通过 inject_designer 准备好了。
        """
        pass