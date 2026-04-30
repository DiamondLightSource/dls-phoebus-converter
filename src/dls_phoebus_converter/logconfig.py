"""logconfig

This is essentially a template which can be copied into a python project and
used to easily achieve a good practice of logging. Modify the local copy as per
the project or site requirements.
"""

import json
import logging
import logging.config
import os
import os.path
from datetime import datetime

GELFLOG_SERVER = "graylog-log-target.diamond.ac.uk"
GELFLOG_SERVER_PORT = "12228"


def get_timestamped_log_filename() -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    os.makedirs("logs", exist_ok=True)
    return os.path.join("logs", f"conversion_{timestamp}.log")


# NOTE: Setting the logging level to DEBUG will produce additional output from
# CSStudio's conversion process, which is very verbose.
default_config = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "%(levelname)s - %(message)s"},
        "detailed": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d"
            " - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        # Useful output that can be piped to other processes.
        "console": {
            "class": "logging.StreamHandler",
            "level": "INFO",
            "formatter": "simple",
            "stream": "ext://sys.stdout",
        },
        # All debug and user messages.
        "stderr": {
            "class": "logging.StreamHandler",
            "level": "DEBUG",
            "formatter": "simple",
            "stream": "ext://sys.stderr",
        },
        # Generated every time the script is run.
        "file": {
            "class": "logging.FileHandler",
            "level": "DEBUG",
            "formatter": "simple",
            "filename": get_timestamped_log_filename(),
            "mode": "w",
        },
    },
    "loggers": {
        # Fine-grained logging configuration for individual modules or classes
        # Use this to set different log levels without changing 'real' code.
        "dls_phoebus_converter": {
            "level": "INFO",
            "propagate": False,
            "handlers": ["stderr", "file"],
        },
    },
    "root": {
        # Set the level here to be the default minimum level of log record to be
        # produced If you set a handler to level DEBUG you will need to set either this
        # level, or the level of one of the loggers above to DEBUG or you won't see any
        # DEBUG messages
        "level": "DEBUG",
        "handlers": ["stderr"],
    },
}


def setup_logging(config: json = default_config) -> None:
    logging.config.dictConfig(config)
