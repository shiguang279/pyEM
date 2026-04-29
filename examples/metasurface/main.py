import numpy as np
from src.core.run_simulation import run_simulation
from .ms_setup import MSSetup  
from .ms_sweep_setup import MSSweepSetup
import h5py

from src.core.data_plotter import DataPlotter

import matplotlib.pyplot as plt

# ===== 参数扫描示例 =====
# 启动扫描仿真
result = run_simulation(setup_class=MSSweepSetup)

if result:

    result_file = result.get('result_file')

    print("正在加载数据准备绘图...")

    # ==========================================
    # 2. 读取 HDF5 并绘图
    # ==========================================
    plotter = DataPlotter()

    # 参数扫描模式绘图 - S 参数对比
    plotter.plot_s_floquet(file_path=result_file)

    # 显示所有图表
    plt.show()

else:
    print("仿真运行失败或未返回成功状态。")
    print(result)