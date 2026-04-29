"""
mf_cells.py

超表面单元设计库 (单元层)
"""

from src.core.structure import Structure

class MSCells:
    """
    超表面单元设计器。
    """

    def __init__(self):
        """
        Args:
            context (MSContext): 上下文对象，包含 Z 轴、材料等全局参数。
        """
        self.default_metal_color = (255, 200, 0)

    def design_rect(self, structure: Structure) -> None:
        """
        设计矩形。
        
        注意：方法名改为 draw_ 开头，以区分 Designer 的 design()。
        必须显式接收 structure 参数。

        Args:
            structure (Structure): 用于执行绘图命令的 Structure 实例。
            W (float): 贴片宽度。
            H (float): 贴片高度。
        """
        # 计算 XY 范围
        x_range = ["-W / 2", "W / 2"]
        y_range = ["H / 2", "-H / 2"]
        z_range = ["ground_thickness + sub_height", 
                   "ground_thickness + sub_height + metal_thickness"]

        # 调用构建函数
        structure.create_brick(
            name='Patch',
            material='PEC',
            Xrange=x_range,
            Yrange=y_range,
            Zrange=z_range,
            color=self.default_metal_color
        )


    def design_circle(self) -> None:

        R = 3.0
    
        # 绘制几何
        self.structure.create_cylinder(
            name='Patch',
            material='PEC',
            r_out=R,    
            r_in=0,          # 实心圆，内径为 0
            xc=0,            # X 中心
            yc=0,            # Y 中心
            Zrange=[self.z_bottom, self.z_top] 
        )

    def design_cross(self, z_substrate_top: float, z_metal_top: float):
        """设计：十字形贴片"""
        aL = 10 
        aW = 2
        # 构建水平臂 (ArmH)
        self.structure.create_brick(
            name='ArmH',
            material='PEC',
            Xrange=[-aL / 2, aL / 2],
            Yrange=[-aW / 2, aW / 2],
            Zrange=[self.z_bottom, self.z_top],
            color=self.default_metal_color
        )

        # 构建垂直臂 (ArmV)
        self.structure.create_brick(
            name='ArmV',
            material='PEC',
            Xrange=[-aW / 2, aW / 2],
            Yrange=[-aL / 2, aL / 2],
            Zrange=[self.z_bottom, self.z_top],
            color=self.default_metal_color
        )

        self.structure.add('ArmH', 'ArmV')

    