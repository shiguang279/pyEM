# -*- coding: utf-8 -*-
"""
通用并行调度器 (ParallelScheduler)

架构设计原则:
1. 全局单例 DesignEnvironment: 所有计算任务共享主进程启动的唯一 CST 主界面。
2. 错峰启动策略: 子进程按指定时间间隔依次启动，避免接口拥堵。
3. 资源隔离: 每个子进程操作独立的 .cst 文件副本，防止数据竞争。
4. 路径安全: 全程使用绝对路径，防止工作目录切换导致的文件丢失。
"""

import os
import time
import shutil
import multiprocessing as mp
from multiprocessing import Process, Queue
from typing import Dict, List, Any
import itertools
import datetime

# 项目依赖导入
from src.cst.app import CSTDesignEnv, CSTProject
from src.core.sim_runner import RUNNER_REGISTRY, RunMode
from src.core.sim_setup import SimSetup, SimulationMode
from src.core.data_saver import HDF5Saver
from src.cst.runner import CSTRunner
from src.utils.logger import logger

# ==========================================
# 子进程 Worker 函数
# ==========================================
def _simulation_worker(
    worker_id: int, 
    task_list: List[Dict], 
    project_file: str, 
    main_de_pid: int, 
    result_queue: Queue,
    runner_type: str,
    setup_dict: Dict,
    batch_id: int = 0
):
    """
    [子进程入口] 执行具体的仿真任务。

    该函数负责在独立的子进程中初始化 CST 环境，加载项目，
    并循环执行分配到的仿真任务列表。

    Args:
        worker_id: 当前工作进程的 ID。
        task_list: 待执行的仿真任务参数列表。
        project_file: 项目文件的路径。
        main_de_pid: 主进程中 Design Environment 的进程 ID。
        result_queue: 用于向主进程回传结果的队列。
        runner_type: 运行器类型的字符串标识。
        setup_dict: 包含仿真配置的全局字典。
    """
    logger.info(f"[Worker {worker_id}] 进程启动 (PID: {os.getpid()})")
    local_results = []
    cst_design_env = None
    cst_project = None
    
    # --------------------------------------------------
    # 阶段 1: 环境连接与初始化
    # --------------------------------------------------
    try:
        # 1.1 连接 DesignEnvironment
        # 使用重试机制以应对多进程启动时的竞态条件或资源锁定
        retry_count = 0
        max_retries = 3
        while retry_count < max_retries:
            try:
                cst_design_env = CSTDesignEnv.connect(main_de_pid, quiet=True)
                logger.debug(f"[Worker {worker_id}] 成功连接到 DesignEnv (PID: {main_de_pid})")
                break
            except Exception as e:
                retry_count += 1
                logger.warning(f"[Worker {worker_id}] 连接 DesignEnv 失败，重试 ({retry_count}/{max_retries}): {e}")
                time.sleep(2) 
        
        if not cst_design_env:
            raise RuntimeError("无法连接到 DesignEnvironment，达到最大重试次数。")
        
        # 1.2 创建 Project 包装器
        cst_project = CSTProject(cst_design_env)
        
        # 确保使用绝对路径，避免子进程工作目录不同导致的问题
        if not os.path.isabs(project_file):
            project_file = os.path.abspath(project_file)

        # 1.3 加载或创建项目
        if os.path.exists(project_file):
            # 情况 A: 文件存在 -> 打开现有副本
            cst_project.open(project_file)
            logger.debug(f"[Worker {worker_id}] 已打开现有项目: {os.path.basename(project_file)}")
        else:
            # 情况 B: 文件不存在 -> 创建新工程 (通常用于 Design 模式)
            cst_project.new_mws() 
            logger.debug(f"[Worker {worker_id}] 已创建新项目")
        
        # 激活项目窗口，确保 CST 能够正确响应后续命令
        if cst_project.project:
            cst_project.project.activate()
            
        logger.debug(f"[Worker {worker_id}] 项目已加载并激活: {os.path.basename(project_file)}")

        # --------------------------------------------------
        # 阶段 2: 任务执行循环
        # --------------------------------------------------
        
        # 获取对应的 Runner 类
        runner_class = RUNNER_REGISTRY.get(runner_type)
        if not runner_class:
            raise ValueError(f"未找到 Runner 类型: {runner_type}")
            
        # 实例化 Runner
        runner = runner_class(
            simulation_mode=setup_dict.get('simulation_mode'), 
            output_dir=setup_dict.get('output_dir', 'output')
        )

        runner.setup_dict = setup_dict
        # 注入共享的 Design Environment，避免重复启动 CST 核心进程
        runner.set_shared_design_env(cst_design_env)

        # 遍历任务列表
        for idx, params in enumerate(task_list):
            try:
                # 确保当前项目处于激活状态
                if cst_project.project:
                    cst_project.project.activate()
                
                logger.info(f"[Worker {worker_id}] 正在执行任务 {idx+1}/{len(task_list)}")
                
                # 执行具体的仿真运行逻辑
                result_data = runner.run(cst_project, setup_dict, params, project_file)
                
                if result_data:
                    result_data['worker_id'] = worker_id
                    result_data['task_idx'] = idx
                    result_data['batch_id'] = batch_id
                    local_results.append(result_data)
                
                logger.info(f"[Worker {worker_id}] 任务 {idx+1}/{len(task_list)} 完成.")
                    
            except Exception as e:
                # 捕获单个任务的异常，记录日志并继续执行下一个任务
                # 防止单个参数组合的错误导致整个 Worker 进程退出
                logger.error(f"[Worker {worker_id}] 任务 {idx+1} 执行失败: {e}", exc_info=True)
                continue

    # --------------------------------------------------
    # 阶段 3: 异常处理与资源清理
    # --------------------------------------------------
    except Exception as e:
        # 捕获初始化或严重错误，导致 Worker 无法继续运行
        logger.error(f"[Worker {worker_id}] 发生严重错误 (Worker 退出): {e}", exc_info=True)
        result_queue.put({'worker_id': worker_id, 'error': str(e), 'status': 'failed'})
        return

    finally:
        # 无论成功与否，都在退出前尝试保存和清理资源
        if cst_project and cst_project.project:
            try:
                cst_project.project.activate()
                # 保存包含结果的项目文件
                cst_project.save(project_file, include_results=True)
                logger.debug(f"[Worker {worker_id}] 结果已保存")
            except Exception as e:
                logger.error(f"[Worker {worker_id}] 保存失败: {e}")
        
        if cst_project:
            try:
                cst_project.close_project()
            except:
                # 忽略关闭时的异常，防止掩盖之前的错误信息
                pass
        
        logger.info(f"[Worker {worker_id}] 任务结束，提交 {len(local_results)} 个结果。")
        result_queue.put({'worker_id': worker_id, 'results': local_results, 'status': 'success'})

# ==========================================
# 并行调度器类
# ==========================================
class ParallelScheduler:
    """
    基于 multiprocessing 的通用并行调度器。
    支持分批执行和 Design Env 的周期性重启，以释放 GUI 资源并提高稳定性。
    """

    def __init__(self, 
                 setup: 'SimSetup', 
                 num_workers: int = 1,
                 base_runner_type: str = "CST",
                 shared_design_env: 'CSTDesignEnv' = None, 
                 result_filename: str = "results.h5", 
                 project_start_interval: int = 10,
                 batch_size: int = 20
                 ):
        """
        初始化调度器。
        
        Args:
            setup: 仿真设置对象。
            num_workers: 并行 Worker 数量。
            base_runner_type: 基础 Runner 类型 (如 "CST")。
            shared_design_env: 共享的 CST DesignEnvironment 实例。
            result_filename: 结果文件名。
            project_start_interval: Worker 进程启动的时间间隔（秒）。
            batch_size: 每批次处理的任务数量，达到此数量后会重启 Design Env。
        """
        self.setup = setup
        self.num_workers = max(1, num_workers)
        self.base_runner_type = base_runner_type.upper()
        self.shared_design_env = shared_design_env
        self.project_start_interval = project_start_interval
        self.batch_size = batch_size
        
        # 1. 设置输出目录 (确保是绝对路径)
        self.output_dir = os.path.abspath(setup.output_dir)
        os.makedirs(self.output_dir, exist_ok=True)
        
        # 2. 构建带时间戳的结果文件路径
        template_path = getattr(setup, 'template_path', None) or setup.file_path
        if template_path:
            template_path = os.path.abspath(template_path)
            template_name = os.path.splitext(os.path.basename(template_path))[0]
        else:
            template_name = "default"
            
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        final_filename = f"{template_name}_{timestamp}_{result_filename}"
        self.result_file_path = os.path.join(self.output_dir, final_filename)
        
        logger.info(f"结果文件将保存为: {self.result_file_path}")

        # 3. 获取 Runner 类
        self.base_runner_class = RUNNER_REGISTRY.get(self.base_runner_type)
        if not self.base_runner_class:
            raise ValueError(f"未注册的 Runner 类型: {self.base_runner_type}")

        # 4. 准备工作目录
        self.work_dir = os.path.join(self.output_dir, "parallel_work")
        if os.path.exists(self.work_dir):
            shutil.rmtree(self.work_dir)
        os.makedirs(self.work_dir, exist_ok=True)

        self.worker_file_map: Dict[int, str] = {}

    def _prepare_worker_files(self):
        """准备阶段：为每个 Worker 准备独立的工程文件。"""
        if self.setup.simulation_mode == SimulationMode.DESIGN:
            logger.info("Design 模式：Worker 将创建新工程。")
            worker_file = os.path.join(self.work_dir, "design_temp.cst")
            worker_file = os.path.abspath(worker_file)
            os.makedirs(os.path.dirname(worker_file), exist_ok=True)
            self.worker_file_map = {0: worker_file}
            return

        template_path = getattr(self.setup, 'template_path', None) or self.setup.file_path
        
        if not template_path or not os.path.exists(template_path):
            raise FileNotFoundError(f"模板文件不存在: {template_path}")
        
        template_path = os.path.abspath(template_path)
        template_basename = os.path.splitext(os.path.basename(template_path))[0]
        
        # 仅在首次调用时复制文件，避免重复IO
        if not self.worker_file_map:
            logger.info(f"正在为 {self.num_workers} 个 Worker 准备独立文件...")
            for worker_id in range(self.num_workers):
                worker_file = os.path.join(self.work_dir, f"{template_basename}_worker_{worker_id}.cst")
                worker_file = os.path.abspath(worker_file)
                shutil.copy2(template_path, worker_file)
                self.worker_file_map[worker_id] = worker_file

    def _generate_tasks(self) -> List[Dict]:
        """[核心逻辑] 生成任务列表。"""
        mode = self.setup.simulation_mode
        
        # --- 1. DESIGN 模式 ---
        if mode == SimulationMode.DESIGN:
            if self.num_workers != 1:
                logger.warning(f"DESIGN 模式强制单进程。")
                self.num_workers = 1
            return []

        # --- 2. TOPOLOGY 模式 ---
        elif mode == SimulationMode.TOPOLOGY_MODELING:
            total = getattr(self.setup, 'total_iterations', 100)
            return [{'iteration': i} for i in range(total)]

        # --- 3. PARAMETRIC 模式 ---
        elif mode == SimulationMode.PARAMETRIC_MODELING:
            sweep_params = self.setup.sweep_params
            
            if isinstance(sweep_params, list):
                return sweep_params
            
            elif isinstance(sweep_params, dict):
                if not sweep_params: return []
                keys, values = zip(*sweep_params.items())
                combinations = [dict(zip(keys, combo)) for combo in itertools.product(*values)]
                return combinations
            
        return []
        
    def _restart_design_env(self) -> 'CSTDesignEnv':
        """
        [新增] 安全重启 Design Env。
        关闭当前环境并启动一个新的实例，返回新实例。
        """
        if not self.shared_design_env:
            logger.warning("没有提供 shared_design_env，跳过重启。")
            return None

        logger.info(">>> 正在关闭旧的 Design Env 以释放 GUI 资源...")
        try:
            # 调用 CSTDesignEnv 提供的 close_env 方法
            self.shared_design_env.close_env()
        except Exception as e:
            logger.error(f"关闭 Design Env 时出错: {e}")
        
        # 删除旧引用，辅助垃圾回收
        del self.shared_design_env

        logger.info(">>> 正在启动新的 Design Env 实例...")
        try:
            # 实例化一个新的 CSTDesignEnv (不带 pid 参数即为新建模式)
            new_env = CSTDesignEnv(quiet=True)
            logger.info(f">>> 新 Design Env 启动成功 (PID: {new_env.pid})")
            return new_env
        except Exception as e:
            logger.error(f"启动新 Design Env 时出错: {e}")
            raise RuntimeError("无法重启 Design Env")

    def run(self) -> Dict[str, str]:
        """主执行入口：支持分批执行和 Env 重启。"""
        # 1. 准备阶段
        self._prepare_worker_files()
        all_tasks = self._generate_tasks()
        
        if not all_tasks:
            logger.warning("任务列表为空")
            return {"status": "empty"}

        # [关键] 将任务分割成批次
        batches = [all_tasks[i:i + self.batch_size] for i in range(0, len(all_tasks), self.batch_size)]
        total_batches = len(batches)
        
        logger.info(f"总共 {len(all_tasks)} 个任务，分为 {total_batches} 个批次 (每批 {self.batch_size} 个任务)。")

        # [关键] 主循环：按批次处理
        for batch_idx, current_batch_tasks in enumerate(batches):
            logger.info(f"--- 开始处理第 {batch_idx + 1}/{total_batches} 批次 ---")
            
            # 如果是第一批之后的批次，先重启 Env
            if batch_idx > 0:
                # 更新 self.shared_design_env 为新的实例
                self.shared_design_env = self._restart_design_env()
                # 给予系统一点时间完成进程启动和资源分配
                time.sleep(5) 

            # 2. 任务分发 (针对当前批次)
            chunks = []
            for wid in range(self.num_workers):
                start_idx = wid * len(current_batch_tasks) // self.num_workers
                end_idx = (wid + 1) * len(current_batch_tasks) // self.num_workers
                if start_idx < end_idx:
                    task_subset = current_batch_tasks[start_idx:end_idx]
                    project_file = os.path.abspath(self.worker_file_map.get(wid, self.setup.file_path))
                    chunks.append((wid, task_subset, project_file))

            if not chunks:
                logger.warning(f"第 {batch_idx + 1} 批次没有生成有效任务块，跳过。")
                continue

            # 3. 获取主进程 PID
            # [关键] 每次循环都重新获取，因为 Env 可能刚刚重启，PID 变了
            main_de_pid = self.shared_design_env.pid if self.shared_design_env else None
            
            # 4. 启动进程
            logger.info(f"启动 {len(chunks)} 个 Worker 进程 (间隔 {self.project_start_interval}s)...")
            processes = []
            result_queue = Queue()
            
            setup_dict = self.setup.to_dict()

            for wid, task_subset, project_file in chunks:
                p = Process(
                    target=_simulation_worker,
                    args=(wid, task_subset, project_file, main_de_pid, result_queue, self.base_runner_type, setup_dict, batch_idx)
                )
                p.start()
                processes.append(p)
                logger.info(f"Worker {wid} 进程已创建 (PID: {p.pid})")
                
                if wid < len(chunks) - 1:
                    time.sleep(self.project_start_interval)

            # 5. 结果收集
            completed_workers = 0
            total_workers = len(processes)
            saver = HDF5Saver()
            result_file_path = os.path.abspath(self.result_file_path)
            
            while completed_workers < total_workers:
                try:
                    item = result_queue.get(timeout=5) 
                    if item.get('status') == 'success':
                        logger.info(f"收到 Worker {item['worker_id']} 的结果包")
                        for res in item['results']:
                            saver.append_to_h5(res, 
                                               result_file_path, 
                                               f"batch_{res['batch_id']}_worker_{res['worker_id']}_{res['task_idx']}")
                    elif item.get('status') == 'failed':
                        logger.error(f"Worker {item['worker_id']} 运行失败: {item.get('error')}")
                except Exception:
                    completed_workers = sum(1 for p in processes if not p.is_alive())
                    continue

            # 6. 进程同步
            for p in processes:
                p.join()
                
            logger.info(f"--- 第 {batch_idx + 1} 批次任务完成 ---")

        # 所有批次处理完毕
        logger.info("所有并行任务完成。")
        
        # --------------------------------------------------
        # 7. 结果验证与结构显示
        # --------------------------------------------------
        if os.path.exists(result_file_path):
            logger.info("正在生成结果文件结构报告...")
            HDF5Saver.display_structure(result_file_path)
        else:
            logger.warning(f"结果文件未生成: {result_file_path}")
            
        return {"result_file_path": result_file_path}