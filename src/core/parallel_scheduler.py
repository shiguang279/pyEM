import os
import time
import shutil
import multiprocessing
from multiprocessing import Process, Queue as MPQueue
from typing import Dict, List, Any, Tuple, Optional
import itertools
import datetime
import threading
import queue

# 项目依赖导入
from src.cst.app import CSTDesignEnv, CSTProject
from src.core.sim_runner import RUNNER_REGISTRY, RunMode
from src.core.sim_setup import SimSetup, SimulationMode
from src.core.data_saver import HDF5Saver
from src.cst.runner import CSTRunner
from src.utils.logger import logger


# =================================================================================
# 1. 全局 Worker 函数 (必须定义在模块顶层，否则 Windows 多进程无法序列化)
# =================================================================================
def _global_simulation_worker(worker_id: int, project_file: str, main_de_pid: int, 
                             status_queue: MPQueue, data_queue: multiprocessing.Queue, 
                             runner_type: str, setup_dict: Dict, task_queue: multiprocessing.Queue, 
                             semaphore: Optional[multiprocessing.Semaphore]): # type: ignore
    """
    全局仿真 Worker (进程级生命周期)。
    负责连接当前批次的 CST 环境，循环领取并执行任务，最后统一关闭。
    """
    cst_design_env = None
    cst_project = None
    
    # 信号量控制：进入此处即占用一个并发名额
    with semaphore:
        try:
            # 连接环境并打开专属 Project
            cst_design_env = CSTDesignEnv.connect(main_de_pid, quiet=True)
            if not cst_design_env:
                raise RuntimeError("无法连接到 DesignEnvironment")
            
            cst_project = CSTProject(cst_design_env)
            if not os.path.isabs(project_file):
                project_file = os.path.abspath(project_file)
                
            if os.path.exists(project_file):
                cst_project.open(project_file)
                logger.info(f"[Worker {worker_id}] 专属项目已打开: {os.path.basename(project_file)}")
            else:
                cst_project.new_mws()
                logger.info(f"[Worker {worker_id}] 已创建新专属项目")
                
            if cst_project.project:
                cst_project.project.activate()

            # 不断从队列里领任务，直到拿到结束信号（None）
            while True:
                try:
                    # 增加超时判断，防止主进程崩溃时 Worker 永久卡死
                    task_package = task_queue.get(timeout=10) 
                except:
                    # 如果连续超时，继续等待
                    continue

                if task_package is None: # 收到结束信号，跳出循环
                    logger.info(f"[Worker {worker_id}] 收到结束信号，准备退出。")
                    break
                
                single_task, batch_idx, task_id = task_package
                
                # 调用具体的任务执行逻辑
                _execute_single_task_logic(worker_id, cst_project, single_task, 
                                           status_queue, data_queue, runner_type, 
                                           setup_dict, batch_idx, task_id)

        except Exception as e:
            logger.error(f"[Worker {worker_id}] 进程发生严重异常: {e}")
        finally:
            # Worker 彻底退出前，最后关闭一次专属 Project
            if cst_project and cst_project.project:
                try:
                    logger.info(f"[Worker {worker_id}] 批次任务完成，正在关闭专属项目...")
                    cst_project.close_project()
                    cst_project.project = None
                except Exception as e:
                    logger.warning(f"[Worker {worker_id}] 关闭项目时发生异常: {e}")


def _execute_single_task_logic(worker_id: int, cst_project: CSTProject, single_task: Dict, 
                               status_queue: MPQueue, data_queue: multiprocessing.Queue, 
                               runner_type: str, setup_dict: Dict, batch_idx: int, task_id: int):
    """
    纯粹的仿真执行逻辑。
    """
    task_status = 'failed'
    
    try:
        # 1. 准备 Runner
        runner_class = RUNNER_REGISTRY.get(runner_type)
        if not runner_class:
            raise ValueError(f"未找到对应的 Runner: {runner_type}")
        
        runner = runner_class(
            simulation_mode=setup_dict.get('simulation_mode'),
            output_dir=setup_dict.get('output_dir', 'output')
        )
        runner.setup_dict = setup_dict
        
        if cst_project.project:
            cst_project.project.activate()
        
        logger.info(f"[Worker {worker_id}] 正在执行批次 {batch_idx} 任务 ID {task_id}")
        status_queue.put({
            'type': 'RUNNING',
            'worker_id': worker_id,
            'batch_idx': batch_idx,
            'task_idx': task_id
        })
        
        # 2. 执行核心仿真任务
        # 这里的 project_file 依然要传进去，因为 run_simulation 内部需要
        project_file = cst_project.filename()
        result = runner.run(cst_project, setup_dict, single_task, project_file)
        
        if result.get('status') == 'success':
            task_status = 'success'
            result_data = {k: v for k, v in result.items() if k != 'status'}
            
            result_package = {
                'worker_id': worker_id,
                'batch_idx': batch_idx,
                'task_idx': task_id,
                'params': single_task,
                'result': result_data,
                'status': 'success'
            }
            try:
                data_queue.put(result_package, timeout=10) 
            except multiprocessing.queues.Full:
                logger.error(f"[Worker {worker_id}] Data Queue 满了！主进程可能卡死。")
        
            logger.info(f"[Worker {worker_id}] 批次 {batch_idx} 任务 {task_id} 已成功")
        else:
            logger.error(f"[Worker {worker_id}] 批次 {batch_idx} 任务 {task_id} 失败: {result.get('message')}")

    except Exception as e:
        logger.error(f"[Worker {worker_id}] 任务执行失败: {e}")
    finally:
        # 3. 汇报当前任务完成
        finish_report = {
            'type': 'FINISHED',
            'worker_id': worker_id,
            'batch_idx': batch_idx,
            'task_idx': task_id,
            'exit_status': task_status
        }
        try:
            status_queue.put(finish_report, timeout=10) 
        except multiprocessing.queues.Full:
            logger.error(f"[Worker {worker_id}] Status Queue 满了！主进程可能卡死。")

# =================================================================================
# 2. ParallelScheduler 类
# =================================================================================

class ParallelScheduler:
    """
    基于 multiprocessing 的通用并行调度器。
    """
    
    def __init__(self, setup: 'SimSetup', num_workers: int = 1, base_runner_type: str = "CST", 
                 shared_design_env: 'CSTDesignEnv' = None, result_filename: str = "results.h5", 
                 project_start_interval: int = 5.0, batch_size: int = 100):
        self.setup = setup
        self.num_workers = max(1, num_workers)
        self.base_runner_type = base_runner_type.upper()
        self.shared_design_env = shared_design_env
        self.project_start_interval = project_start_interval
        self.batch_size = batch_size

        # 设置输出目录
        self.output_dir = os.path.abspath(setup.output_dir)
        os.makedirs(self.output_dir, exist_ok=True)

        # 文件路径
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

        # 获取 Runner 类
        self.base_runner_class = RUNNER_REGISTRY.get(self.base_runner_type)
        if not self.base_runner_class:
            raise ValueError(f"未注册的 Runner 类型: {self.base_runner_type}")

        # 准备工作目录
        self.work_dir = os.path.join(self.output_dir, "parallel_work")
        if os.path.exists(self.work_dir):
            shutil.rmtree(self.work_dir)
        os.makedirs(self.work_dir, exist_ok=True)
        self.worker_file_map: Dict[int, str] = {}

    def _prepare_worker_files(self):
        """
        准备每个 Worker 使用的独立 Project 文件。
        """
        if self.setup.simulation_mode == SimulationMode.DESIGN:
            logger.info("Design 模式：Worker 将创建新工程。")
            worker_file = os.path.abspath(os.path.join(self.work_dir, "design_temp.cst"))
            os.makedirs(os.path.dirname(worker_file), exist_ok=True)
            self.worker_file_map = {0: worker_file}
            return

        template_path = getattr(self.setup, 'template_path', None) or self.setup.file_path
        if not template_path or not os.path.exists(template_path):
            raise FileNotFoundError(f"模板文件不存在: {template_path}")
        
        template_basename = os.path.splitext(os.path.basename(template_path))[0]
        self.worker_file_map = {}
        
        for worker_id in range(self.num_workers):
            worker_filename = f"{template_basename}_worker_{worker_id}.cst"
            worker_file_path = os.path.abspath(os.path.join(self.work_dir, worker_filename))
            shutil.copy2(template_path, worker_file_path)
            self.worker_file_map[worker_id] = worker_file_path
            
        logger.info(f"独立 Project 文件准备完成，共 {len(self.worker_file_map)} 个。")

    def _generate_tasks(self) -> List[Dict]:
        """
        根据 Setup 配置生成任务列表。
        """
        mode = self.setup.simulation_mode
        if mode == SimulationMode.DESIGN:
            if self.num_workers != 1:
                logger.warning("DESIGN 模式强制单进程。")
                self.num_workers = 1
            return []
            
        elif mode == SimulationMode.TOPOLOGY_MODELING:
            total = getattr(self.setup, 'total_iterations', 100)
            return [{'iteration': i} for i in range(total)]
            
        elif mode == SimulationMode.PARAMETRIC_MODELING:
            sweep_params = self.setup.sweep_params
            if isinstance(sweep_params, list):
                return sweep_params
            elif isinstance(sweep_params, dict):
                if not sweep_params:
                    return []
                keys, values = zip(*sweep_params.items())
                return [dict(zip(keys, combo)) for combo in itertools.product(*values)]
        return []

    def _restart_design_env(self) -> 'CSTDesignEnv':
        """
        重启 Design Environment 实例。
        防止仿真软件内存泄漏或状态异常，定期重启后台服务。
        """
        if not self.shared_design_env:
            return None
            
        try:
            self.shared_design_env.close_env()
        except Exception as e:
            logger.error(f"关闭 Design Env 时出错: {e}")
        finally:
            del self.shared_design_env

        logger.info("正在启动新的 Design Env 实例...")
        try:
            new_env = CSTDesignEnv(quiet=True)
            logger.info(f"新 Design Env 启动成功 (PID: {new_env.pid})")
            self.shared_design_env = new_env
            return new_env
        except Exception as e:
            logger.error(f"启动新 Design Env 时出错: {e}")
            raise RuntimeError("无法重启 Design Env")

    def _hdf5_writer_loop(self, data_queue: MPQueue):
        """
        HDF5 写入线程逻辑。
        在一个单独的线程中持续监听队列，将仿真结果写入 HDF5 文件。
        """
        saver = HDF5Saver()
        write_index = 0
        while True:
            try:
                item = data_queue.get()
                if item is None:
                    break
                result_data = item['result']
                unique_path = f"/sample_{write_index:06d}"
                try:
                    saver.append_to_h5(result_data, self.result_file_path, unique_path)
                    logger.info(f"HDF5 Writer: 成功写入 {unique_path} （按照仿真完成时间重新编号）")
                    write_index += 1
                except Exception as e:
                    logger.error(f"HDF5 Writer: 写入失败 {unique_path} （按照仿真完成时间重新编号）: {e}", exc_info=True)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"写入线程异常: {e}")
                break
        logger.info(f"HDF5 写入线程已退出，共写入 {write_index} 个样本")

    def _start_hdf5_writer(self, write_queue: MPQueue) -> threading.Thread:
        """
        启动 HDF5 写入线程。
        """
        writer_thread = threading.Thread(
            target=self._hdf5_writer_loop,
            args=(write_queue,),
            daemon=True
        )
        writer_thread.start()
        return writer_thread
    
    def run(self) -> Dict[str, str]:
        """
        执行调度。
        策略：每个批次独立运行，强制重启 CST 环境。
        """
        self._prepare_worker_files()
        all_tasks = self._generate_tasks()
        
        if not all_tasks:
            return {"status": "empty"}

        # 使用 Manager.Queue 保证跨进程通信稳定
        self.manager = multiprocessing.Manager()
        data_queue = self.manager.Queue()
        status_queue = self.manager.Queue()
        writer_thread = self._start_hdf5_writer(data_queue)

        # 状态监听线程：只负责打印 RUNNING 日志
        def monitor_status():
            while True:
                try:
                    msg = status_queue.get(timeout=1)
                    if msg is None:  # 收到 None 代表彻底结束信号
                        break
                    if msg['type'] == 'RUNNING':
                        logger.info(f"任务 [批次{msg['batch_idx']}-任务 ID {msg['task_idx']}] 开始运行")
                except:
                    continue

        monitor_thread = threading.Thread(target=monitor_status, daemon=True)
        monitor_thread.start()

        try:
            # 进入批次循环
            for batch_idx, batch in enumerate([all_tasks[i:i + self.batch_size] for i in range(0, len(all_tasks), self.batch_size)]):
                logger.info(f"--- 开始处理批次 {batch_idx} (任务数: {len(batch)}) ---")
                
                # 核心逻辑：每个批次都执行一次：重启环境 -> 运行批次 -> 销毁环境
                if not self._run_batch_with_fresh_env(batch, batch_idx, data_queue, status_queue):
                    logger.warning(f"批次 {batch_idx} 运行失败，跳过...")
                    continue
                    
            return self._finalize_run(data_queue, writer_thread)
            
        except Exception as e:
            logger.error(f"运行时发生异常: {e}", exc_info=True)
            return {"status": "exception"}
            
        finally:
            # 通知监听线程退出
            status_queue.put(None)
            monitor_thread.join(timeout=2)

            try:
                data_queue.put(None)
                writer_thread.join(timeout=2)
            except:
                pass
    
    def _run_batch_with_fresh_env(self, tasks: List[Dict], batch_idx: int, data_queue: multiprocessing.Queue, status_queue: multiprocessing.Queue) -> bool:
        setup_dict = self.setup.to_dict()
        worker_processes = []
        worker_queues = []
        
        try:
            # 1. 启动全新的 CST Design Environment
            logger.info(f"批次 {batch_idx}: 正在启动全新的 CST Design Environment...")
            self._restart_design_env()
            main_de_pid = self.shared_design_env.pid

            # 2. 启动 Worker 进程
            batch_semaphore = self.manager.Semaphore(self.num_workers)
            for wid in range(self.num_workers):
                project_file = self.worker_file_map[wid]
                task_queue = self.manager.Queue()
                worker_queues.append(task_queue)
                args = (wid, project_file, main_de_pid, status_queue, data_queue, self.base_runner_type, setup_dict, task_queue, batch_semaphore)
                p = Process(target=_global_simulation_worker, args=args)
                p.start()
                worker_processes.append(p)
                logger.info(f"Worker {wid} (PID: {p.pid}) 已启动")

            # --- 核心修复点：任务分发与计数逻辑 ---
            tasks_in_batch = len(tasks)
            
            # 1. 计算每个 Worker 应该分到多少任务
            # 例如 10 个任务，2 个 Worker -> Worker0: 任务0,2,4,6,8 | Worker1: 任务1,3,5,7,9
            worker_task_load = [[] for _ in range(self.num_workers)]
            for local_idx, task in enumerate(tasks):
                target_worker_id = local_idx % self.num_workers
                worker_task_load[target_worker_id].append((task, local_idx))

            # 2. 向每个 Worker 发送“任务列表”和“结束信号”
            # 这样 Worker 可以自己内部循环，不用主进程反复发
            for wid in range(self.num_workers):
                task_list_for_this_worker = worker_task_load[wid]
                # 发送 (任务数据, 批次ID, 任务ID) 的列表
                # 最后加一个 None 作为结束标志
                for task, task_id in task_list_for_this_worker:
                    worker_queues[wid].put((task, batch_idx, task_id))
                worker_queues[wid].put(None) # 发送结束信号，告诉 Worker “别等了，这批活干完了”

            # 3. 等待所有任务完成 (逻辑简化)
            # 现在我们只管数“收到多少个 FINISHED”
            finished_count = 0
            while finished_count < tasks_in_batch:
                try:
                    msg = status_queue.get(timeout=30)
                    if msg and msg['type'] == 'FINISHED':
                        finished_count += 1
                        task_id = msg['task_idx']
                        logger.info(f"批次 {batch_idx}: 任务 {task_id} 完成，当前进度: {finished_count}/{tasks_in_batch}")
                except queue.Empty:
                    # 超时检查：防止死锁
                    # 检查 Worker 进程是否还活着
                    if any(not p.is_alive() for p in worker_processes):
                        logger.error("检测到 Worker 进程意外退出")
                        return False
                    continue

            return True

        except Exception as e:
            logger.error(f"批次 {batch_idx} 执行出错: {e}")
            return False
            
        finally:
            # 4. 资源清理 (Worker 已经收到 None 自行退出，这里主要是防呆)
            for p in worker_processes:
                if p.is_alive():
                    p.join(timeout=10)
            if self.shared_design_env:
                self.shared_design_env.close_env()
    
    def _finalize_run(self, data_queue: MPQueue, writer_thread: threading.Thread) -> Dict[str, str]:
        """
        清理工作。
        """
        # 停止 HDF5 写入线程
        logger.info("正在停止 HDF5 写入线程...")
        data_queue.put(None)
        writer_thread.join(timeout=5)
            
        total_elements = HDF5Saver.count_total_elements(self.result_file_path)
        logger.info(f"仿真全部结束，共收集样本数: {total_elements}")
        
        return { 
            "status": "success", 
            "result_file": self.result_file_path, 
        }