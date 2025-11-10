from sys import stdout as sys_stdout

from ansi2html import Ansi2HTMLConverter

from logging import DEBUG as logging_DEBUG
from logging import getLogger as logging_getLogger
from logging import Handler as logging_Handler
from logging import Formatter as logging_Formatter
from logging import StreamHandler as logging_StreamHandler

from PyQt5.QtCore import pyqtSignal, QObject


class EmittingStream(QObject):
    """Custom stream to emit text to a QTextEdit."""

    text_written = pyqtSignal(str)

    def write(self, text):
        if text != "\n":  # Avoid emitting empty newlines
            self.text_written.emit(text)

    def flush(self):  # Required for sys.stdout/stderr
        pass


class QTextEditLogger(logging_Handler):
    """Custom logging handler to redirect log messages to a QTextEdit with colors."""

    def __init__(self, text_edit):
        super().__init__()
        self.text_edit = text_edit
        self.converter = Ansi2HTMLConverter(inline=True)
        self.setFormatter(logging_Formatter("%(levelname)s: %(message)s"))

    def emit(self, record):
        msg = self.format(record)
        html = self.converter.convert(msg)
        self.text_edit.appendHtml(html)


def setup_gui_logging(text_edit_widget, custom_logger_instance):
    """
    Sets up logging to redirect to a QTextEdit widget and also to the console.
    """
    # Create a handler for the QTextEdit
    gui_handler = QTextEditLogger(text_edit_widget)

    # Get the root logger
    root_logger = logging_getLogger()

    # Add the GUI handler to the root logger
    root_logger.addHandler(gui_handler)
    root_logger.setLevel(logging_DEBUG)  # Set a general level for the root logger

    # Ensure a StreamHandler is present for console output
    # This prevents duplicate console output if one is already present
    if not any(
        isinstance(handler, logging_StreamHandler) for handler in root_logger.handlers
    ):
        console_handler = logging_StreamHandler(sys_stdout)
        console_formatter = logging_Formatter("%(levelname)s: %(message)s")
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

    # Also add the GUI handler to the custom logger instance
    if custom_logger_instance:
        custom_logger_instance.logger.addHandler(gui_handler)
