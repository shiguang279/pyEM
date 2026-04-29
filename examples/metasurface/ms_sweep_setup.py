"""
ms_setup.py

超表面专用配置器
"""
import numpy as np
from pathlib import Path
from src.core.sim_setup import SimSetup
from src.utils.logger import logger

class MSSweepSetup(SimSetup):

    def setup(self) -> None:

        logger.info(">>> 正在执行 超表面 扫描 Setup 配置...")

        self.template_path = str(Path("E:/pyEM/output/rect.cst"))

        # 设置并行数
        self.num_workers = 4

        # 设置扫描参数
        self.set_sweep_params(
            W=np.linspace(2, 8, 24).tolist()  # 扫描变量 W (宽度)，从 2 到 8
        )

        self.set_export_options("s_floquet")

        logger.info(">>> 超表面扫描设置完成。")