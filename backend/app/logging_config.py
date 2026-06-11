"""
应用日志配置
"""
import logging


def setup_logging(level: int = logging.INFO) -> None:
    """
    初始化全局日志格式。

    仅在应用工厂创建时调用一次，避免重复配置。
    """
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
