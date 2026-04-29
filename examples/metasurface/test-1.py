from src.core.data_plotter import DataPlotter
import matplotlib.pyplot as plt

h5_path = "E:\\pyEM\\output\\results.h5" # 请替换为你实际的输出路径

# ==========================================
# 2. 读取 HDF5 并绘图
# ==========================================
print("正在加载数据准备绘图...")

plotter = DataPlotter() # 实例化修改后的 DataPlotter

# 参数扫描模式绘图 - S 参数对比
# 这会加载所有 sample_id，并将它们的 S11 曲线画在同一张图上进行比较
plotter.plot_s_parameters(file_path=h5_path, mode="comparison", save_path="output/param_sweep_comparison.png")

# 如果你想查看某个特定样本的详细信息，可以这样做
# plotter.plot_s_parameters(file_path=h5_path, mode="detail", target_samples=["worker_0_param_W_9.890000"]) # 示例 ID

plt.show() # 显示所有图表