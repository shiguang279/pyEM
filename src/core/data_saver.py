# -*- coding: utf-8 -*-
"""
HDF5 数据保存工具类。

专门用于将 CSTResultExtractor 提取的数据字典保存为 HDF5 文件。
策略：严格模式。遇到非法键名或结构冲突直接报错，不进行自动替换或降级。
"""

import h5py
import numpy as np
import os
from typing import Dict, Any, Optional
from src.utils.logger import logger


class HDF5Saver:
    """HDF5 文件保存工具类。"""
    
    @staticmethod
    def save_results_to_h5(result_dict: Dict[str, Any], file_path: str, sample_id: Optional[str] = None) -> None:
        """
        保存 CST 仿真结果数据到 HDF5 文件。
        """
        # 强制转换为绝对路径
        file_path = os.path.abspath(file_path)
        
        # 确保输出目录存在
        dir_path = os.path.dirname(file_path)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
        
        with h5py.File(file_path, 'w') as f:
            if sample_id:
                root_group = f.create_group(sample_id)
            else:
                root_group = f
                
            primary_keys = set(result_dict.keys())
            expected_data_types = {'s_parameters', 's_floquet', 'realized_gain', 'farfield'}
            
            if primary_keys.intersection(expected_data_types):
                # 多数据字典处理
                for data_type, data_content in result_dict.items():
                    if isinstance(data_content, dict) and data_type in expected_data_types:
                        sub_group = root_group.create_group(data_type)
                        HDF5Saver._write_dict_to_group(sub_group, data_content)
            else:
                # 单一数据字典处理
                HDF5Saver._write_dict_to_group(root_group, result_dict)
                    
        logger.info(f"仿真数据已成功保存至: {file_path}")
        HDF5Saver.display_structure(file_path)

    @staticmethod
    def append_to_h5(result_dict: Dict[str, Any], file_path: str, sample_id: str) -> None:
        """以追加模式将数据写入 HDF5 文件。"""
        # 强制转换为绝对路径
        file_path = os.path.abspath(file_path)
        
        dir_path = os.path.dirname(file_path)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
        
        with h5py.File(file_path, 'a') as f:
            if sample_id in f:
                logger.warning(f"样本 ID '{sample_id}' 已存在，跳过写入。")
                return
            
            target_group = f.create_group(sample_id)
            HDF5Saver._write_dict_to_group(target_group, result_dict)
            
        logger.debug(f"数据已追加至: {file_path} -> {sample_id}")

    @staticmethod
    def _write_dict_to_group(group: h5py.Group, data_dict: Dict[str, Any]) -> None:
        """
        递归地将 Python 字典写入 HDF5 Group。
        严格模式：遇到非法键名直接抛出异常。
        """
        if not isinstance(data_dict, dict):
            logger.error(f"[HDF5Saver] 类型错误: 期望字典，得到 {type(data_dict)}")
            raise TypeError(f"期望字典类型，得到 {type(data_dict)}")
            
        logger.debug(f"[HDF5Saver] 正在处理字典，键: {list(data_dict.keys())}")

        for key, value in data_dict.items():
            # 如果键名包含非法字符，HDF5 底层会报错，我们在下方的 try-except 中捕获并抛出明确异常
            safe_key = str(key)
            
            logger.debug(f"[HDF5Saver] 处理键 '{safe_key}'，值类型: {type(value)}")
            
            # 1. 处理数值数组
            if isinstance(value, (np.ndarray, list)):
                try:
                    arr_value = np.array(value)
                    group.create_dataset(
                        safe_key, 
                        data=arr_value, 
                        compression="gzip", 
                        compression_opts=9
                    )
                except Exception as e:
                    logger.error(f"创建数据集 '{safe_key}' 失败: {e}")
                    raise

            # 2. 处理嵌套字典
            elif isinstance(value, dict):
                try:
                    sub_group = group.create_group(safe_key)
                    HDF5Saver._write_dict_to_group(sub_group, value)
                except Exception as e:
                    # 捕获底层错误，并抛出包含明确信息的运行时异常
                    error_msg = (
                        f"无法创建子组 '{safe_key}': {e}。 "
                        f"原因可能是：键名包含非法字符，或者该名称已作为数据集存在。"
                    )
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)

            # 3. 处理标量
            elif isinstance(value, (int, float, str, bool, np.number)):
                try:
                    group.create_dataset(safe_key, data=[value])
                except Exception as e:
                    logger.error(f"创建标量数据集 '{safe_key}' 失败: {e}")
                    raise

    @staticmethod
    def display_structure(file_path: str) -> None:
        """显示 HDF5 文件中的详细数据结构"""
        file_path = os.path.abspath(file_path)
        
        try:
            with h5py.File(file_path, 'r') as f:
                logger.info(f"=== HDF5 文件详细结构: {file_path} ===")
                
                found_datasets = False

                def print_structure(name, obj):
                    nonlocal found_datasets
                    depth = name.count('/')
                    indent = "  " * depth 
                    
                    if isinstance(obj, h5py.Dataset):
                        found_datasets = True
                        logger.info(f"{indent} 数据集: {name} | 形状: {obj.shape} | 类型: {obj.dtype}")
                    elif isinstance(obj, h5py.Group):
                        display_name = name if name else '/'
                        logger.info(f"{indent} 组: {display_name}")
                
                f.visititems(print_structure)
                
                if not found_datasets:
                    logger.warning("警告：未检测到任何数据集！正在检查顶层内容...")
                    for key in f.keys():
                        group = f[key]
                        logger.info(f"正在检查组 '{key}' 的直接成员：")
                        for sub_key in group.keys():
                            obj = group[sub_key]
                            logger.info(f"   - {sub_key}: 类型={type(obj)}")

                logger.info("="*50)
        except Exception as e:
            logger.error(f"读取 HDF5 文件结构失败: {e}")