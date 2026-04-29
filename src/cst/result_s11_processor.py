# result_s11_processor.py
import numpy as np
from typing import Tuple, List, Dict
import cst.results as cstr
from .app import CSTBase
from ..utils.logger import logger

class CSTS11Processor(CSTBase):
    """CST S11 后处理模块 (仅提取第一组仿真数据，非兼容版本)"""

    def extract_s11(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        提取第一组仿真 (Run ID 1) 的 S11 数据
        
        Returns:
            freq_data (np.ndarray): 频率数组 (1D)
            s11_db (np.ndarray): S11 数组 (1D)
        """
        try:
            result_prj = cstr.ProjectFile(self.project.filename(), allow_interactive=True)
            # 获取所有 Run ID (跳过第一个)
            # Exclude the first entry (the first entry is "Current Run", 
            # which appears as "Current Run" in the CST GUI under 3D -> Result Navigator).
            run_ids = result_prj.get_3d().get_all_run_ids()[1:] 
            
            if not run_ids:
                logger.error("未找到仿真结果")
                raise ValueError("No simulation results found")

            # --- 修改点：仅取第一个 Run ID (索引 0) ---
            target_run_id = run_ids[0]
            logger.info(f"正在提取仿真数据 | Run ID: {target_run_id} (仅提取第一组)")

            # 获取结果项
            item = result_prj.get_3d().get_result_item(
                "1D Results\\S-Parameters\\S1,1", 
                run_id=target_run_id
            )
            
            if item is None:
                logger.error("无法获取 S11 结果项，请检查结果路径是否正确")
                raise ValueError("S11 result item is None")

            # 数据处理
            freq_data = np.asarray(item.get_xdata())
            s11_linear = np.asarray(item.get_ydata())
            s11_db = 20 * np.log10(np.abs(s11_linear))
            
            # --- 新增输出信息 ---
            logger.info(f"S11 数据提取完成 | 数据点数: {len(freq_data)} | "
                       f"频率范围: {freq_data[0]:.3f} - {freq_data[-1]:.3f} GHz")
            
            return freq_data, s11_db
            
        except Exception as e:
            logger.error(f"S11 Extraction Failed: {e}")
            raise

    def compute_s11_bandwidth(self, freq_data: np.ndarray, s11_data: np.ndarray, threshold_db: float = -10.0) -> Dict:
        """
        计算 S11 带宽 (输入为一维数据)
        
        Args:
            freq_data (np.ndarray): 频率轴数据 (1D)
            s11_data (np.ndarray): S11 数据 (1D)
            threshold_db (float): S11 阈值，默认 -10 dB

        Returns:
            Dict: 包含带宽信息的字典 (非列表，因为仅有一组数据)
        """
        # 由于只有一组数据，不需要外层列表
        result = {
            "run_index": 0,
            "bands": []
        }

        mask = s11_data < threshold_db
        
        if not np.any(mask):
            logger.warning(f"未检测到满足 S11 < {threshold_db} dB 的频段")
            return result

        # 寻找连续区间
        diff = np.diff(mask.astype(int))
        start_indices = np.where(diff == 1)[0] + 1
        end_indices = np.where(diff == -1)[0]

        # 处理边界
        if mask[0]:
            start_indices = np.insert(start_indices, 0, 0)
        if mask[-1]:
            end_indices = np.append(end_indices, len(mask) - 1)

        total_points = len(s11_data)
        total_points_below_threshold = np.sum(mask)
        overall_percentage = (total_points_below_threshold / total_points) * 100.0

        for start_idx, end_idx in zip(start_indices, end_indices):
            if end_idx > start_idx:
                start_freq = float(freq_data[start_idx])
                end_freq = float(freq_data[end_idx])
                bandwidth = end_freq - start_freq
                
                band_info = {
                    "start_freq": start_freq,
                    "end_freq": end_freq,
                    "bandwidth": bandwidth,
                    "percentage_in_band": overall_percentage, # 整体满足率
                    "start_idx": int(start_idx),
                    "end_idx": int(end_idx)
                }
                result["bands"].append(band_info)
                logger.info(
                    f"检测到有效频带 | "
                    f"[{start_freq:.3f} - {end_freq:.3f}] GHz | "
                    f"带宽: {bandwidth:.3f} GHz | "
                    f"整体满足率: {overall_percentage:.1f}%"
                )

        return result
    
    def extract_s11_bandwidth(self, threshold_db: float = -10.0) -> Tuple[np.ndarray, np.ndarray, List[dict]]:
        """
        提取 S11 结果数据并计算带宽

        Returns:
            freq_data (np.ndarray): 频率数据 (GHz)
            s11_data_matrix (np.ndarray): S11 数据矩阵 (N_runs, N_freq)
            bandwidth_results (List[dict]): 详细的带宽结果列表
        """
        try:
            freq_data, s11_data_matrix = self.extract_s11() 
            
            # 传入矩阵和阈值
            bandwidth_results = self.compute_s11_bandwidth(freq_data, s11_data_matrix, threshold_db=threshold_db)

            return freq_data, s11_data_matrix, bandwidth_results

        except Exception as e:
            logger.error("结果提取失败", exc_info=True)