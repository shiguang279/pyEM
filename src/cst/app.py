# -*- coding: utf-8 -*-
"""
cst/app.py
"""

import time
from pathlib import Path
from typing import Optional
import cst.interface as csti
from src.cst.vba import CSTVBA
from src.utils.logger import logger

class CSTDesignEnv:
    """
    CST 设计环境类。
    支持两种模式：
    1. 新建模式 (默认): 启动一个新的 CST DesignEnvironment。
    2. 连接模式: 连接到指定的已有进程 PID。
    """

    def __init__(self, pid: Optional[int] = None, quiet: bool = True):
        """
        初始化 CST DesignEnvironment。
        
        Args:
            pid (int, optional): 如果提供 PID，则连接到该现有进程；
                                 如果为 None，则启动一个新进程。
            quiet (bool): 是否开启静默模式。
        """
        self.quiet = quiet
        self.cst_de = None
        self.pid = None

        try:
            if pid is not None:
                # --- 模式 1: 连接到现有进程 ---
                logger.debug(f"正在连接到现有的 CST DesignEnvironment (PID={pid})...")
                self.cst_de = csti.DesignEnvironment.connect(pid)
                self.pid = pid
                logger.debug(f"成功连接到 PID={pid}")
            else:
                # --- 模式 2: 启动新进程 ---
                logger.debug(f"正在启动新的 CST DesignEnvironment 实例...")
                self.cst_de = csti.DesignEnvironment()
                self.pid = self.cst_de.pid()
                logger.debug(f"CST 实例已启动 (PID={self.pid})")

            # 统一设置静默模式
            if quiet:
                self.cst_de.set_quiet_mode(True)

        except Exception as e:
            logger.error(f"CST DesignEnvironment 初始化失败: {e}", exc_info=True)
            raise RuntimeError(f"无法初始化 CST 环境: {e}")

    @staticmethod
    def new(quiet: bool = True) -> 'CSTDesignEnv':
        """语法糖：显式创建一个新环境"""
        return CSTDesignEnv(quiet=quiet)

    @staticmethod
    def connect(pid: int, quiet: bool = True) -> 'CSTDesignEnv':
        """语法糖：显式连接到一个现有环境"""
        return CSTDesignEnv(pid=pid, quiet=quiet)

    def close_env(self) -> None:
        """安全关闭 CST DesignEnvironment 进程。"""
        logger.debug("正在执行 CST DesignEnvironment 安全关闭流程...")
        
        if self.cst_de is not None:
            try:
                self.cst_de.close()
                logger.debug("CST DesignEnvironment closed successfully.")
            except Exception as e:
                logger.warning(f"关闭设计环境时发生异常: {e}")
            finally:
                self.cst_de = None
                
        logger.debug("CST DesignEnvironment 资源已完全释放。")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_env()
        return False

class CSTProject:
    """
    CST 项目类，负责管理单个 CST 项目。

    职责：
    1. 项目生命周期管理 (打开/关闭)。
    2. 基础文件操作 (保存)。
    3. 求解器控制 (运行仿真)。
    4. 组合功能模块 (持有 vba 实例)。
    """

    def __init__(self, design_env_instance: 'CSTDesignEnv'):
        """
        初始化项目上下文，关联到一个 CST Design Environment 实例。

        Args:
            design_env_instance (CSTDesignEnv): 一个活跃的 CST Design Environment 实例。
        """
        self.design_env = design_env_instance
        self.project = None
        # VBA 模块实例，将在项目打开或新建后绑定
        self.vba = None
        logger.debug(f"Project Context initialized for env PID {self.design_env.pid}")

    def open(self, file_path: str) -> None:
        """
        打开现有的 CST 项目文件。

        Args:
            file_path (str): 项目文件的完整路径。
        
        Raises:
            FileNotFoundError: 如果文件不存在。
        """
        if not Path(file_path).exists():
            raise FileNotFoundError(f"无法打开文件，文件不存在: {file_path}")
            
        logger.debug(f"正在打开项目: {file_path}")
        
        try:
            if self.project is not None:
                logger.debug("检测到旧句柄，强制丢弃...")
                self.project = None
                self.vba = None
            
            # 2. 使用 DesignEnvironment 打开项目
            self.project = self.design_env.cst_de.open_project(file_path)
            
            # 3. 更新 VBA 接口（因为 project 对象变了，必须重新绑定）
            self.vba = CSTVBA(self.project)
                
            logger.debug(f"项目打开成功: {file_path}")
            
        except Exception as e:
            logger.error(f"打开项目失败: {e}")
            raise

    def new_mws(self) -> None:
        """
        在当前 DesignEnvironment 中新建一个 MWS 项目。
        """
        if self.project is None:
            self.project = self.design_env.cst_de.new_mws()
            self.vba = CSTVBA(self.project)
            logger.debug("已创建新的 MWS 项目")
        else:
            logger.warning("项目已存在，跳过新建。")
    
    def filename(self):
        """
        获取当前项目完整路径文件名。
        """
        if self.project is None:
            return None
        return self.project.filename()

    def save(self, prj_file: str, include_results: bool = False) -> None:
        """
        保存当前 CST 项目。如果失败直接抛出异常。
        """
        if self.project is None:
            raise RuntimeError("CST 项目句柄为空")

        file_path = Path(prj_file)
        
        # 确保保存目录存在
        if not file_path.parent.exists():
            file_path.parent.mkdir(parents=True, exist_ok=True)

        # 直接调用 API，如果出错让它自然抛出异常
        self.project.save(str(file_path), include_results=include_results, allow_overwrite=True)
        
        logger.debug(f"项目已保存: {prj_file}")
    
    def start_solver(self) -> None:
        """
        仅启动求解器进行计算。
        """
        if self.project is None:
            raise RuntimeError("项目句柄未初始化，无法运行仿真。")

        logger.debug(">>> 正在启动 CST 求解器 ...")
        try:
            # 调用底层接口运行求解器
            self.project.model3d.run_solver()
            logger.debug(">>> CST 求解器计算完成。")
        except Exception as e:
            logger.error(f"求解器运行失败: {e}")
            raise

    def run_simulation(self, prj_file: str) -> None:
        """
        执行全自动化仿真流程。
        
        核心逻辑：
        1. 强制重置：清除旧结果，确保 Run ID 中只有最新的数据。
        2. 模型保护：先保存纯净模型，防止计算崩溃导致建模数据丢失。
        3. 求解计算：调用底层求解器并阻塞等待。
        4. 结果归档：计算完成后，将结果写入文件。

        Args:
            prj_file (str): CST 项目文件的完整路径（例如: "D:/Projects/antenna_v1.cst"）。
        """
        # ==================================================
        # 0. 前置检查
        # ==================================================
        if self.project is None:
            raise RuntimeError("仿真流程终止：项目句柄 (Project Handle) 未初始化。")
        
        logger.debug(f"仿真开始运行: {prj_file}")
        
        try:
            # ==================================================
            # 阶段 1: 模型持久化 (Pre-Solve Save)
            # ==================================================
            logger.debug(">>> 正在保存/加载仿真模型 (建立 Project 引用)...")
            self.save(prj_file, include_results=False)

            # ==================================================
            # 阶段 2: 环境重置 (Safe to call now)
            # ==================================================
            logger.debug(">>> 正在清除旧的仿真结果 (重置 Run ID)...")
            self.vba.delete_all_results()

            # ==================================================
            # 3. 求解器执行
            # ==================================================
            logger.info("正在启动求解器进行计算...")
            self.start_solver()

            # ==================================================
            # 4. 结果归档
            # ==================================================
            logger.debug("正在保存仿真结果数据...")
            self.save(prj_file, include_results=True)
            
            logger.debug(f"仿真流程执行成功: {prj_file}")

        except Exception as e:
            logger.error(f"仿真流程执行失败: {e}", exc_info=True)
            raise

    def close_project(self) -> None:
        """
        关闭当前打开的 CST 项目，但保留关联的 CST DesignEnvironment 进程。
        """
        logger.debug("正在关闭当前 CST 项目...")
        if self.project is not None:
            try:
                self.project.close()
                logger.debug("CST Project closed successfully.")
            except Exception as e:
                logger.warning(f"关闭项目时发生异常 (可能已关闭): {e}")
            finally:
                self.project = None
                # 关闭项目后，VBA 实例也失效了，需要重置
                self.vba = None
        else:
            logger.debug("当前没有打开的项目。")

    def __enter__(self):
        """进入上下文时执行，返回 self。"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文时执行，确保项目被关闭。"""
        self.close_project()
        return False