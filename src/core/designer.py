# -*- coding: utf-8 -*-
"""
模块：designer.py
描述：设计器抽象基类，定义几何建模的标准流程。

该模块定义了建模器的核心接口，采用模板方法模式，
将建模流程的控制权保留在基类中，而将具体的几何构建细节交由子类实现。
"""

from abc import ABC, abstractmethod
from typing import Tuple, Optional
from src.utils.logger import logger
from src.core.structure import Structure
from src.core.array_structure import ArrayStructure

# 定义颜色类型别名 (R, G, B) 0-255
ColorRGB = Tuple[int, int, int]


class Designer(ABC):
    """
    设计器抽象基类。

    核心职责：
        1. 定义建模流程：通过模板方法 execute_design() 控制记录与执行的顺序。
        2. 持有 Structure 实例：子类通过 self.structure 调用几何构建方法。
        3. 解耦：Designer 不直接依赖 IBuilder，仅依赖 Structure。

    设计模式：
        模板方法模式：execute_design() 定义了算法骨架，子类只需实现 design() 细节。
    """

    # ================= 常用颜色定义 (0-255 格式) =================
    COLOR_GOLD: ColorRGB = (255, 255, 0)
    COLOR_CYAN: ColorRGB = (0, 255, 255)
    COLOR_RED: ColorRGB = (255, 0, 0)
    COLOR_GREEN: ColorRGB = (0, 255, 0)
    COLOR_BLUE: ColorRGB = (0, 0, 255)
    COLOR_WHITE: ColorRGB = (255, 255, 255)
    COLOR_BLACK: ColorRGB = (0, 0, 0)
    COLOR_GRAY: ColorRGB = (128, 128, 128)
    COLOR_ORANGE: ColorRGB = (255, 165, 0)
    COLOR_PURPLE: ColorRGB = (128, 0, 128)

    def __init__(self) -> None:
        """
        初始化设计器。
        """
        self._structure: Optional[Structure] = None
        self._array_structure: Optional[ArrayStructure] = None
        logger.debug(f"Designer initialized: {self.__class__.__name__}")

    def set_structure(self, structure: Structure) -> None:
        """
        接收由 SimFlow 准备好的 Structure。
        
        Args:
            structure (Structure): 已经初始化好的 Structure 实例。
        """
        if structure is None:
            raise ValueError("注入的 Structure 不能为空")
            
        self._structure = structure
        # ArrayStructure 通常是无状态的或者是辅助工具，可以在这里初始化
        self._array_structure = ArrayStructure()
        
        logger.debug(f"Structure received and initialized in Designer: {type(structure).__name__}")

    def execute_design(self) -> None:
        """
        主入口方法：执行几何结构建模设计流程。

        流程步骤：
            1. 检查 Structure 是否已初始化。
            2. 调用子类的 design() 方法记录几何操作。
            3. 调用 structure.execute() 统一提交并执行所有缓存的操作。

        Raises:
            RuntimeError: 如果 Structure 未初始化（即未调用 set_builder）。
        """
        if self._structure is None:
            raise RuntimeError("Structure 未初始化！请在调用 execute_design 前使用 set_builder()。")

        logger.info(f"Starting design process: {self.__class__.__name__}")
        
        # 阶段 1: 记录几何操作 (子类调用 self.structure.xxx)
        logger.info(f"Recording geometric operations...")

        try:
            self.design()
        except Exception as e:
            logger.error(f"Design recording failed: {e}")
            raise e
        
        # 阶段 2: 统一执行
        logger.info(f"Executing cached operations via structure...")
        # 调用 Structure 的 execute，由 Structure 内部去调用 Builder
        # ArrayStructure 生成的几何体也是通过 Structure 添加的，所以只需 execute Structure 即可
        self._structure.execute()
        
        logger.info(f"Design process completed: {self.__class__.__name__}")

    @property
    def structure(self) -> Structure:
        """
        提供对 Structure 的只读访问。

        子类通过此属性调用 create_brick, extrude_face 等几何构建方法。

        Returns:
            Structure: 当前设计器持有的 Structure 实例。

        Raises:
            RuntimeError: 如果 Structure 尚未初始化。
        """
        if self._structure is None:
            raise RuntimeError("Structure 尚未初始化，请先调用 set_builder()")
        return self._structure
    
    @property
    def array_structure(self) -> ArrayStructure:
        """
        提供对 ArrayStructure 的只读访问。
        用于阵列排布和实例化。
        """
        if self._array_structure is None:
            raise RuntimeError("ArrayStructure 尚未初始化，请先调用 set_builder()")
        return self._array_structure

    @abstractmethod
    def design(self) -> None:
        """
        [抽象方法] 几何结构建模操作。

        子类必须实现此方法以定义具体的几何形状、尺寸及位置。
        在实现中，可以使用 self.structure 进行单元定义，
        也可以使用 self.array_structure 进行阵列生成。

        示例:
            # 录制单元
            self.structure.start_unit_definition("Unit1")
            self.structure.create_brick(...)
            self.structure.end_unit_definition()
            
            # 生成阵列
            self.array_structure.create_array(...)

        Raises:
            NotImplementedError: 如果子类未实现此方法。
        """
        raise NotImplementedError("Subclasses must implement the design() method")