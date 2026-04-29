# src/utils/logger.py
from pathlib import Path
from .logging_setup import setup_logger

# 使用 .parents[3] 直接定位工程根目录
# 0: logger.py 自身
# 1: utils 目录
# 2: src 目录
# 3: 工程根目录
PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = PROJECT_ROOT / "logs"

print(f"Log directory will be: {LOG_DIR}")
# 直接创建 logger
logger = setup_logger(log_dir=LOG_DIR)