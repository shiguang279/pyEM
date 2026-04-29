"""
ms_setup.py

超表面专用配置器
"""
from .ms_cells import MSCells
from .ms_designer import MSDesigner
from src.core.sim_setup import SimSetup
from src.utils.logger import logger

class MSSetup(SimSetup):

    def __init__(self):
        
        # 先设置参数
        self.unit_size = 10.0      # 单元周期 P
        self.sub_height = 1.6      # 介质层高度
        self.ground_thickness = 0.0

        # 父类会直接调用 setup()
        super().__init__()

    def setup(self) -> None:
        """
        超表面专用配置入口。
        """
        logger.info(">>> 正在执行 超表面 Setup 配置...")
         # --- 物理参数配置 ---
        # metal_thickness: float = 0.035   # 金属层厚度
        # ground_thickness: float = 0.035  # 接地层厚度
        metal_thickness: float = 0.0

        # --- 1. 定义仿真参数 ---
        self.set_params(
            # Geometry
            P=10.0,              # Unit cell period
            W = 6, 
            H = 6,
            
            # Frequency
            f_min=4.0,           # Min frequency GHz
            f_max=12.0,          # Max frequency GHz
            
            # Substrate material
            sub_eps=4.3,         # Permittivity
            sub_tan=0.025,       # Loss tangent

            unit_size = self.unit_size,
            sub_height = self.sub_height,
            metal_thickness = metal_thickness,
            ground_thickness = self.ground_thickness
        )

        # GUI 界面选择 Boundaries Floquet 端口。
        # 图中点击 Floquet Boundaries... 按钮后出现的对话框。
        # 分别将 Zmin 和 Z_max 修改 Number of Floquet modes = 2
        # 修改为频域仿真，并且 修改 Normalize S-parameter to 50 Ohm

        # --- 2. 实例化 Designer 层级 ---
        
        # A. 实例化单元设计器 (Cells)
        cells = MSCells()
        
        # B. 实例化架构设计器 (MSDesigner)
        # 将 cells 注入到 MSDesigner 中。
        # MSDesigner 负责管理整体的 Stackup 和 Array，并协调 Cells 的调用。

        
        # 内置设计 (Built-in designs):
        #   rect            - 矩形贴片
        #   cross           - 十字形
        #   circle          - 圆形贴片 
        #   ring            - 圆环
        #   srr             - 开口谐振环 (SRR)
        #   bowtie          - 领结形
        #   h_shape         - H形
        #   jerusalem_cross - 耶路撒冷十字
        #   smith_srr       - Smith双SRR (PRL 2000经典)
        #   concentric_rings- 同心矩形环 (Sci.Rep. 2018)

        self.design_name = "rect" # 默认设计名称

        # 在实例化 Designer 时使用 self.design_name
        self.designer = MSDesigner(cells=cells, design_name=self.design_name)
        
        logger.info(">>> 超表面设置完成，Designer 已注册。")