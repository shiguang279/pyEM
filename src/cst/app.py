import time
import psutil  
from pathlib import Path
from typing import Optional
import cst.interface as csti
from src.core.app import SimDesignEnv, SimProject
from src.cst.vba import CSTVBA
from src.utils.logger import logger

class CSTDesignEnv(SimDesignEnv):
    """
    CST 专用环境类。实现了具体的 initialize 逻辑。
    """

    def __init__(self, pid: Optional[int] = None, quiet: bool = True):
        super().__init__(quiet=quiet)
        self.cst_de = None
        self.pid = pid
        self.initialize(pid=pid)
    
    def __getstate__(self):
        """
        序列化钩子：定义对象在保存（或跨进程传输）时需要保留哪些状态。
        """
        return {'pid': self.pid, 'quiet': self.quiet}

    def __setstate__(self, state):
        """
        反序列化钩子：在子进程中利用保存的状态重新恢复对象。
        """
        self.pid = state['pid']
        self.quiet = state['quiet']
        self.initialize(pid=self.pid)

    def initialize(self, pid: Optional[int] = None, **kwargs) -> bool:
        """
        实现父类的抽象方法。
        在这里真正执行 CST 的启动或连接逻辑。
        """
        # 允许传入参数覆盖构造时的参数
        if pid is None:
            pid = self.pid  

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
            if self.quiet and self.cst_de:
                self.cst_de.set_quiet_mode(True)

            self._is_initialized = True
            return True

        except Exception as e:
            logger.error(f"CST DesignEnvironment 初始化失败: {e}", exc_info=True)
            self._is_initialized = False
            raise RuntimeError(f"无法初始化 CST 环境: {e}")

    def close_env(self, force_kill: bool = True, timeout: int = 15) -> None:
        logger.debug("正在执行 CST DesignEnvironment 安全关闭流程...")
        if hasattr(self, 'cst_de') and self.cst_de is not None:
            try:
                self.cst_de.close()
                logger.debug("已发送 CST DesignEnvironment 关闭指令。")

                # 等待进程真正退出
                start_time = time.time()
                while time.time() - start_time < timeout:
                    try:
                        proc = psutil.Process(self.pid)
                        if not proc.is_running():
                            break
                    except psutil.NoSuchProcess:
                        break
                    time.sleep(0.5)
                else:
                    # 超时仍未退出
                    if force_kill:
                        logger.warning(f"CST 进程 (PID={self.pid}) 未按时退出，正在强制终止...")
                        try:
                            proc.kill()
                            proc.wait(timeout=5)
                            logger.debug("CST 进程已被强制终止。")
                        except Exception as ke:
                            logger.error(f"强制终止 CST 进程失败: {ke}")
            except Exception as e:
                logger.warning(f"关闭设计环境时发生异常: {e}")
            finally:
                self.cst_de = None
                self.pid = None
                self._is_initialized = False
                logger.debug("CST DesignEnvironment 资源已完全释放。")
   

class CSTProject(SimProject):
    """
    CST 专用项目类。
    """
    def __init__(self, design_env_instance: CSTDesignEnv):
        super().__init__(design_env_instance)
        self.vba = None # VBA 接口实例
        self.file_path = None

    def open(self, file_path: str) -> None:
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"无法打开文件，文件不存在: {file_path}")

        logger.debug(f"正在打开项目: {file_path}")
        
        # 1. 关闭旧项目
        if self._project_handle is not None:
            logger.debug("检测到旧句柄，正在底层关闭它...")
            try:
                self._project_handle.close()
            except Exception as e:
                logger.warning(f"关闭旧项目时发生异常（可忽略）: {e}")
            finally:
                self._project_handle = None
                self.vba = None

        # 2. 打开新项目
        try:
            self._project_handle = self.design_env.cst_de.open_project(file_path)
            logger.debug(f"CST 底层项目打开成功: {file_path}")
        except Exception as e:
            logger.error(f"CST 底层打开项目失败: {e}")
            raise

        # 3. 绑定 VBA 接口
        try:
            if self._project_handle is None:
                raise RuntimeError("Project 句柄为空，无法初始化 VBA")
            self.vba = CSTVBA(self._project_handle)
            self.file_path = file_path
            logger.debug("VBA 接口绑定成功！")
        except Exception as vba_err:
            logger.error(f"致命错误：VBA 接口绑定失败！错误信息: {vba_err}")
            raise

    def new_mws(self) -> None:
        """新建 MWS 项目"""
        if self._project_handle is None:
            self._project_handle = self.design_env.cst_de.new_mws()
            self.vba = CSTVBA(self._project_handle)
            self.file_path = None
            logger.debug("已创建新的 MWS 项目")
        else:
            logger.warning("项目已存在，跳过新建。")

    def save(self, prj_file: str, include_results: bool = False) -> None:
        if self._project_handle is None:
            raise RuntimeError("CST 项目句柄为空")
        
        file_path = Path(prj_file)
        if not file_path.parent.exists():
            file_path.parent.mkdir(parents=True, exist_ok=True)

        self._project_handle.save(str(file_path), include_results=include_results, allow_overwrite=True)
        self.file_path = file_path
        logger.debug(f"项目已保存: {prj_file}")

    def run_solver(self) -> None:
        if self._project_handle is None:
            raise RuntimeError("项目句柄未初始化，无法运行仿真。")
        
        logger.debug(">>> 正在启动 CST 求解器 ...")
        try:
            self._project_handle.model3d.run_solver()
            logger.info(">>> CST 求解器计算完成。")
        except Exception as e:
            logger.error(f"求解器运行失败: {e}")
            raise

    def _pre_run_cleanup(self):
        """
        重写父类的清理钩子，用于 CST 特有的操作。
        """
        if self.vba:
            logger.debug(">>> 正在清除旧的仿真结果 (重置 Run ID)...")
            self.vba.delete_all_results()
        else:
            logger.warning("VBA 接口未就绪，无法清除旧结果")

    def close(self) -> None:
        logger.debug("正在关闭当前 CST 项目...")
        if self._project_handle is not None:
            try:
                self._project_handle.close()
                logger.debug("CST Project closed successfully.")
            except Exception as e:
                logger.warning(f"关闭项目时发生异常 (可能已关闭): {e}")
            finally:
                self._project_handle = None
                self.vba = None
                self.file_path = None
        else:
            logger.debug("当前没有打开的项目。")