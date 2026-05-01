# src/utils/logger.py
from pathlib import Path
from .logging_setup import setup_logger
import multiprocessing

# 定位工程根目录和日志目录
PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = PROJECT_ROOT / "logs"

# 自动判断当前是主进程还是 Worker 子进程
current_process = multiprocessing.current_process()
if current_process.name == 'MainProcess':
    log_name = "main"
else:
    # 子进程会自动提取名字里的数字，比如 Process-1 -> 1
    # 如果你的进程名里带 worker，这里可以灵活调整
    pid = current_process.pid
    log_name = f"worker_{pid}"

# 直接创建全局的 logger
logger = setup_logger(log_dir=LOG_DIR, log_file_name=log_name)

__all__ = ['logger']