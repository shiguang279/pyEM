from src.core.data_saver import HDF5Saver


# 替换为你的实际文件路径
file_path = "E:\\pyEM\\output\\results.h5"

HDF5Saver.display_structure(file_path)

from src.core.data_plotter import DataPlotter

plotter = DataPlotter()

plotter.plot_s_floquet(file_path)
