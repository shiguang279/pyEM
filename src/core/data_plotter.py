# -*- coding: utf-8 -*-
import os
from matplotlib import cm, colors as mcolors, ticker
import numpy as np
import h5py
import random
from typing import List, Optional, Union, Dict, Any
import matplotlib
from src.utils.logger import logger
from datetime import datetime

# --- 1. 强制设置后端 ---
matplotlib.use('TkAgg') 
import matplotlib.pyplot as plt

class DataPlotter:
    """通用仿真数据绘图工具类"""
    
    def __init__(self):
        # --- 2. 全局设置 ---
        plt.rcParams['font.family'] = 'Times New Roman'
        plt.rcParams['font.size'] = 12
        plt.rcParams['figure.figsize'] = (14, 10)
        plt.rcParams['axes.unicode_minus'] = False

    def _load_data(self, file_path: str) -> Optional[List[Dict[str, Any]]]:
        """
        通用数据加载接口
        返回一个列表，包含所有样本的数据字典
        """
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()
        all_samples_data = []
        
        try:
            if ext in ['.h5', '.hdf5']:
                with h5py.File(file_path, 'r') as f:
                    # 遍历顶层组
                    for group_name in f.keys():
                        sample_data = {}
                        grp = f[group_name]
                        
                        # 递归读取数据
                        self._load_group_recursively(grp, sample_data)
                        
                        if sample_data:
                            all_samples_data.append(sample_data)
                
                logger.info(f"成功加载 {len(all_samples_data)} 个样本")
                return all_samples_data
            else:
                logger.error(f"暂不支持读取格式: {ext}")
                return None
                
        except Exception as e:
            logger.error(f"数据加载失败: {e}")
            return None

    def _load_group_recursively(self, h5_group: h5py.Group, target_dict: Dict, prefix: str = ""):
        """递归读取 HDF5 组"""
        for name, obj in h5_group.items():
            full_path = f"{prefix}/{name}" if prefix else name
            
            if isinstance(obj, h5py.Dataset):
                data = obj[:]
                if data.dtype.kind in ['S', 'U']:
                    if isinstance(data, np.ndarray):
                        data = np.char.decode(data, 'utf-8')
                    else:
                        data = data.decode('utf-8')
                target_dict[full_path] = data
                
            elif isinstance(obj, h5py.Group):
                self._load_group_recursively(obj, target_dict, prefix=full_path)

    # ============================================================
    # 模块 1: 标准 S 参数绘图
    # ============================================================
    
    def plot_s_parameters(self, file_path: str, indices: Optional[List[int]] = None, save_path: str = None):
        """
        标准 S 参数绘图入口
        """
        # 1. 确定保存路径
        if save_path is None:
            input_dir = os.path.dirname(os.path.abspath(file_path))
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = os.path.join(input_dir, f"{timestamp}_Standard_S11.png")
        else:
            dir_name = os.path.dirname(os.path.abspath(save_path))
            os.makedirs(dir_name, exist_ok=True)

        # 2. 加载数据
        all_data = self._load_data(file_path)
        if not all_data:
            return

        # 3. 筛选标准S参数数据 (查找根目录下的 S11_dB)
        standard_data = []
        for data_dict in all_data:
            if 'S11_dB' in data_dict:
                standard_data.append(data_dict)

        if not standard_data:
            logger.warning("没有找到标准 S 参数数据 (S11_dB)")
            return

        # 4. 根据 indices 筛选数据
        if indices is not None:
            standard_data = [standard_data[i] for i in indices if i < len(standard_data)]
            logger.info(f"筛选后绘制 {len(standard_data)} 组数据")

        # 5. 绘图
        self._plot_standard_s_params(standard_data, save_path)

    def _plot_standard_s_params(self, all_data: List[Dict[str, Any]], save_path: str):
        """绘制标准 S 参数图表"""
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))
        plt.subplots_adjust(hspace=0.3, right=0.75)

        for idx, data_dict in enumerate(all_data):
            # 生成图例标签
            param_labels = []
            # 直接获取 params 组
            params_group = data_dict.get('params')
            
            # 确保它是一个字典（组），然后遍历
            if isinstance(params_group, dict):
                for p_name, p_val in params_group.items():
                    # 提取数值：如果是 numpy 数组则取第一个元素，否则直接取值
                    if isinstance(p_val, np.ndarray):
                        val_num = p_val.flatten()[0]
                    else:
                        val_num = p_val
                    
                    param_labels.append(f"{p_name}={float(val_num):.2f}")
            
            # 3. 组合标签
            label = ", ".join(param_labels) if param_labels else f"Sample_{idx}"

            # 获取数据
            freq = data_dict.get('freq')
            s11_mag = data_dict.get('S11_dB')
            s11_phase = data_dict.get('S11_Phase')

            if freq is None or s11_mag is None:
                continue

            # 统一长度
            min_len = min(len(freq), len(s11_mag), len(s11_phase) if s11_phase is not None else len(freq))
            f_plot = freq[:min_len]

            # 绘图
            ax1.plot(f_plot, s11_mag[:min_len], label=label)
            if s11_phase is not None:
                ax2.plot(f_plot, s11_phase[:min_len], label=label)

        # 格式化
        ax1.set_ylabel("Magnitude (dB)")
        ax1.set_title("Standard S11 Magnitude")
        ax1.grid(True)
        ax1.legend(loc='center left', bbox_to_anchor=(1, 0.5))

        ax2.set_xlabel("Frequency (GHz)")
        ax2.set_ylabel("Phase (deg)")
        ax2.set_title("Standard S11 Phase")
        ax2.grid(True)
        ax2.legend(loc='center left', bbox_to_anchor=(1, 0.5))

        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        logger.info(f"标准S参数图已保存: {save_path}")
        plt.show()

    # ============================================================
    # 模块 2: Floquet S 参数绘图 (2x2 布局)
    # ============================================================

    def plot_s_floquet(self, file_path: str, indices: Optional[List[int]] = None, save_path: str = None):
        """
        Floquet S 参数绘图入口
        """
        # 1. 确定保存路径
        if save_path is None:
            input_dir = os.path.dirname(os.path.abspath(file_path))
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = os.path.join(input_dir, f"{timestamp}_Floquet_S11_2x2.png")
        else:
            dir_name = os.path.dirname(os.path.abspath(save_path))
            os.makedirs(dir_name, exist_ok=True)

        # 2. 加载数据
        all_data = self._load_data(file_path)
        if not all_data:
            return

        # 3. 筛选Floquet数据 (查找 s_floquet/ 子目录下的数据)
        floquet_data = []
        for data_dict in all_data:
            # 修改点：检查带路径的键名
            if 's_floquet/S11_M1_mag' in data_dict or 's_floquet/S11_M2_mag' in data_dict:
                floquet_data.append(data_dict)

        if not floquet_data:
            logger.warning("没有找到 Floquet S 参数数据 (检查 s_floquet/ 路径)")
            return

        # 4. 根据 indices 筛选数据
        if indices is not None:
            floquet_data = [floquet_data[i] for i in indices if i < len(floquet_data)]
            logger.info(f"筛选后绘制 {len(floquet_data)} 组数据")

        # 5. 绘图 (2x2)
        self._plot_floquet_s_params_2x2(floquet_data, save_path)

    def _plot_floquet_s_params_2x2(self, all_data: List[Dict[str, Any]], save_path: str):
        print("\n" + "="*60)
        print("[DEBUG] ENTERING _plot_floquet_s_params_2x2")
        print(f"[DEBUG] len(all_data) = {len(all_data)}")
        for i, d in enumerate(all_data):
            param_keys = [k for k in d.keys() if k.startswith('params/')]
            print(f"[DEBUG] Sample {i}: param_keys = {param_keys}")
        print("="*60 + "\n")
        
        """绘制 Floquet S 参数图表 (2x2 布局) - 适配现有键结构"""
        if not all_data:
            logger.warning("没有数据可供绘图")
            return

        fig, axs = plt.subplots(2, 2, figsize=(18, 14))
        plt.subplots_adjust(hspace=0.25, wspace=0.2, top=0.93)
        plt.suptitle("Floquet S-Parameters", fontsize=16, fontweight='bold')

        modes = [('S11_M1', 0), ('S11_M2', 1)]

        for mode_prefix, col_idx in modes:
            mag_key = f's_floquet/{mode_prefix}_mag'
            phase_key = f's_floquet/{mode_prefix}_phase'

            ax_mag = axs[0, col_idx]
            ax_phase = axs[1, col_idx]

            for idx, data_dict in enumerate(all_data):
                color = plt.cm.tab10(idx % 10)

                param_labels = []
                
                # 遍历所有以 'params/' 开头的键
                for key in data_dict.keys():
                    if key.startswith('params/'):
                        # 分离参数名：'params/W' -> 'W'
                        param_name = key.split('/')[-1]
                        param_value = data_dict[key]
                        
                        # 提取数值（兼容 numpy array 和标量）
                        if isinstance(param_value, np.ndarray):
                            if param_value.size == 1:
                                val = float(param_value.item())
                            else:
                                val = float(param_value[0])  # 取第一个元素
                        else:
                            # 已经是标量
                            val = float(param_value)
                        
                        param_labels.append(f"{param_name}={val:.2f}")

                # 生成标签文本
                label_text = ", ".join(param_labels) if param_labels else f"Sample_{idx}"
                print(f"[DEBUG] Sample {idx} -> Label: {label_text}")  # 显示生成的标签

                freq = data_dict.get('s_floquet/freq')
                if freq is None:
                    continue

                if mag_key in data_dict:
                    mag_data = data_dict[mag_key]
                    min_len = min(len(freq), len(mag_data))
                    ax_mag.plot(freq[:min_len], mag_data[:min_len], color=color, label=label_text, linewidth=2)

                if phase_key in data_dict:
                    phase_data = data_dict[phase_key]
                    min_len = min(len(freq), len(phase_data))
                    ax_phase.plot(freq[:min_len], phase_data[:min_len], color=color, label=label_text, linewidth=2)

            ax_mag.set_title(f"Floquet {mode_prefix} Magnitude")
            ax_mag.set_ylabel("Mag (dB)")
            ax_mag.grid(True, alpha=0.3)
            ax_mag.legend(loc='lower left', fontsize=9)

            ax_phase.set_title(f"Floquet {mode_prefix} Phase")
            ax_phase.set_ylabel("Phase (deg)")
            ax_phase.set_xlabel("Frequency (GHz)")
            ax_phase.grid(True, alpha=0.3)
            ax_phase.legend(loc='lower left', fontsize=9)

        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        logger.info(f"Floquet S参数图已保存: {save_path}")
        plt.show()

    # ============================================================
    # 模块 2: 3D 远场绘图 (保持不变)
    # ============================================================

    def load_cst_farfield_h5(self, file_path):
        """
        加载包含远场辐射图案数据的 HDF5 文件。
        严格遵循参考代码的数据处理逻辑：重塑、闭合、计算形状与颜色。
        """
        try:
            with h5py.File(file_path, 'r') as f:
                # --- 1. 数据提取 (严格对应参考代码) ---
                theta = np.array(f["Theta"])
                phi = np.array(f['Phi'])
                # 获取第一个非坐标轴的数据集 (通常是 Directivity 或 Gain)
                data_keys = [key for key in f.keys() if key not in ['Theta', 'Phi']]
                if not data_keys:
                    raise KeyError("HDF5文件中未找到远场数值数据集")
                abs_dir = np.array(f[data_keys[0]])

                # --- 2. 网格形状推断 (严格对应参考代码) ---
                N = len(np.unique(theta))  # Unique theta values (rows)
                M = len(np.unique(phi))    # Unique phi values (cols)

                # --- 3. 数据重塑 (严格对应参考代码) ---
                # 注意：这里假设数据排列顺序适配 (M, N)
                try:
                    theta = theta.reshape(M, N)
                    phi = phi.reshape(M, N)
                    abs_dir = abs_dir.reshape(M, N)
                except ValueError:
                    # 如果数据排列顺序不同，尝试转置 (N, M)
                    print(f"注意：(M,N) 重塑失败，尝试 (N,M) 顺序。")
                    theta = theta.reshape(N, M)
                    phi = phi.reshape(N, M)
                    abs_dir = abs_dir.reshape(N, M)

                # --- 4. 单位转换 (严格对应参考代码) ---
                theta = theta * np.pi / 180  # Convert to radians
                phi = phi * np.pi / 180      # Convert to radians

                # --- 5. 边界闭合处理 (严格对应参考代码) ---
                # Extend phi by duplicating the first row as `phi=360`
                theta = np.vstack([theta, theta[0, :]])
                phi = np.vstack([phi, phi[0, :] + 2 * np.pi])
                abs_dir = np.vstack([abs_dir, abs_dir[0, :]])

                # --- 6. 计算形状与颜色 (严格对应参考代码) ---
                # Convert Abs(Dir.) from linear scale to dBi
                # 注意：参考代码逻辑假设 abs_dir 是线性值
                r_shape = 10 * np.log10(abs_dir) + np.abs(np.min(10 * np.log10(abs_dir)))
                r_cmap = 10 * np.log10(abs_dir)

                # --- 7. 坐标转换 (严格对应参考代码) ---
                # Convert to Cartesian coordinates with scaled radius
                x = r_shape * np.sin(theta) * np.cos(phi)
                y = r_shape * np.sin(theta) * np.sin(phi)
                z = r_shape * np.cos(theta)

                # 返回处理好的数据字典
                return {
                    'x': x,
                    'y': y,
                    'z': z,
                    'r_cmap': r_cmap,
                    'r_shape': r_shape,
                    'max_dBi': np.max(r_cmap)
                }

        except Exception as e:
            print(f"加载文件时出错: {e}")
            return None

    def plot_3d_farfield_from_file(self, file_path):
        """
        从 HDF5 文件读取数据并绘制 3D 远场辐射方向图。
        调用 load_cst_farfield_h5 获取数据，并严格遵循参考代码的绘图逻辑。
        """
        # --- 调用加载函数 ---
        data_dict = self.load_cst_farfield_h5(file_path)
        
        if data_dict is None:
            print("没有数据可供绘图。")
            return

        # --- 验证加载的数据 (关键点) ---
        required_keys = ['x', 'y', 'z', 'r_cmap']
        missing_keys = [key for key in required_keys if key not in data_dict]
        if missing_keys:
            print(f"错误：加载的数据中缺少必要的键: {missing_keys}")
            print(f"实际包含的键: {list(data_dict.keys())}")
            return

        x, y, z, r_cmap = data_dict['x'], data_dict['y'], data_dict['z'], data_dict['r_cmap']

        # 验证数组类型和形状
        if not all(isinstance(arr, np.ndarray) for arr in [x, y, z, r_cmap]):
            print(f"错误：加载的数据中包含非numpy数组: x:{type(x)}, y:{type(y)}, z:{type(z)}, r_cmap:{type(r_cmap)}")
            return

        # 检查形状兼容性 (这是一个简化的检查，实际情况可能更复杂)
        # 通常 x, y, z, r_cmap 应该是形状相似的 2D 网格数组 (例如 MxN)
        expected_shape = x.shape
        if not all(arr.shape == expected_shape for arr in [y, z, r_cmap]):
            print(f"警告：数组形状不完全匹配。期望形状: {expected_shape}, 实际: x:{x.shape}, y:{y.shape}, z:{z.shape}, r_cmap:{r_cmap.shape}")
            # 可以选择继续，但结果可能不理想
            # return # 或者直接返回

        print(f"--- DEBUG: plot_3d_farfield: x/y/z/r_cmap shapes: {x.shape}/{y.shape}/{z.shape}/{r_cmap.shape} ---")
        print(f"--- DEBUG: plot_3d_farfield: r_cmap range: [{np.min(r_cmap):.4f}, {np.max(r_cmap):.4f}] ---")


        # --- 绘图逻辑 (严格对应参考代码) ---
        
        # Normalize colors based on r_cmap
        norm = mcolors.Normalize(vmin=np.min(r_cmap), vmax=np.max(r_cmap))
        color_map = plt.cm.jet(norm(r_cmap))  # Get RGBA values

        # Create 3D Surface Plot
        fig = plt.figure(figsize=(8, 6))
        ax = fig.add_subplot(111, projection='3d')

        # Plot surface with shape determined by r_shape but colors by r_cmap
        # rstride=6, cstride=6
        try:
            surf = ax.plot_surface(x, y, z, 
                                facecolors=color_map, rstride=6, cstride=6)
        except ValueError as e:
            print(f"plot_surface 绘图时出错: {e}")
            print(f"这通常是由于输入数组形状不兼容导致的。请检查 load_cst_farfield_h5 的输出。")
            return

        # Improve visualization
        ax.set_box_aspect([1, 1, 1]) # 优先使用这个
        # ax.set_aspect('equal') # 3D 中可能无效或引起问题，注释掉
        ax.set_xlabel("X")
        ax.set_ylabel("Y")
        ax.set_zlabel("Z")

        # Hide x, y, and z tick marks
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_zticks([])

        # Add a colorbar with more ticks
        mappable = cm.ScalarMappable(norm=norm, cmap=plt.cm.jet)
        mappable.set_array([])  # Empty array needed for colorbar
        cbar = plt.colorbar(mappable, ax=ax, shrink=0.5, aspect=10)

        # Add colorbar label
        cbar.set_label("Directivity (dBi)", fontsize=12)

        # Increase the number of ticks on the colorbar
        cbar.locator = ticker.MaxNLocator(nbins=12)
        cbar.update_ticks()

        # Show interactive surface plot
        plt.title(f'3D Farfield Pattern\n{os.path.basename(file_path)}')
        plt.tight_layout()
        plt.show()