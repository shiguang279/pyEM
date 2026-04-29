# -*- coding: utf-8 -*-
# result_extractor.py
import os
import pandas as pd
import numpy as np
from abc import ABC, abstractmethod
from typing import Dict, List, Tuple, Any, Optional
from src.utils.logger import logger

class ResultExtractor(ABC):
    """
    仿真结果提取器抽象基类
    
    定义通用的结果提取标准和数据处理方法，
    """

    def __init__(self):
        """
        初始化基类
        Args:
            project_handle: 仿真软件的项目对象句柄
        """
        self.output_dir = os.path.join(os.getcwd(), "simulation_results")
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    # ============================================================
    # 抽象方法：子类必须实现的核心功能
    # ============================================================
    
    @abstractmethod
    def extract_s_parameters(self, **kwargs) -> Dict[str, np.ndarray]:
        """
        [抽象] 提取 S 参数数据
        子类必须实现此方法以获取具体的 S 参数。
        
        Returns:
            Dict: 包含 freq, S11_mag, S11_phase 等的字典
        """
        pass

    @abstractmethod
    def extract_realized_gain(self, **kwargs) -> Tuple[np.ndarray, np.ndarray]:
        """
        [抽象] 提取增益数据
        子类必须实现此方法以获取具体的增益值。
        
        Returns:
            Tuple: (freq_array, gain_array)
        """
        pass

    def extract_valid_data(self, threshold_db: float = -10.0, **kwargs) -> Optional[Dict[str, np.ndarray]]:
        """
        提取数据 -> 计算掩码 -> 验证有效性 -> 计算带宽
        """
        try:
            # 1. 提取原始数据
            logger.info(f"正在提取数据 (阈值: {threshold_db} dB)...")
            raw_data = self.extract_s_parameters(**kwargs)
            
            # 获取 S11 幅度
            s11_keys = [k for k in raw_data.keys() if 'mag' in k]
            if not s11_keys: return None
            
            s11_data = raw_data[s11_keys[0]]
            freq_data = raw_data['freq']

            # mask 是一个布尔数组，True 表示该频点满足条件 (S11 < threshold)
            mask = s11_data < threshold_db

            # 3. 快速过滤：如果没有一个点是 True，直接返回 None
            if not np.any(mask):
                logger.warning(f"数据无效：全频段 S11 均未低于 {threshold_db} dB，已过滤。")
                return None

            # 4. 数据有效，直接复用上面的 mask 计算带宽
            bw_info = self._calculate_bandwidth_from_mask(freq_data, mask)
            
            # 5. 注入结果
            raw_data['bandwidth_info'] = bw_info
            logger.info(f"数据有效 | 占比: {bw_info['overall_percentage']:.1f}% | 频带数: {len(bw_info['bands'])}")
            
            return raw_data

        except Exception as e:
            logger.error(f"数据处理失败: {e}")
            return None

    def _calculate_bandwidth_from_mask(self, freq_data: np.ndarray, mask: np.ndarray) -> Dict:
        """
        [内部工具] 直接利用现成的 mask 计算带宽
        不再接收 threshold 参数，因为 mask 已经代表了阈值判断结果
        """
        result = {"bands": [], "overall_percentage": 0.0}
        
        # 计算整体占比
        result["overall_percentage"] = (np.sum(mask) / len(freq_data)) * 100.0

        # 寻找连续区间 (利用现成的 mask)
        diff = np.diff(mask.astype(int))
        start_indices = np.where(diff == 1)[0] + 1
        end_indices = np.where(diff == -1)[0]

        # 处理边界
        if mask[0]: start_indices = np.insert(start_indices, 0, 0)
        if mask[-1]: end_indices = np.append(end_indices, len(mask) - 1)

        for start_idx, end_idx in zip(start_indices, end_indices):
            if end_idx > start_idx:
                f_start = float(freq_data[start_idx])
                f_end = float(freq_data[end_idx])
                result["bands"].append({
                    "start_freq": f_start, 
                    "end_freq": f_end, 
                    "bandwidth": f_end - f_start,
                    "center_freq": (f_start + f_end) / 2
                })
        
        return result

    def compute_bandwidth(self, freq_data: np.ndarray, s11_data: np.ndarray, threshold_db: float = -10.0) -> Dict:
        """
        如果外部只想单独算带宽，这里负责生成 mask 并调用内部工具
        """
        mask = s11_data < threshold_db
        return self._calculate_bandwidth_from_mask(freq_data, mask)

    def save_to_csv(self, data: Dict, filename: str) -> str:
        """
        [通用] 将结果字典保存为 CSV 文件
        
        Args:
            data: 包含数据的字典
            filename: 文件名
            
        Returns:
            str: 保存的文件路径
        """
        filepath = os.path.join(self.output_dir, filename)
        try:
            # 将数组转换为 DataFrame 并保存
            # 如果数组长度不一致，pandas 会自动处理（需确保数据对齐）
            df = pd.DataFrame(data)
            df.to_csv(filepath, index=False)
            logger.info(f"结果已保存至: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"保存 CSV 失败: {e}")
            raise