"""Logging configuration for the FPL Solver package."""
import logging
import sys
from typing import Optional

def setup_logger(name: str, level: Optional[int] = None) -> logging.Logger:
    """
    Set up a logger with consistent formatting and optional level override.
    
    Args:
        name: The name of the logger
        level: Optional logging level override. If None, uses INFO
        
    Returns:
        logging.Logger: Configured logger instance
    """
    logger = logging.getLogger(name)
    
    if not logger.handlers:  # Only add handler if logger doesn't have one
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    logger.setLevel(level or logging.INFO)
    return logger
