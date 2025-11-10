#!/usr/bin/env python3

from os.path import join as os_path_join
from os.path import exists as os_path_exists
from os.path import dirname as os_path_dirname
from os.path import basename as os_path_basename

from PyQt5.QtCore import QProcess, pyqtSlot, QTimer
from PyQt5.QtGui import QFont, QTextCursor
from PyQt5.QtWidgets import (
    QLabel,
    QWidget,
    QGroupBox,
    QLineEdit,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QPlainTextEdit,
    QMessageBox,
    QFileDialog,
)

from logger.logger import Logger as CustomLogger


class HackerTerminalWidget(QPlainTextEdit):
    """Hacker-style terminal widget with syntax highlighting"""

    def __init__(self):
        super().__init__()
        self.setup_hacker_style()

    def setup_hacker_style(self):
        """Setup the hacker terminal style"""
        # Set hacker color scheme
        self.setStyleSheet(
            """
            QPlainTextEdit {
                background-color: #000000;
                color: #00ff00;
                border: 2px solid #333333;
                border-radius: 5px;
                padding: 10px;
                font-family: 'Courier New', 'Monaco', 'Consolas', monospace;
                font-size: 12px;
                selection-background-color: #333333;
                selection-color: #ffffff;
            }
        """
        )

        # Set monospace font
        font = QFont("Courier New", 12)
        font.setStyleHint(QFont.Monospace)
        self.setFont(font)

        # Read only
        self.setReadOnly(True)

    def append_hacker_text(self, text, color="#00ff00"):
        """Append text with specified color"""
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)

        # Add color formatting
        html_text = f'<span style="color: {color};">{text}</span>'
        cursor.insertHtml(html_text)
        cursor.insertText("\n")

        # Auto-scroll to bottom
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def append_highlighted_text(self, text, highlight_patterns=None):
        """Append text with highlighted patterns"""
        if highlight_patterns is None:
            highlight_patterns = []

        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)

        # Highlight specific patterns
        formatted_text = text
        for pattern, color in highlight_patterns:
            formatted_text = formatted_text.replace(
                pattern,
                f'<span style="color: {color}; font-weight: bold;">{pattern}</span>',
            )

        cursor.insertHtml(f'<span style="color: #00ff00;">{formatted_text}</span>')
        cursor.insertText("\n")

        self.setTextCursor(cursor)
        self.ensureCursorVisible()


class ElfPatcherWidget(QWidget):
    """ELF Patcher Widget with interactive terminal-style interface"""

    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.setup_logging()
        self.current_process = None
        self.current_file_path = None
        self.current_file_paths = []  # For multiple file operations
        self.current_operation_index = 0  # Track progress in batch operations
        self.is_batch_operation = False  # Flag for batch vs single operations

    def setup_ui(self):
        """Setup the ELF patcher UI"""
        self.main_layout = QVBoxLayout(self)

        # Header with file selection
        self.header_groupbox = QGroupBox("ELF GNU_STACK Patcher")
        self.header_layout = QVBoxLayout()

        # File path input
        self.file_path_label = QLabel("Shared Library (.so) File Path(s):")
        self.file_path_input = QLineEdit()
        self.file_path_input.setPlaceholderText(
            "Enter path(s) to .so file(s). Multiple paths separated by ';'"
        )
        self.file_path_browse_button = QPushButton("Browse Single")
        self.file_path_browse_button.clicked.connect(self._browse_file_path)

        self.file_path_browse_multiple_button = QPushButton("Browse Multiple")
        self.file_path_browse_multiple_button.clicked.connect(
            self._browse_multiple_files
        )
        self.file_path_browse_multiple_button.setStyleSheet(
            """
            QPushButton {
                background-color: #5E81AC;
                color: #ECEFF4;
                border: 2px solid #88C0D0;
                border-radius: 5px;
                padding: 6px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #88C0D0;
                border-color: #8FBCBB;
            }
        """
        )

        file_layout = QHBoxLayout()
        file_layout.addWidget(self.file_path_input, 4)
        file_layout.addWidget(self.file_path_browse_button, 1)
        file_layout.addWidget(self.file_path_browse_multiple_button, 1)

        # Action buttons
        self.buttons_layout = QHBoxLayout()

        self.analyze_button = QPushButton("🔍 Analyze ELF")
        self.analyze_button.setStyleSheet(
            """
            QPushButton {
                background-color: #2E3440;
                color: #88C0D0;
                border: 2px solid #434C5E;
                border-radius: 5px;
                padding: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #434C5E;
                border-color: #88C0D0;
            }
            QPushButton:pressed {
                background-color: #3B4252;
            }
        """
        )
        self.analyze_button.clicked.connect(self._analyze_elf)

        self.patch_button = QPushButton("⚡ Patch GNU_STACK")
        self.patch_button.setStyleSheet(
            """
            QPushButton {
                background-color: #BF616A;
                color: #ECEFF4;
                border: 2px solid #B48EAD;
                border-radius: 5px;
                padding: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #D08770;
                border-color: #EBCB8B;
            }
            QPushButton:pressed {
                background-color: #A3BE8C;
            }
        """
        )
        self.patch_button.clicked.connect(self._patch_elf)
        self.patch_button.setEnabled(False)

        self.clear_button = QPushButton("Clear Terminal")
        self.clear_button.setStyleSheet(
            """
            QPushButton {
                background-color: #4C566A;
                color: #D8DEE9;
                border: 2px solid #5E81AC;
                border-radius: 5px;
                padding: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5E81AC;
                border-color: #81A1C1;
            }
        """
        )
        self.clear_button.clicked.connect(self._clear_terminal)

        self.buttons_layout.addWidget(self.analyze_button)
        self.buttons_layout.addWidget(self.patch_button)
        self.buttons_layout.addWidget(self.clear_button)

        self.header_layout.addWidget(self.file_path_label)
        self.header_layout.addLayout(file_layout)
        self.header_layout.addLayout(self.buttons_layout)
        self.header_groupbox.setLayout(self.header_layout)

        # Terminal interface
        self.terminal_groupbox = QGroupBox("🖥️ Interactive ELF Terminal")
        self.terminal_layout = QVBoxLayout()

        self.terminal = HackerTerminalWidget()
        self.terminal.setMinimumHeight(400)

        self.terminal_layout.addWidget(self.terminal)
        self.terminal_groupbox.setLayout(self.terminal_layout)

        # Add to main layout
        self.main_layout.addWidget(self.header_groupbox)
        self.main_layout.addWidget(self.terminal_groupbox, 1)

        # Welcome message
        self._show_welcome_message()

    def setup_logging(self):
        """Setup logging for this widget"""
        self.custom_logger = CustomLogger("INFO", "ElfPatcherWidget")

    def _show_welcome_message(self):
        """Show welcome message in terminal"""
        self.terminal.append_hacker_text("=" * 60, "#00ffff")
        self.terminal.append_hacker_text(
            "ELF GNU_STACK PATCHER TERMINAL v1.0", "#00ffff"
        )
        self.terminal.append_hacker_text("=" * 60, "#00ffff")
        self.terminal.append_hacker_text("")
        self.terminal.append_hacker_text(
            "Welcome to the ELF patcher terminal!", "#ffff00"
        )
        self.terminal.append_hacker_text("This tool allows you to:", "#ffffff")
        self.terminal.append_hacker_text(
            "  • Analyze ELF shared libraries (.so files)", "#aaaaaa"
        )
        self.terminal.append_hacker_text(
            "  • View GNU_STACK segment information", "#aaaaaa"
        )
        self.terminal.append_hacker_text(
            "  • Patch executable stack to non-executable", "#aaaaaa"
        )
        self.terminal.append_hacker_text(
            "  • Support for BATCH operations on multiple files!", "#00ffff"
        )
        self.terminal.append_hacker_text("")
        self.terminal.append_hacker_text(
            "📁 Single file: Select 'Browse Single' or enter path", "#00ff00"
        )
        self.terminal.append_hacker_text(
            "📂 Multiple files: Select 'Browse Multiple' or enter paths separated by ';'",
            "#00ff00",
        )
        self.terminal.append_hacker_text("")

    def _browse_file_path(self):
        """Browse for shared library file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Shared Library File",
            "",
            "Shared Libraries (*.so *.so.*);;All Files (*)",
        )
        if file_path:
            self.file_path_input.setText(file_path)

    def _browse_multiple_files(self):
        """Browse for multiple shared library files"""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Multiple Shared Library Files",
            "",
            "Shared Libraries (*.so *.so.*);;All Files (*)",
        )
        if file_paths:
            # Join paths with semicolon separator
            paths_text = ";".join(file_paths)
            self.file_path_input.setText(paths_text)

    def _parse_file_paths(self, input_text):
        """Parse file paths from input text (handles both single and multiple paths)"""
        if not input_text.strip():
            return []

        # Split by semicolon and clean up paths
        paths = [path.strip() for path in input_text.split(";") if path.strip()]
        return paths

    def _validate_shared_library(self, file_path):
        """Validate that the file is a shared library"""
        if not os_path_exists(file_path):
            return False, "File does not exist"

        # Check file extension
        if not (file_path.endswith(".so") or ".so." in file_path):
            return False, "File does not appear to be a shared library (.so)"

        # Check ELF magic bytes
        try:
            with open(file_path, "rb") as f:
                magic = f.read(4)
                if magic != b"\x7fELF":
                    return False, "File is not a valid ELF file"
        except Exception as e:
            return False, f"Cannot read file: {str(e)}"

        return True, "Valid ELF shared library"

    def _show_message_box(self, title, message, icon=QMessageBox.Information):
        """Show message box"""
        msg_box = QMessageBox()
        msg_box.setIcon(icon)
        msg_box.setText(message)
        msg_box.setWindowTitle(title)
        msg_box.exec_()

    @pyqtSlot()
    def _analyze_elf(self):
        """Analyze ELF file(s) using readelf"""
        input_text = self.file_path_input.text().strip()

        if not input_text:
            self._show_message_box(
                "Error", "Please specify file path(s)", QMessageBox.Critical
            )
            return

        # Parse file paths
        file_paths = self._parse_file_paths(input_text)
        if not file_paths:
            self._show_message_box(
                "Error", "No valid file paths found", QMessageBox.Critical
            )
            return

        # Validate all files first
        invalid_files = []
        valid_files = []

        for file_path in file_paths:
            is_valid, message = self._validate_shared_library(file_path)
            if is_valid:
                valid_files.append(file_path)
            else:
                invalid_files.append(f"{file_path}: {message}")

        # Show validation results
        if invalid_files:
            error_message = "Invalid files found:\n" + "\n".join(invalid_files)
            if valid_files:
                error_message += (
                    f"\n\nContinuing with {len(valid_files)} valid file(s)..."
                )
                self._show_message_box("Warning", error_message, QMessageBox.Warning)
            else:
                self._show_message_box("Error", error_message, QMessageBox.Critical)
                return

        if not valid_files:
            return

        # Set up for batch operation
        self.current_file_paths = valid_files
        self.current_operation_index = 0
        self.is_batch_operation = len(valid_files) > 1
        self.patch_button.setEnabled(True)

        # Clear terminal and show analysis header
        if self.is_batch_operation:
            self.terminal.append_hacker_text(
                f"\n[BATCH ANALYSIS] Starting analysis of {len(valid_files)} files...",
                "#00ffff",
            )
        else:
            self.terminal.append_hacker_text(
                f"\n[ANALYSIS] Starting analysis of: {os_path_basename(valid_files[0])}",
                "#00ffff",
            )

        self.terminal.append_hacker_text("=" * 60, "#444444")

        # Start with first file
        self.current_file_path = valid_files[0]
        self._run_readelf_analysis()

    def _run_readelf_analysis(self):
        """Run readelf analysis"""
        if not self.current_file_path:
            return

        # Show progress for batch operations
        if self.is_batch_operation:
            progress = (
                f"[{self.current_operation_index + 1}/{len(self.current_file_paths)}]"
            )
            self.terminal.append_hacker_text(
                f"\n{progress} Analyzing: {os_path_basename(self.current_file_path)}",
                "#00ffff",
            )

        # Create QProcess for readelf
        self.current_process = QProcess(self)
        self.current_process.readyReadStandardOutput.connect(
            self._handle_readelf_output
        )
        self.current_process.readyReadStandardError.connect(self._handle_readelf_error)
        self.current_process.finished.connect(self._readelf_finished)

        # Run readelf -l (program headers)
        self.terminal.append_hacker_text(
            "🔍 Executing: readelf -l " + self.current_file_path, "#ffff00"
        )
        self.current_process.start("readelf", ["-l", self.current_file_path])

    @pyqtSlot()
    def _handle_readelf_output(self):
        """Handle readelf output"""
        if self.current_process is None:
            return

        data = self.current_process.readAllStandardOutput()
        output = bytes(data).decode("utf8").strip()

        # Highlight GNU_STACK entries
        for line in output.split("\n"):
            if line.strip():
                if "GNU_STACK" in line:
                    # Highlight GNU_STACK line with special colors
                    highlight_patterns = [
                        ("GNU_STACK", "#ff0000"),  # Red for GNU_STACK
                        ("RWE", "#ff0000"),  # Red for executable
                        ("RW", "#00ff00"),  # Green for non-executable
                        ("0x", "#ffff00"),  # Yellow for hex values
                    ]
                    self.terminal.append_highlighted_text(line, highlight_patterns)
                else:
                    self.terminal.append_hacker_text(line, "#cccccc")

    @pyqtSlot()
    def _handle_readelf_error(self):
        """Handle readelf errors"""
        if self.current_process is None:
            return

        data = self.current_process.readAllStandardError()
        error = bytes(data).decode("utf8").strip()

        if error:
            self.terminal.append_hacker_text(f"ERROR: {error}", "#ff0000")

    @pyqtSlot()
    def _readelf_finished(self):
        """Handle readelf process completion"""
        if self.current_process:
            self.current_process.deleteLater()
            self.current_process = None

        self.terminal.append_hacker_text("-" * 40, "#444444")

        # Check if there are more files to analyze
        self.current_operation_index += 1
        if self.is_batch_operation and self.current_operation_index < len(
            self.current_file_paths
        ):
            # Continue with next file
            self.current_file_path = self.current_file_paths[
                self.current_operation_index
            ]
            QTimer.singleShot(
                500, self._run_readelf_analysis
            )  # Small delay for readability
        else:
            # All files analyzed
            if self.is_batch_operation:
                self.terminal.append_hacker_text(
                    f"[BATCH ANALYSIS] Complete! Analyzed {len(self.current_file_paths)} files.",
                    "#00ffff",
                )
            else:
                self.terminal.append_hacker_text(
                    "[ANALYSIS] Complete! Review GNU_STACK segment above.", "#00ffff"
                )
            self.terminal.append_hacker_text("=" * 60, "#444444")

    @pyqtSlot()
    def _patch_elf(self):
        """Patch ELF file(s) using patch_gnustack.py"""
        if not self.current_file_paths:
            self._show_message_box("Error", "No files selected", QMessageBox.Critical)
            return

        # Reset for patching operation
        self.current_operation_index = 0
        self.current_file_path = self.current_file_paths[0]

        if self.is_batch_operation:
            self.terminal.append_hacker_text(
                f"\n[BATCH PATCHING] Starting patch operation on {len(self.current_file_paths)} files...",
                "#ff00ff",
            )
        else:
            self.terminal.append_hacker_text(
                "\n[PATCHING] Starting patch operation...", "#ff00ff"
            )
        self.terminal.append_hacker_text("=" * 60, "#444444")

        # Start patching first file
        self._run_patch_operation()

    def _run_patch_operation(self):
        """Run patch operation on current file"""
        if not self.current_file_path:
            return

        # Show progress for batch operations
        if self.is_batch_operation:
            progress = (
                f"[{self.current_operation_index + 1}/{len(self.current_file_paths)}]"
            )
            self.terminal.append_hacker_text(
                f"\n{progress} Patching: {os_path_basename(self.current_file_path)}",
                "#ff00ff",
            )

        # Get path to patch_gnustack.py
        script_dir = os_path_dirname(os_path_dirname(os_path_dirname(__file__)))
        patch_script = os_path_join(script_dir, "tools", "patch_gnustack.py")

        # Create QProcess for patching
        self.current_process = QProcess(self)
        self.current_process.readyReadStandardOutput.connect(self._handle_patch_output)
        self.current_process.readyReadStandardError.connect(self._handle_patch_error)
        self.current_process.finished.connect(self._patch_finished)

        # Run patch command
        self.terminal.append_hacker_text(
            f"⚡ Executing: python3 {os_path_basename(patch_script)} {self.current_file_path}",
            "#ffff00",
        )
        self.current_process.start("python3", [patch_script, self.current_file_path])

    @pyqtSlot()
    def _handle_patch_output(self):
        """Handle patch output"""
        if self.current_process is None:
            return

        data = self.current_process.readAllStandardOutput()
        output = bytes(data).decode("utf8").strip()

        for line in output.split("\n"):
            if line.strip():
                # Highlight important patch messages
                if "Patched" in line:
                    self.terminal.append_hacker_text(
                        line, "#00ff00"
                    )  # Green for success
                elif "Found GNU_STACK" in line:
                    self.terminal.append_hacker_text(line, "#ffff00")  # Yellow for info
                elif "Already not executable" in line:
                    self.terminal.append_hacker_text(line, "#00ffff")  # Cyan for info
                else:
                    self.terminal.append_hacker_text(line, "#cccccc")

    @pyqtSlot()
    def _handle_patch_error(self):
        """Handle patch errors"""
        if self.current_process is None:
            return

        data = self.current_process.readAllStandardError()
        error = bytes(data).decode("utf8").strip()

        if error:
            self.terminal.append_hacker_text(f"ERROR: {error}", "#ff0000")

    @pyqtSlot()
    def _patch_finished(self):
        """Handle patch process completion"""
        if self.current_process:
            self.current_process.deleteLater()
            self.current_process = None

        self.terminal.append_hacker_text("-" * 40, "#444444")

        # Check if there are more files to patch
        self.current_operation_index += 1
        if self.is_batch_operation and self.current_operation_index < len(
            self.current_file_paths
        ):
            # Continue with next file
            self.current_file_path = self.current_file_paths[
                self.current_operation_index
            ]
            QTimer.singleShot(
                500, self._run_patch_operation
            )  # Small delay for readability
        else:
            # All files patched
            if self.is_batch_operation:
                self.terminal.append_hacker_text(
                    f"[BATCH PATCHING] Complete! Patched {len(self.current_file_paths)} files.",
                    "#ff00ff",
                )
                self.terminal.append_hacker_text(
                    "[BATCH PATCHING] Running post-patch analysis...", "#ff00ff"
                )
            else:
                self.terminal.append_hacker_text(
                    "[PATCHING] Complete! Running post-patch analysis...", "#ff00ff"
                )

            # Reset for post-patch analysis
            self.current_operation_index = 0
            self.current_file_path = self.current_file_paths[0]

            # Run analysis again to show changes
            QTimer.singleShot(1000, self._run_post_patch_analysis)

    def _run_post_patch_analysis(self):
        """Run analysis after patching to show changes"""
        self.terminal.append_hacker_text(
            "\n[POST-PATCH ANALYSIS] Verifying changes...", "#00ffff"
        )
        self.terminal.append_hacker_text("-" * 60, "#444444")
        self._run_readelf_analysis()

    @pyqtSlot()
    def _clear_terminal(self):
        """Clear terminal content and reset state"""
        self.terminal.clear()
        # Reset operation state
        self.current_file_paths = []
        self.current_operation_index = 0
        self.is_batch_operation = False
        self.current_file_path = None
        self.patch_button.setEnabled(False)
        self._show_welcome_message()
