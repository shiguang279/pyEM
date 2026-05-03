# -*- coding: utf-8 -*-
"""
通用仿真接口定义
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Dict, Any
from src.utils.logger import logger

class SimDesignEnv(ABC):
    """
    通用仿真设计环境基类。
    """
    def __init__(self, quiet: bool = True):
        self.quiet = quiet
        self._pid: Optional[int] = None
        self._is_initialized = False
        logger.debug(f"通用仿真环境 {self.__class__.__name__} 已实例化 (未启动)")

    @property
    def pid(self) -> Optional[int]:
        return self._pid
    
    @pid.setter 
    def pid(self, value: Optional[int]):
        self._pid = value

    @abstractmethod
    def initialize(self, **kwargs) -> bool:
        """
        抽象方法：具体的初始化逻辑（启动或连接）放在这里。
        子类必须重写此方法。
        """
        pass

    @abstractmethod
    def close_env(self, force_kill: bool = True, timeout: int = 15) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_env(force_kill=True)
        return False


class SimProject(ABC):
    """
    通用仿真项目基类 (父类)。
    职责：管理项目文件的打开、保存、仿真运行及结果处理。
    """
    def __init__(self, design_env: SimDesignEnv):
        self.design_env = design_env
        self._project_handle = None
        self._file_path: Optional[Path] = None
        logger.debug(f"Project Context 初始化，关联环境 PID: {design_env.pid}")

    @property
    def file_path(self) -> Optional[Path]:
        return self._file_path

    @abstractmethod
    def open(self, file_path: str) -> None:
        """抽象方法：打开项目"""
        pass

    @abstractmethod
    def save(self, prj_file: str, include_results: bool = False) -> None:
        """抽象方法：保存项目"""
        pass

    @abstractmethod
    def run_solver(self) -> None:
        """抽象方法：运行求解器"""
        pass

    def run_simulation(self, prj_file: str = None) -> Dict[str, Any]:
        """
        通用仿真流程模板 (Template Method)。
        子类可以重写具体步骤，但流程由父类控制。
        
        清理以前的仿真结果 > 保存 > 求解 > 保存
        """
        if not prj_file:
            raise ValueError("未指定工程路径")

        try:
            logger.info(f"开始仿真流程: {prj_file}")
            self._pre_run_cleanup()  # 清理以前的仿真结果
            self.save(prj_file, include_results=False)
            self.run_solver()
            self.save(prj_file, include_results=True)
            return {"status": "success", "prj_file": prj_file}
        except Exception as e:
            logger.error(f"仿真流程失败: {e}")
            return {"status": "error", "message": str(e)}

    def _pre_run_cleanup(self):
        """
        仿真前的清理钩子。
        子类可以重写此方法。
        """
        logger.debug("执行通用仿真前清理 (无操作)")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    @abstractmethod
    def close(self) -> None:
        """抽象方法：关闭项目"""
        pass