# -*- coding: utf-8 -*-
"""
通用仿真调度器 (SimScheduler) 
核心架构：主进程单例 DesignEnv，Worker 进程复用该实例并独立管理 Project。
"""

import os
import shutil
import multiprocessing
from multiprocessing import Process, Queue as MPQueue
from typing import Dict, List, Any, Optional
import datetime
import queue
import itertools

from src.core.data_saver import HDF5Saver
from src.core.setup import SimSetup
from src.core.runner import RUNNER_REGISTRY, RunMode, SimulationMode
from src.core.app import SimDesignEnv
from src.utils.logger import logger


# =================================================================================
# 1. 全局 Worker 函数
# =================================================================================
def _batch_worker(worker_id, design_env, data_queue, runner_type, setup_dict, project_file, task_package_list, batch_id):
    """
    批次 Worker：一个批次内只打开一次 Project，连续跑完所有分配的任务。
    task_package_list: 里面装的是 (task_params, global_task_id) 的元组列表
    """
    if runner_type == "CST":
        try:
            # 动态导入 CST Runner 模块
            from src.cst.runner import CSTRunner
            # 强制写入全局注册表
            from src.core.runner import RUNNER_REGISTRY
            RUNNER_REGISTRY["CST"] = CSTRunner
            logger.info(f"[Worker {worker_id}] 子进程注入 CST Runner")
        except Exception as e:
            logger.info(f"[Worker {worker_id}] 子进程注入 CST 失败: {e}")
            raise
    runner = None

    try:
        # 1. 实例化 Runner
        runner_class = RUNNER_REGISTRY.get(runner_type)
        if not runner_class:
            raise RuntimeError(f"未注册的 Runner: {runner_type}")
            
        runner = runner_class(
            output_dir=setup_dict.get('output_dir', 'output'),
            run_mode=setup_dict.get('run_mode', RunMode.SAVE_AND_RUN),
            simulation_mode=setup_dict.get('simulation_mode', SimulationMode.DESIGN)
        )
        
        # 2. 注入当前批次的 DesignEnv
        runner.set_shared_design_env(design_env)
        
        # 3. 批次开始时，只打开一次 Project
        logger.info(f"[Worker {worker_id}] 批次 {batch_id} 准备执行 {len(task_package_list)} 个任务：打开 Project {project_file}")
        project_instance = runner.open_project(design_env, project_file)
        
        # 4. 循环执行分给这个 Worker 的所有任务
        for local_idx, package in enumerate(task_package_list):
            task_params, global_task_id = package # 直接解包拿到准确的 ID
            
            logger.info(f"[Worker {worker_id}] 执行批次 {batch_id} 的第 {local_idx + 1}/{len(task_package_list)} 个任务 (全局ID: {global_task_id})")
            
            result = runner.run(
                setup_dict=setup_dict,
                params=task_params,
                project_file=project_file
            )
            
            # 5. 发送结果
            if result and result.get('status') == 'success':
                result_package = {
                    'worker_id': worker_id,
                    'batch_id': batch_id,
                    'global_task_id': global_task_id,
                    'params': task_params,
                    'result': {k: v for k, v in result.items() if k != 'status'},
                    'status': 'success'
                }
                data_queue.put(result_package)
            else:
                logger.error(f"[Worker {worker_id}] 任务失败: {result}")

    except Exception as e:
        logger.error(f"[Worker {worker_id}] 异常: {e}")
    finally:
        # 6. 批次结束时，关闭 Project
        if runner and runner.current_project:
            logger.info(f"[Worker {worker_id}] 批次 {batch_id}：关闭 Project")
            runner.close_project()

# =================================================================================
# 2. SimScheduler 类 (主进程调度器)
# =================================================================================
class SimScheduler:
    """
    通用仿真调度器。
    负责在主进程启动单例 DesignEnv，并为 Worker 分配独立 Project 文件。
    """

    def __init__(self, 
                 setup: SimSetup, 
                 num_workers: int = 1, 
                 runner_type: str = "CST",
                 result_filename: str = "results.h5", 
                 batch_size: int = 100):
        
        self.setup = setup
        self.num_workers = max(1, num_workers)
        self.runner_type = runner_type.upper()
        self.batch_size = batch_size

        self.output_dir = os.path.abspath(setup.output_dir)
        os.makedirs(self.output_dir, exist_ok=True)
        
        template_path = getattr(setup, 'template_path', None) or setup.file_path
        template_name = os.path.splitext(os.path.basename(template_path))[0] if template_path else "default"
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.result_file_path = os.path.join(self.output_dir, f"{template_name}_{timestamp}_{result_filename}")
        
        self.work_dir = os.path.join(self.output_dir, "parallel_work")
        os.makedirs(self.work_dir, exist_ok=True)
        
        self.worker_file_map: Dict[int, str] = {}

    def _prepare_worker_files(self):
        """为每个 Worker 准备独立的 Project 文件副本"""
        self.worker_file_map = {}
        template_path = getattr(self.setup, 'template_path', None) or self.setup.file_path
        if not template_path or not os.path.exists(template_path):
            raise FileNotFoundError(f"模板文件不存在: {template_path}")

        template_basename = os.path.splitext(os.path.basename(template_path))[0]
        # 动态决定文件后缀的映射字典，方便后续扩展更多软件
        ext_map = {
            "CST": ".cst",
            "HFSS": ".aedt",
            "COMSOL": ".mph"  # COMSOL Multiphysics 的原生文件格式
        }
        # 获取当前 Runner 类型对应的后缀，如果没有则默认为空字符串
        ext = ext_map.get(self.runner_type, "")
        for worker_id in range(self.num_workers):
            worker_filename = f"{template_basename}_worker_{worker_id}{ext}"
            worker_file_path = os.path.abspath(os.path.join(self.work_dir, worker_filename))
            shutil.copy2(template_path, worker_file_path)
            self.worker_file_map[worker_id] = worker_file_path
        logger.info(f"独立 Project 文件准备完成，共 {len(self.worker_file_map)} 个")

    def run(self):
        """执行整体调度流程"""
        logger.info(f"启动 SimScheduler，Worker 数量: {self.num_workers}")
        self._prepare_worker_files()
        
        # 获取所有任务
        all_tasks = self._generate_tasks()
        total_tasks = len(all_tasks)
        
        # 计算批次数
        num_batches = (total_tasks + self.batch_size - 1) // self.batch_size 
        
        # 启动 HDF5 写入进程
        data_queue = multiprocessing.Queue()
        writer_process = multiprocessing.Process(target=self._hdf5_writer_loop, args=(data_queue,))
        writer_process.start()

        try:
            task_offset = 0
            
            # --- 循环：遍历每一个批次 ---
            for batch_id in range(num_batches):
                logger.info(f"--- 主进程：开始执行第 {batch_id + 1} / {num_batches} 批任务 ---")
                
                # 准备当前批次的任务
                current_batch_tasks = all_tasks[task_offset : task_offset + self.batch_size]
                # 给任务打上真实的全局 ID（比如第 0 批就是 0-99，第 1 批就是 100-199）
                batch_tasks_with_id = []
                for i, task in enumerate(current_batch_tasks):
                    real_global_id = task_offset + i
                    batch_tasks_with_id.append((task, real_global_id))
                
                task_offset += len(current_batch_tasks)
                
                # 为当前批次启动 DesignEnv
                runner_class = RUNNER_REGISTRY.get(self.runner_type)
                batch_design_env: SimDesignEnv = runner_class.start_design_environment()
                logger.info(f"[批次 {batch_id}] DesignEnv 启动成功")

                # 将当前批次的任务，平均分给 Worker
                worker_task_map = {}
                for i, task_package in enumerate(batch_tasks_with_id):
                    target_worker_id = i % self.num_workers
                    if target_worker_id not in worker_task_map:
                        worker_task_map[target_worker_id] = []
                    worker_task_map[target_worker_id].append(task_package)
                
                # 启动当前批次的并行 Worker
                group_processes = []
                for worker_id in range(self.num_workers):
                    tasks_for_this_worker = worker_task_map.get(worker_id, [])
                    project_file = self.worker_file_map.get(worker_id)
                    
                    if not tasks_for_this_worker:
                        continue

                    p = Process(
                        target=_batch_worker,
                        args=(
                            worker_id, 
                            batch_design_env, 
                            data_queue, 
                            self.runner_type,
                            self.setup.to_dict(),
                            project_file, 
                            tasks_for_this_worker, 
                            batch_id
                        )
                    )
                    p.start()
                    group_processes.append(p)
                
                # 阻塞等待当前批次的所有 Worker 完成
                for p in group_processes:
                    p.join()
                
                logger.info(f"--- 第 {batch_id} 批次所有子任务完成 ---")

                # 当前批次结束：关闭当前批次的 DesignEnv
                logger.info(f"[批次 {batch_id}] 正在关闭当前批次的 DesignEnv...")
                batch_design_env.close_env()
                logger.info(f"结果写入到 {self.result_file_path}")
            
            logger.info("所有批次仿真完成！")

        except Exception as e:
            logger.error(f"调度器运行出错: {e}")
        finally:
            # 结束写入进程
            data_queue.put(None)
            writer_process.join(timeout=10)

    def _generate_tasks(self) -> List[Dict]:
        mode = self.setup.simulation_mode
        if mode == SimulationMode.DESIGN:
            return [{}]
        elif mode == SimulationMode.TOPOLOGY_MODELING:
            total = getattr(self.setup, 'total_iterations', 100)
            return [{'iteration': i} for i in range(total)]
        elif mode == SimulationMode.PARAMETRIC_MODELING:
            sweep_params = self.setup.sweep_params
            if isinstance(sweep_params, list): return sweep_params
            elif isinstance(sweep_params, dict):
                if not sweep_params: return []
                keys, values = zip(*sweep_params.items())
                return [dict(zip(keys, combo)) for combo in itertools.product(*values)]
        return []

    def _hdf5_writer_loop(self, data_queue: MPQueue):
        """
        HDF5 写入循环：流式处理队列数据。
        """
        saver = HDF5Saver()
        logger.info(f"HDF5 写入进程启动，目标文件: {self.result_file_path}")
        
        while True:
            try:
                # 非阻塞式获取数据 (超时0.1秒)，确保能实时响应退出信号
                item = data_queue.get(timeout=0.1)
                
                if item is None:
                    logger.info("收到结束信号，HDF5 写入进程即将退出。")
                    break
                    
                # 提取任务标识
                batch_id = item['batch_id']
                global_task_id = item['global_task_id']
                result_data = item['result']
                
                # 构建存储路径
                group_path = f"/sample_{global_task_id}"
                
                saver.append_to_h5(result_data, self.result_file_path, group_path)
                
                logger.info(f"结果数据成功写入 | Batch:{batch_id} Task:{global_task_id} -> [HDF5 目录]: {group_path}")
                
            except multiprocessing.queues.Empty:
                # 队列空闲，继续轮询
                continue
            except Exception as e:
                logger.error(f"HDF5 写入异常: {e}", exc_info=True)