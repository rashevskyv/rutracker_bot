import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logging(log_level=logging.INFO, log_file="bot.log", log_to_console=True):
    """
    Sets up the logging configuration for the bot.
    """
    # Create logs directory if it doesn't exist
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Define the logging format
    log_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Configure the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Clear existing handlers
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # File handler with rotation (5MB per file, keep 3 backup files)
    file_handler = RotatingFileHandler(
        log_file, maxBytes=5*1024*1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(log_format)
    root_logger.addHandler(file_handler)

    # Console handler
    if log_to_console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(log_format)
        root_logger.addHandler(console_handler)

    logging.info(f"Logging initialized. Level: {logging.getLevelName(log_level)}, File: {log_file}")

# Initialize by default
if __name__ == "__main__":
    setup_logging()
