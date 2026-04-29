"""
port.py
负责 CST 项目的端口定义。
"""

# 这个文件没有实际用处，存放了 CST VBA 代码的一些注释。

class CSTPort:
    """
    CST 端口定义模块
    职责：通过注入的 CSTBase 实例定义和注册材料。
    """

    def __init__(self, vba):
        """
        初始化材料管理器
        Args:
            vba: CSTVBA 实例 (依赖注入)
        """
        self.vba = vba

    def create_port(self, Xrange, Yrange, Zrange):
        """
        创建端口，坐标通过参数传入
        Args:
            x_range: tuple, (x_min, x_max) 例如 ("-10*substrate_height-feed_line_width/2", "10*substrate_height+feed_line_width/2")
            y_range: tuple, (y_min, y_max) 例如 ("patch_length/2+matching_line_length+feed_line_length", "patch_length/2+matching_line_length+feed_line_length")
            z_range: tuple, (z_min, z_max) 例如 ("-1*substrate_height", "9*substrate_height")
        """
        vba_code = f"""
        With Port
            .Reset
            .PortNumber "1"
            .NumberOfModes "1"
            .AdjustPolarization False
            .PolarizationAngle "0.0"
            .ReferencePlaneDistance "0"
            .TextSize "50"
            .Coordinates "Free"
            .Orientation "ymax"
            .PortOnBound "False"
            .ClipPickedPortToBound "False"
            .Xrange "{Xrange[0]}", "{Xrange[1]}"
            .Yrange "{Yrange[0]}", "{Yrange[1]}"
            .Zrange "{Zrange[0]}", "{Zrange[1]}"
            .XrangeAdd "0.0", "0.0"
            .YrangeAdd "0.0", "0.0"
            .ZrangeAdd "0.0", "0.0"
            .SingleEnded "False"
            .Create
        End With
        """
        self.vba.to_cst_history(vba_code, "Define Port")

   