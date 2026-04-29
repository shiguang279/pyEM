# src/utils/logging_setup.py
import logging
from pathlib import Path
from datetime import datetime

def setup_logger(
    log_dir: Path,
    level: int = logging.INFO,
    is_main_process: bool = True,
    log_file_name: str = None
) -> logging.Logger:
    """
    设置日志记录器
    """
    # 1. 确保目录存在
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # 2. 强制生成带时间戳的文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if log_file_name:
        final_log_file_name = f"{log_file_name}_{timestamp}.log"
    else:
        final_log_file_name = f"log_{timestamp}.log"
        
    log_file = log_dir / final_log_file_name

    # 3. 获取 Logger (使用当前模块名，虽然不打印，但用于区分日志源)
    logger = logging.getLogger(__name__)
    logger.setLevel(level)
    
    # 清除已有 handlers，防止重复打印
    if logger.hasHandlers():
        logger.handlers.clear()

    # 格式: [日期] [INFO] 消息内容
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s')

    # 5. 主进程：添加文件处理器
    if is_main_process:
        try:
            fh = logging.FileHandler(log_file, mode='a', encoding='utf-8')
            fh.setLevel(level)
            fh.setFormatter(formatter)
            logger.addHandler(fh)
        except Exception as e:
            print(f"[Warning] Failed to add file handler: {e}")

    # 6. 所有进程：添加控制台输出
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    return logger