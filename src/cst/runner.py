# -*- coding: utf-8 -*-
"""
CST Studio Suite 仿真运行器模块 (CSTRunner)

该模块负责处理与 CST 软件的底层交互，包括工程生命周期管理、
参数同步、自动化建模、求解器控制及结果提取。
"""

import os
import time
from typing import Dict, Any, Optional, List, Callable

from src.core.sim_runner import SimRunner, register_runner, RunMode, SimulationMode
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
        simulation_mode: SimulationMode = SimulationMode.DESIGN,
        shared_design_env: Optional[CSTDesignEnv] = None,
    ):
        """
        初始化 CST 运行器。

        Args:
            output_dir: 仿真结果的输出目录路径。
            run_mode: 运行模式枚举（如 SAVE_AND_RUN, SAVE_ONLY）。
            simulation_mode: 仿真策略枚举（如 DESIGN, PARAMETRIC_MODELING）。
            shared_design_env: 外部传入的 CST 应用程序实例，用于多进程共享环境。
        """
        super().__init__(output_dir, run_mode, simulation_mode)
        self.design_env_instance = shared_design_env
        self.use_shared_design_env = shared_design_env is not None
        self.builder: Optional[CSTStructureBuilder] = None
        self.strategy_map = {
            SimulationMode.DESIGN: self._execute_design,
            SimulationMode.PARAMETRIC_MODELING: self._execute_parametric_sweep,
            SimulationMode.TOPOLOGY_MODELING: self._execute_topology_modeling,
        }

    def get_software_name(self) -> str:
        """返回当前运行器支持的软件名称。"""
        return "CST"

    def _create_project(self, design_env_instance: CSTDesignEnv) -> CSTProject:
        """
        实例化一个新的 CST 工程对象。

        Args:
            design_env_instance: CST 设计环境接口。

        Returns:
            CSTProject: 新创建的工程实例。
        """
        return CSTProject(design_env_instance)

    def _open_project_with_shared_env(
        self, shared_design_env: CSTDesignEnv, project_file: str
    ) -> CSTProject:
        """
        在共享环境中打开指定的工程文件。

        Args:
            shared_design_env: 共享的 CST 设计环境。
            project_file: 目标工程文件的路径。

        Returns:
            CSTProject: 打开的工程实例。
        """
        project = CSTProject(shared_design_env)
        logger.debug(f"使用共享环境打开项目: {project_file}")
        project.open(project_file)
        return project

    def run(self, project_instance: CSTProject, setup_dict: Dict = None, 
            params: Optional[Dict[str, Any]] = None, project_file: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """执行仿真流程。

        Args:
            project_instance: 由外部调度器传入的已激活项目实例。
            params: 仿真参数字典。
            project_file: 项目文件路径，用于保存结果。

        Returns:
            包含执行状态和结果的字典。
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
                return handler(project_instance, setup_dict, setup_dict)
            elif mode == SimulationMode.PARAMETRIC_MODELING:
                return handler(project_instance, setup_dict, params, project_file)
            elif mode == SimulationMode.TOPOLOGY_MODELING:
                return handler(project_instance, setup_dict, project_file)
        except Exception as e:
            logger.error(f"执行 {mode} 失败: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}
    
    def _retry_on_failure(
        self, 
        cst_project: CSTProject, 
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
                    
                    # 1. 强制丢弃句柄
                    logger.debug("强制丢弃旧的 Project 句柄...")
                    cst_project.project = None
                    cst_project.vba = None
                    
                    # 2. 等待系统释放文件锁和 CST 内部进程清理
                    time.sleep(2)
                    
                else:
                    logger.error("达到最大重试次数，任务彻底失败。")
                    return False, e
        
        return False, None

    def _execute_design(
        self, cst_project: CSTProject, setup_dict: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        执行设计模式流程。

        Args:
            cst_project: CST 工程对象。
            setup_dict: 配置字典。

        Returns:
            执行结果字典。
        """
        logger.info("执行设计模式...")

        if cst_project is None:
            logger.error("Project 对象为空，无法继续。")
            return {"status": "error", "message": "Project object is None."}

        # 1. 路径准备
        design_name = setup_dict.get("design_name", "DefaultDesign")
        cst_file_path = os.path.abspath(os.path.join(self.output_dir, f"{design_name}.cst"))

        # 2. 工程初始化
        if os.path.exists(cst_file_path):
            logger.info(f"打开已存在工程: {cst_file_path}")
            cst_project.open(cst_file_path)
        else:
            logger.info(f"创建新工程: {cst_file_path}")
            cst_project.new_mws()

        # 3. 初始化 Flow 与参数同步
        vba = cst_project.vba
        flow = CSTFlow(builder=self.builder, output_dir=self.output_dir)
        
        # 从字典读取参数并同步
        sim_params = setup_dict.get("sim_params", {})
        flow.sync_parameters_to_software(sim_params)

        # 4. 注入 Designer
        designer = setup_dict.get("designer")
        if designer:
            flow.inject_designer(designer)
            flow.execute_automated_modeling()

        # 5. 保存并运行
        cst_project.save(cst_file_path, include_results=False)
        cst_project.run_simulation(cst_file_path)

        # 6. 提取结果
        extractor = CSTResultExtractor(cst_project, setup_dict=self.setup_dict)
        extracted_data = extractor.execute_export()

        return {"status": "success", "path": cst_file_path, **extracted_data}

    def _execute_parametric_sweep(
        self,
        cst_project: CSTProject,
        setup_dict: Dict[str, Any],
        params: Dict[str, Any],
        project_file: str,
    ) -> Optional[Dict[str, Any]]:
        """
        执行参数化扫描（单点模式）。
        """
        logger.info(f">>> 执行扫描参数：{params}")

        # 初始检查（为了 VBA 初始化）
        if cst_project.project is None:
            logger.debug(f"正在初始化并打开项目文件: {project_file}")
            cst_project.open(project_file)

        # --- 定义具体的业务逻辑 ---
        def task_logic():
            # 确保项目已打开
            if cst_project.project is None:
                logger.debug("检测到项目未打开（重试模式），正在重新打开...")
                cst_project.open(project_file)
            # 确保 VBA 已绑定（依赖 open 方法中的 self.vba = CSTVBA(...)）
            if cst_project.vba is None:
                raise RuntimeError("VBA 接口初始化失败，请检查 CST 环境。")

            # 1. 同步参数
            for name, value in params.items():
                vba_cmd = f'StoreParameter("{name}", "{value}")'
                cst_project.vba.execute(f"{vba_cmd}")

            # 2. 重建模型
            cst_project.vba.execute("RebuildOnParametricChange(True, False)")

            # 3. 运行仿真
            abs_project_file = os.path.abspath(project_file)
            cst_project.run_simulation(prj_file=abs_project_file)

            # 4. 提取数据
            extractor = CSTResultExtractor(cst_project, setup_dict=setup_dict)
            return extractor.execute_export()

        # --- 执行重试逻辑 ---
        success, result = self._retry_on_failure(cst_project, task_logic)

        if success:
            return {"params": params, **result}
        else:
            return {"params": params, "status": "error", "message": str(result)}

    def _execute_topology_modeling(
        self, 
        cst_project: CSTProject, 
        setup_dict: Dict[str, Any], 
        project_file: str
    ) -> Optional[Dict[str, Any]]:
        """
        执行拓扑建模流程。
        """
        logger.debug(">>> 执行模式：拓扑建模 (TOPOLOGY_MODELING)")
        # 初始检查（为了 VBA 初始化）
        if cst_project.project is None:
            logger.debug(f"正在初始化并打开项目文件: {project_file}")
            cst_project.open(project_file)

        # --- 定义具体的业务逻辑 ---
        def task_logic():
            # 确保项目已打开
            if cst_project.project is None:
                logger.debug("检测到项目未打开（可能是重试），正在重新打开...")
                cst_project.open(project_file)
            
            # 确保 VBA 已绑定
            # 依赖 open 方法中的 self.vba = CSTVBA(self.project)
            if cst_project.vba is None:
                raise RuntimeError("VBA 接口未初始化，无法执行建模流程。")

            # 1. 建模流程
            flow = CSTFlow(builder=self.builder, output_dir=self.output_dir)
            sim_params = setup_dict.get("sim_params", {})
            flow.sync_parameters_to_software(sim_params)

            designer = setup_dict.get("designer")
            if not designer:
                raise ValueError("配置中缺少 designer 对象")
            flow.inject_designer(designer)
            flow.execute_automated_modeling()

            # 2. 运行仿真
            absolute_project_file = os.path.abspath(project_file)
            # run_simulation 内部通常会处理打开/激活项目，但为了保险，依赖上面的 open 逻辑
            
            cst_project.run_simulation(prj_file=absolute_project_file)

            # 3. 提取数据
            extractor = CSTResultExtractor(cst_project, setup_dict=self.setup_dict)
            return extractor.execute_export()

        # --- 执行重试逻辑 ---
        success, result = self._retry_on_failure(cst_project, task_logic)

        if success:
            return result
        else:
            return None

# 注册 Runner 到工厂
register_runner("CST", CSTRunner)