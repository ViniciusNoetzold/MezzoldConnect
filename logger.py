from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from database import DATA_DIR


def setup_logger(name: str, log_filename: str, max_bytes: int = 5 * 1024 * 1024, backup_count: int = 3) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Evita adicionar múltiplos handlers caso setup_logger seja chamado mais de uma vez para o mesmo nome
    if not logger.handlers:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        log_path = DATA_DIR / log_filename
        
        handler = RotatingFileHandler(
            log_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
        
        formatter = logging.Formatter(
            fmt="[%(asctime)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
    return logger
