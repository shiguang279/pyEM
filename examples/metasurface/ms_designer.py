"""
ms_designer.py

超表面结构构建器 (架构层)
职责：
    1. 定义超表面的物理堆叠结构 (介质、接地、金属厚度)。
    2. 计算全局 Z 轴坐标。
    3. 协调单元 (Cells) 的录制与阵列 (Array) 的生成。
"""

from .ms_cells import MSCells
from src.core.designer import Designer
from src.core.sim_setup import SimSetup
from src.utils.logger import logger

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .ms_setup import MSSetup

class MSDesigner(Designer):
    """
    超表面顶层架构设计器。
    
    继承自 Designer，利用模板方法模式控制建模流程。
    """

    def __init__(self, cells: MSCells, design_name: str):
        """
        初始化架构设计器。
        
        Args:
            cells (MSCells): 单元设计器实例，包含具体的单元几何定义。
            design_name (str): 设计项目的名称标识。
        """
        super().__init__()
        
        self.cells = cells

        self.design_name = design_name

        setup: 'MSSetup' = SimSetup.get_current()
        
        # 现在可以直接访问 MSSetup 的专属属性，IDE 也会有代码提示
        self.ground_thickness = setup.ground_thickness
        self.sub_height = setup.sub_height
        self.unit_size = setup.unit_size



    def design(self) -> None:
        """
        [模板方法实现] 主入口：执行完整的超表面构建流程。
        
        流程：
            1. 计算 Z 轴坐标 -> 2. 构建环境 (介质/接地) -> 3. 录制单元 -> 4. 实例化阵列
        """
        logger.info(f'>>> [MSStructure] 开始构建超表面架构: {self.design_name}...')

        unit_name = f"design_{self.design_name}"
        
        try:

            # 2. 构建基板 (在阵列外部构建)
            self._build_stackup()

            # 3. 录制单元蓝图
            logger.debug(f'正在录制单元蓝图: {unit_name}')
            self.structure.start_unit_definition(unit_name)

            # 4. 委托 Cells 绘制具体几何
            if hasattr(self.cells, unit_name):
                # 调用 cells 的方法，并传入当前的 structure 实例
                # 例如：self.cells.design_rect(self.structure)
                getattr(self.cells, unit_name)(self.structure)
            else:
                raise AttributeError(f"MSCells 中未找到单元定义方法: {unit_name}")
            
        finally:
            # 无论绘制是否成功，必须结束定义
            self.structure.end_unit_definition()

        # 5. 实例化阵列
        self._build_unit_array(unit_name)
        
        logger.info('>>> [MSStructure] 超表面构建完成。')

    def _build_stackup(self) -> None:
        """
        构建接地面和介质基板。
        注意：这些结构通常在阵列单元之外独立构建，或者作为背景层。
        """
        
        z_gnd_bottom = 0.0

        # --- 1. 构建接地层 (Ground Plane) ---
        self.structure.create_brick(
            name="Ground",
            material="PEC", # 理想电导体
            Xrange=["-unit_size / 2.0", "unit_size / 2.0"],
            Yrange=["-unit_size / 2.0", "unit_size / 2.0"],
            Zrange=[z_gnd_bottom, "ground_thickness"], 
            color=(100, 100, 100)
        )
        logger.info(f'   [Stackup] Ground (PEC, t={self.ground_thickness:.3f} mm)')

        # --- 2. 构建介质基板 (Substrate) ---
        self.structure.create_brick(
            name="Substrate",
            material="FR4",
            Xrange=["-unit_size / 2.0", "unit_size / 2.0"],
            Yrange=["-unit_size / 2.0", "unit_size / 2.0"],
            Zrange=["ground_thickness", "ground_thickness + sub_height"],          
            color=(0, 255, 255) # Cyan
        )
        logger.info(f'   [Stackup] Substrate (h={self.sub_height:.1f} mm)')

    def _build_unit_array(self, unit_name: str) -> None:
        """
        构建单元阵列。
        调用 ArrayStructure 将录制好的蓝图实例化。
        """
        # 这里演示 1x1 阵列，实际应用中 matrix 可以是 NxM
        matrix = [[1]] 
        
        self.array_structure.create_array(
            structure=self.structure,     # 传入 Structure 实例，用于执行构建
            unit_name=unit_name,          # 蓝图名称
            matrix=matrix,                # 阵列规模
            pitch_u=self.unit_size,       # U向周期
            pitch_v=self.unit_size,       # V向周期
            plane='xy',                   # 阵列平面
            alignment='center'            # 对齐方式
        )
        logger.info(f"   [Array] 单元阵列实例化完成: {unit_name} (Size: {len(matrix)}x{len(matrix[0])})")