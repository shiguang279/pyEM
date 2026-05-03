# -*- coding: utf-8 -*-
"""
仿真主控入口文件
"""

import os
import time
from typing import Type, Optional, Dict, Any
from src.core.scheduler import SimScheduler
from src.core.runner import SimulationMode, RUNNER_REGISTRY
from src.utils.logger import logger

def run_simulation(software: str = "CST", setup_class: Type = None) -> Optional[Dict[str, Any]]:
    """
    通用仿真启动工厂函数。
    
    流程:
    1. 实例化 Setup 配置。
    2. 通过 SimScheduler 调度器执行任务。
    """
    start_time = time.time()

    if setup_class is None:
        raise ValueError("没有提供 Setup.")
    
    software_key = software.upper()

    if software_key == "CST":
        # 只有在需要用到 CST 时，才在这里导入。
        from src.cst.runner import CSTRunner
        RUNNER_REGISTRY["CST"] = CSTRunner
        logger.info(">>> [系统] CST Runner 已注册到全局注册表")

    # --- 2. 实例化 Setup 配置 ---
    try:
        setup_instance = setup_class()
    except Exception as e:
        logger.error(f"实例化 Setup 配置失败: {e}")
        return {"status": "error", "message": f"Setup instantiation failed: {e}"}

    # --- 3. 提取配置参数 ---
    simulation_mode = getattr(setup_instance, 'SIMULATION_MODE', SimulationMode.DESIGN)
    num_workers = getattr(setup_instance, 'num_workers', 1)
    
    # 强制输出目录为绝对路径，防止相对路径在子进程中失效
    if getattr(setup_instance, 'output_dir', None):
        setup_instance.output_dir = os.path.abspath(setup_instance.output_dir)
    
    # 确保模板文件路径也是绝对路径
    if hasattr(setup_instance, 'file_path') and setup_instance.file_path:
        setup_instance.file_path = os.path.abspath(setup_instance.file_path)
    if hasattr(setup_instance, 'template_path') and setup_instance.template_path:
        setup_instance.template_path = os.path.abspath(setup_instance.template_path)

    # --- 4. 执行调度 ---
    result = {}
    try:
        # 校验模式合法性
        if simulation_mode not in [SimulationMode.DESIGN, SimulationMode.PARAMETRIC_MODELING, SimulationMode.TOPOLOGY_MODELING]:
            raise ValueError(f"未知的仿真模式: {simulation_mode}")

        logger.info(f"准备启动仿真调度器 | 软件: {software_key} | 模式: {simulation_mode.value} | Worker数: {num_workers}")

        # 实例化调度器并运行
        scheduler = SimScheduler(
            setup=setup_instance, 
            num_workers=num_workers,
            runner_type=software_key
        )
        result = scheduler.run() 

    except Exception as e:
        logger.error(f"调度器运行发生严重错误: {e}", exc_info=True)
        result = {"status": "error", "message": str(e)}

    # --- 5. 耗时统计 ---
    end_time = time.time()
    elapsed_time = end_time - start_time
    hours, rem = divmod(elapsed_time, 3600)
    minutes, seconds = divmod(rem, 60)
    time_str = f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"
    
    logger.info(f"运行结束，总耗时: {time_str}")

    return result