# -*- coding: utf-8 -*-
"""
仿真主控入口文件
"""

import os
import time
import datetime
from typing import Type, Optional, Dict, Any
from src.core.parallel_scheduler import ParallelScheduler
from src.core.sim_runner import SimulationMode, RUNNER_REGISTRY
from src.utils.logger import logger

def run_simulation(software: str = "CST", setup_class: Type = None) -> Optional[Dict[str, Any]]:
    """
    通用仿真启动工厂函数。
    
    流程:
    1. 启动软件环境 (CST)。
    2. 实例化 Setup 配置。
    3. 通过并行调度器执行任务 (DESIGN 模式自动降级为单进程)。
    """
    start_time = time.time()

    # --- 1. 参数校验 ---
    if setup_class is None:
        raise ValueError("No Setup class provided.")
    
    software_key = software.upper()
    design_env_instance = None

    # --- 2. 软件环境初始化 (CST) ---
    if software_key == "CST":
        logger.info(f"正在加载 CST 模块...")
        try:
            # 启动 CST 设计环境
            from src.cst.app import CSTDesignEnv
            logger.info("正在启动 CST 设计环境...")
            design_env_instance = CSTDesignEnv(quiet=True)
            logger.info("CST 设计环境启动成功")
            
        except ImportError as e:
            logger.error(f"找不到 CST 模块: {e}")
            if design_env_instance:
                try: design_env_instance.close_env()
                except: pass
            return {"status": "error", "message": f"Module not found: {e}"}
        except Exception as e:
            logger.error(f"启动 CST 设计环境失败: {e}")
            return {"status": "error", "message": f"Failed to start CST environment: {e}"}
    
    # --- 3. 实例化 Setup 配置 ---
    try:
        setup_instance = setup_class()
    except Exception as e:
        logger.error(f"实例化 Setup 配置失败: {e}")
        if design_env_instance:
            try: design_env_instance.close_env()
            except: pass
        return {"status": "error", "message": f"Setup instantiation failed: {e}"}

    # --- 4. 提取配置参数 ---
    simulation_mode = getattr(setup_instance, 'SIMULATION_MODE', SimulationMode.DESIGN)
    num_workers = getattr(setup_instance, 'num_workers', 1)
    
    # 强制输出目录为绝对路径，防止相对路径在子进程中失效
    if setup_instance.output_dir:
        setup_instance.output_dir = os.path.abspath(setup_instance.output_dir)

    logger.info(f"启动调度器模式 -> {software_key} (Mode: {simulation_mode.value})")

    # --- 5. 执行调度 ---
    result = {}
    try:
        # 校验模式合法性
        if simulation_mode not in [SimulationMode.DESIGN, SimulationMode.PARAMETRIC_MODELING, SimulationMode.TOPOLOGY_MODELING]:
            raise ValueError(f"未知的仿真模式: {simulation_mode.value}")

        # 实例化调度器并运行
        scheduler = ParallelScheduler(
            setup=setup_instance, 
            num_workers=num_workers,
            base_runner_type=software_key,
            shared_design_env=design_env_instance
        )
        result = scheduler.run() 

    except Exception as e:
        logger.error(f"调度器运行发生严重错误: {e}", exc_info=True)
        result = {"status": "error", "message": str(e)}

    # --- 6. 资源清理 ---
    finally:
        if design_env_instance:
            try:
                logger.info("正在关闭 CST 设计环境...")
                design_env_instance.close_env()
                logger.info("CST 设计环境已安全关闭")
            except Exception as e:
                logger.error(f"关闭 CST 设计环境时发生错误: {e}")

    # --- 7. 耗时统计 ---
    end_time = time.time()
    elapsed_time = end_time - start_time
    hours, rem = divmod(elapsed_time, 3600)
    minutes, seconds = divmod(rem, 60)
    time_str = f"{int(hours):04d}:{int(minutes):02d}:{seconds:05.2f}"
    
    logger.info(f"运行结束，总耗时: {time_str}")

    return result