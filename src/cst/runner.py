# -*- coding: utf-8 -*-
"""
CST Studio Suite 仿真运行器模块 (CSTRunner)

该模块负责处理与 CST 软件的底层交互，包括工程生命周期管理、
参数同步、自动化建模、求解器控制及结果提取。
"""

import os
import time
import traceback
from typing import Dict, Any, Optional, List, Callable

from src.core.runner import SimRunner, register_runner, RunMode, SimulationMode
from src.cst.flow import CSTFlow
from src.cst.app import CSTDesignEnv, CSTProject
from src.cst.result_extractor import CSTResultExtractor
from src.cst.vba import CSTVBA  
from src.cst.structure import CSTStructureBuilder 
from src.utils.logger import logger


class CSTRunner(SimRunner):
    """
    CST 仿真运行器实现类（字典驱动版）。

    继承自 SimRunner 基类，专门用于编排 CST 软件的自动化工作流。
    所有配置参数均通过字典传递，不再依赖 SimSetup 类实例。
    """

    runner_name = "CST"

    def __init__(
        self,
        output_dir: str = "output",
        run_mode: RunMode = RunMode.SAVE_AND_RUN,
        simulation_mode: SimulationMode = SimulationMode.DESIGN
    ):
        """
        初始化 CST 运行器。

        Args:
            output_dir: 仿真结果的输出目录路径。
            run_mode: 运行模式枚举（如 SAVE_AND_RUN, SAVE_ONLY）。
            simulation_mode: 仿真策略枚举（如 DESIGN, PARAMETRIC_MODELING）。
            shared_design_env: 外部传入的 CST 应用程序实例，用于多进程共享环境。
        """
        # 强制要求通过 set_shared_design_env 方法注入
        super().__init__(output_dir, run_mode, simulation_mode)
        self.design_env_instance = None
        self.use_shared_design_env = False
        self.builder: Optional[CSTStructureBuilder] = None
        self.strategy_map = {
            SimulationMode.DESIGN: self._execute_design,
            SimulationMode.PARAMETRIC_MODELING: self._execute_parametric_sweep,
            SimulationMode.TOPOLOGY_MODELING: self._execute_topology_modeling,
        }
        # 持有的 Project 实例
        self.current_project: CSTProject = None

    def get_software_name(self) -> str:
        """返回当前运行器支持的软件名称。"""
        return "CST"

    @classmethod
    def start_design_environment(cls):
        """启动 CST 设计环境"""
        return CSTDesignEnv(quiet=True)

    def create_project(self, design_env_instance: CSTDesignEnv) -> CSTProject:
        """
        实例化一个新的 CST 工程对象。

        Args:
            design_env_instance: CST 设计环境接口。

        Returns:
            CSTProject: 新创建的工程实例。
        """
        self.current_project = CSTProject(design_env_instance)
        return self.current_project
    
    def open_project(self, design_env_instance: CSTDesignEnv, project_file: str) -> CSTProject:
        """
        强制打开指定的 CST 工程文件（极简版）。
        
        Args:
            design_env_instance: CST 设计环境实例。
            project_file: .cst 文件路径。
            
        Returns:
            CSTProject: 打开的工程实例。
            
        Raises:
            FileNotFoundError: 文件不存在时。
        """
        if not os.path.exists(project_file):
            raise FileNotFoundError(f"工程文件不存在: {project_file}")

        if self.current_project:
            self.current_project.close()
            self.current_project = None

        self.design_env_instance = design_env_instance
        self.current_project = CSTProject(design_env_instance)
        self.current_project.open(project_file) 
        
        return self.current_project
    
    def close_project(self) -> None:
        """
        仅关闭当前打开的 Project。
        这是 Worker 退出时必须调用的方法。
        """
        if self.current_project:
            logger.debug("CSTRunner 正在关闭当前 Project...")
            self.current_project.close() 
            self.current_project = None
        else:
            logger.debug("CSTRunner 中没有活动的 Project 需要关闭。")
    
    def run(self, setup_dict: Dict = None, params: Optional[Dict[str, Any]] = None, project_file: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        执行仿真流程。
        """
        if not setup_dict:
            return {"status": "error", "message": "setup_dict is missing"}

        # 1. 获取模式
        mode = setup_dict.get('simulation_mode')
        logger.info(f">>> CSTRunner.run | 模式: {mode}")

        # 2. 查找对应的处理函数
        handler = self.strategy_map.get(mode)
        if not handler:
            return {"status": "error", "message": f"未知的仿真模式: {mode}"}

        try:
            if mode == SimulationMode.DESIGN:
                return handler(setup_dict, project_file)
            elif mode == SimulationMode.PARAMETRIC_MODELING:
                return handler(setup_dict, params, project_file)
            elif mode == SimulationMode.TOPOLOGY_MODELING:
                return handler(setup_dict, project_file)
        except Exception as e:
            logger.error(f"执行 {mode} 失败: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}
    
    def _retry_on_failure(
        self, 
        func: Callable[[], Any], 
        max_retries: int = 3
    ) -> tuple[bool, Any]:
        """
        通用重试包装器：执行函数，如果失败则强制重置 Project 句柄并重试。
        """
        attempt = 0
        while attempt < max_retries:
            attempt += 1
            try:
                # 执行传入的函数
                return True, func()
            
            except Exception as e:
                logger.warning(f"执行失败 (尝试 {attempt}/{max_retries}): {e}")
                
                if attempt < max_retries:
                    # 1. 强制丢弃句柄，防止句柄污染导致后续操作失败
                    logger.debug("强制丢弃旧的 Project 句柄...")
                    self.current_project = None
                    
                    # 2. 等待系统释放文件锁和 CST 内部进程清理
                    time.sleep(3)
                    
                else:
                    logger.error("达到最大重试次数，任务彻底失败。")
                    return False, e
        
        return False, None

    def _execute_design(
        self, setup_dict: Dict[str, Any], project_file: str
    ) -> Optional[Dict[str, Any]]:
        """
        执行设计模式流程（支持 GUI 交互循环）。

        Args:
            cst_project: CST 工程对象。
            setup_dict: 配置字典。
            project_file: 项目文件路径。

        Returns:
            执行结果字典。
        """
        logger.info("执行设计模式...")

        # 1. 路径准备
        design_name = setup_dict.get("design_name", "DefaultDesign")
        project_file = os.path.abspath(project_file if project_file else os.path.join(self.output_dir, f"{design_name}.cst"))

        # 2. 工程初始化
        if os.path.exists(project_file):
            logger.info(f"打开已存在工程: {project_file}")
            self.current_project.open(project_file)
        else:
            logger.info(f"创建新工程: {project_file}")
            self.current_project.new_mws()

        # 3. 初始化 Flow 与参数同步
        flow = CSTFlow(builder=self.builder, output_dir=self.output_dir)
        
        # 从字典读取参数并同步
        sim_params = setup_dict.get("sim_params", {})
        flow.sync_parameters_to_software(sim_params)

        # 4. 注入 Designer
        designer = setup_dict.get("designer")
        if designer:
            flow.inject_designer(designer)

        # 5. GUI 交互循环：让用户手动操作，直到退出
        while True:
            logger.info(">>> 请在 CST GUI 界面中进行手动操作，完成后请在控制台输入 'y' 继续自动化建模，输入 'q' 退出操作：")
            try:
                user_input = input("是否继续自动化建模？(y/n): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                # 处理终端强制退出或文件结束符
                user_input = 'q'

            if user_input in ['q', 'quit', 'n', 'no']:
                logger.info("用户选择退出 GUI 交互模式，准备保存并运行仿真。")
                break
            elif user_input in ['y', 'yes', '']:
                logger.info("用户确认继续，开始执行自动化建模...")
                try:
                    flow.execute_automated_modeling()
                    logger.info("自动化建模完成。你可以继续在 GUI 中调整，或退出进行仿真。")
                except Exception as e:
                    logger.error(f"自动化建模步骤执行失败: {e}", exc_info=True)
                    # 建模失败不中断循环，允许用户修正后重试
            else:
                logger.warning(f"输入无效：'{user_input}'，请输入 'y' 继续或 'q' 退出。")

        # 6. 运行仿真
        try:
            self.current_project.run_simulation(project_file)
        except Exception as e:
            logger.error(f"保存或运行仿真失败: {e}", exc_info=True)
            return {"status": "failed", "message": f"仿真运行失败: {e}"}

        # 7. 提取结果
        try:
            extractor = CSTResultExtractor(self.current_project, setup_dict=setup_dict)
            extracted_data = extractor.execute_export()
            return {"status": "success", "path": project_file, **extracted_data}
        except Exception as e:
            logger.error(f"结果数据提取失败: {e}", exc_info=True)
            return {"status": "failed", "message": f"结果提取失败: {e}"}

    def _execute_parametric_sweep(
        self,
        setup_dict: Dict[str, Any],
        params: Dict[str, Any],
        project_file: str,
    ) -> Optional[Dict[str, Any]]:
        """
        执行参数化扫描（单点模式）。
        """
        logger.info(f">>> 执行扫描参数：{params}")

        try:

            # 1. 同步参数
            for name, value in params.items():
                try:
                    vba_cmd = f'StoreParameter("{name}", "{value}")'
                    self.current_project.vba.execute(f"{vba_cmd}")
                except Exception as e:
                    # 捕获单个参数设置失败的异常
                    error_msg = f"设置参数 {name}={value} 失败: {e}"
                    logger.error(error_msg)
                    return {"status": "failed", "message": error_msg, "params": params, "error_type": "Param_Setup"}

            # 2. 重建模型
            logger.debug(">>> 正在根据新参数重建模型...")
            self.current_project.vba.execute("RebuildOnParametricChange(True, False)")

            # 3. 运行仿真
            project_file = os.path.abspath(project_file)
            self.current_project.run_simulation(project_file)

            # 4. 提取数据
            extractor = CSTResultExtractor(self.current_project, setup_dict=setup_dict)
            result = extractor.execute_export()

            return {"status": "success", "params": params, **result}

        except Exception as e:
            # 捕获整体任务的严重异常（如 CST 崩溃、连接断开等）
            error_trace = traceback.format_exc()
            logger.error(f"执行参数化扫描时发生严重异常: {e}\n{error_trace}")
            
            # 关键修改：不再向上抛出异常，而是返回包含详细错误信息的字典
            # 这样 Worker 进程不会崩溃，主进程也能收到具体的参数和报错堆栈
            return {
                "status": "failed", 
                "message": f"仿真任务执行失败: {e}", 
                "params": params, 
                "full_traceback": error_trace,
                "error_type": "Critical_Runtime_Error"
            }

    def _execute_topology_modeling(
        self, 
        setup_dict: Dict[str, Any], 
        project_file: str
    ) -> Optional[Dict[str, Any]]:
        """
        执行拓扑建模流程。
        """
        logger.debug(">>> 执行模式：拓扑建模 (TOPOLOGY_MODELING)")

        # 提前提取任务标识和设计上下文，方便在报错时回传
        task_id = setup_dict.get('task_id', os.path.basename(project_file))
        design_context = setup_dict.get('design_context', {})

        try:
            # 1. 建模流程
            try:
                flow = CSTFlow(builder=self.builder, output_dir=self.output_dir)
                sim_params = setup_dict.get("sim_params", {})
                flow.sync_parameters_to_software(sim_params)

                designer = setup_dict.get("designer")
                if not designer:
                    raise ValueError("配置中缺少 designer 对象")
                flow.inject_designer(designer)
                flow.execute_automated_modeling()
            except Exception as e:
                error_msg = f"拓扑建模流程执行失败: {e}"
                logger.error(error_msg)
                return {
                    "status": "failed", 
                    "message": error_msg, 
                    "task_id": task_id, 
                    "design_context": design_context,
                    "stage": "MODELING" # 标记错误发生的具体阶段
                }

            # 2. 运行仿真
            try:
                project_file = os.path.abspath(project_file)
                self.current_project.run_simulation(project_file)
            except Exception as e:
                error_msg = f"仿真运行失败: {e}"
                logger.error(error_msg)
                return {
                    "status": "failed", 
                    "message": error_msg, 
                    "task_id": task_id,
                    "stage": "SIMULATION"
                }

            # 3. 提取数据
            try:
                extractor = CSTResultExtractor(self.current_project, setup_dict=setup_dict)
                result = extractor.execute_export()
                return {"status": "success", "task_id": task_id, **result}
            except Exception as e:
                error_msg = f"结果数据提取失败: {e}"
                logger.error(error_msg)
                return {
                    "status": "failed", 
                    "message": error_msg, 
                    "task_id": task_id,
                    "stage": "EXTRACTION"
                }

        except Exception as e:
            # 捕获整体任务的严重异常（如 CST 崩溃、连接断开等）
            error_trace = traceback.format_exc()
            logger.error(f"执行拓扑建模时发生严重异常: {e}\n{error_trace}")
            
            # 关键修改：不再抛出 RuntimeError，而是返回包含任务ID和上下文的错误字典
            return {
                "status": "failed", 
                "message": f"拓扑建模任务执行失败: {e}", 
                "task_id": task_id,
                "design_context": design_context,
                "full_traceback": error_trace,
                "stage": "CRITICAL"
            }
        

# 注册 Runner 到工厂
register_runner("CST", CSTRunner)