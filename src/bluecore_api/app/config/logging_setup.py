# logging_setup.py
import logging
import logging.config
import os
import sys


def setup_logging():
    level = os.getenv("LOG_LEVEL", "INFO").upper()

    # Color only when running in a TTY
    use_colors = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "uvicorn_dt": {
                "()": "uvicorn.logging.DefaultFormatter",
                "fmt": "%(asctime)s %(levelprefix)s [%(name)s] %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
                "use_colors": use_colors,
            },
            "uvicorn_access_dt": {
                "()": "uvicorn.logging.AccessFormatter",
                "fmt": "%(asctime)s %(levelprefix)s [%(name)s] %(client_addr)s - '%(request_line)s' %(status_code)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
                "use_colors": use_colors,
            },
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "stream": sys.stdout,
                "formatter": "uvicorn_dt",
            },
            "access": {
                "class": "logging.StreamHandler",
                "stream": sys.stdout,
                "formatter": "uvicorn_access_dt",
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": level, "propagate": False},
            "uvicorn.error": {
                "handlers": ["default"],
                "level": level,
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["access"],
                "level": os.getenv("ACCESS_LOG_LEVEL", "INFO").upper(),
                "propagate": False,
            },
            # "keycloak_auth": {"handlers": [], "level": level, "propagate": True},
        },
        "root": {"level": level, "handlers": ["default"]},
    }

    logging.config.dictConfig(LOGGING)
