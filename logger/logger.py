import sys
import inspect
import logging
from colorlog import ColoredFormatter

SUPPORTED_LOG_LEVELS = [
    "DEBUG",
    "INFO",
    "SUCCESS",
    "NOTE",
    "WARNING",
    "ERROR",
    "CRITICAL",
]


class Logger:
    _loggers = {}  # Dictionary with loggers by module name
    SUCCESS_LEVEL_NUM = 25
    NOTE_LEVEL_NUM = 26

    def _configure_logger(self, log_level, module_name):
        """Creates and configures a logger for a specific module."""
        if module_name in self._loggers:
            return self._loggers[module_name]  # Already configured

        logging.addLevelName(self.SUCCESS_LEVEL_NUM, "SUCCESS")
        logging.addLevelName(self.NOTE_LEVEL_NUM, "NOTE")

        def success(self, message, *args, **kwargs):
            if self.isEnabledFor(self.SUCCESS_LEVEL_NUM):
                self._log(self.SUCCESS_LEVEL_NUM, message, args, **kwargs)

        setattr(logging.Logger, "success", success)

        def note(self, message, *args, **kwargs):
            if self.isEnabledFor(self.NOTE_LEVEL_NUM):
                self._log(self.NOTE_LEVEL_NUM, message, args, **kwargs)

        setattr(logging.Logger, "note", note)

        # 2. Check logging level
        if log_level not in SUPPORTED_LOG_LEVELS:
            print(
                f"⚠️ WARNING: Invalid LOG_LEVEL '{log_level}', falling back to 'INFO'.",
                file=sys.stderr,
            )
            log_level = "INFO"
        print(
            f"ℹ️ INFO: Logger initialized for '{module_name}' with level: '{log_level}'",
            file=sys.stdout,
        )

        # 3. Configure log format with colorlog
        formatter = ColoredFormatter(
            "%(log_color)s%(asctime)s | %(levelname)s - %(name)s : %(message)s",
            datefmt=None,
            reset=True,
            log_colors={
                "DEBUG": "cyan",
                "INFO": "white",
                "SUCCESS": "green",
                "NOTE": "blue",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "red,bg_white",
            },
            secondary_log_colors={},
            style="%",
        )

        # 4. Create new logger
        logger = logging.getLogger(module_name)
        logger.setLevel(log_level)

        # Add console handler with color formatter
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        self._loggers[module_name] = logger
        return logger

    def _get_caller_module(self):
        """Determines the name of the module that called the logger."""
        stack = inspect.stack()

        # Getting module name from stack trace
        # 2 because:
        #   0 is this function,
        #   1 is the function that called this one,
        #   2 is the function that called the one that called this one
        #   ... and so on
        module = inspect.getmodule(stack[2][0])
        return module.__name__ if module else "unknown"

    def __init__(self, log_level: str, caller_module: str):
        if not caller_module:
            caller_module = self._get_caller_module()
        self.logger = self._configure_logger(log_level, caller_module)

    def debug(self, message, *args, **kwargs):
        self.logger.debug(message, *args, **kwargs)

    def info(self, message, *args, **kwargs):
        self.logger.info(message, *args, **kwargs)

    def success(self, message, *args, **kwargs):
        if self.logger.isEnabledFor(Logger.SUCCESS_LEVEL_NUM):
            self.logger._log(Logger.SUCCESS_LEVEL_NUM, message, args, **kwargs)

    def note(self, message, *args, **kwargs):
        if self.logger.isEnabledFor(Logger.NOTE_LEVEL_NUM):
            self.logger._log(Logger.NOTE_LEVEL_NUM, message, args, **kwargs)

    def warning(self, message, *args, **kwargs):
        self.logger.warning(message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        self.logger.error(message, *args, **kwargs, exc_info=True)

    def critical(self, message, *args, **kwargs):
        self.logger.critical(message, *args, **kwargs, exc_info=True)

    def get_level_name(self) -> str:
        return logging.getLevelName(self.logger.level)
