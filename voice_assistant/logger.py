import logging
from rich.logging import RichHandler
from rich.console import Console

# 全局 console 对象，用于直接打印富文本（如果需要替代 print）
console = Console()

def setup_logger(name: str = "VoiceAssistant", level: int = logging.INFO) -> logging.Logger:
    """
    配置并获取 logger
    """
    # 避免重复添加 handler
    logger = logging.getLogger(name)
    if logger.hasHandlers():
        return logger
        
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, console=console)]
    )
    
    return logger

def get_logger(name: str) -> logging.Logger:
    """
    获取指定名称的 logger，通常在各模块中使用
    """
    return logging.getLogger(name)
