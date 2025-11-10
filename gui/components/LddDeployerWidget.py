#!/usr/bin/env python3

from os import makedirs as os_makedirs
from os.path import exists as os_path_exists
from os.path import join as os_path_join
from os.path import dirname as os_path_dirname

from PyQt5.QtCore import QProcess, QTimer, pyqtSlot
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
    QProgressBar,
    QCheckBox,
    QComboBox,
)

from logger.logger import Logger as CustomLogger
from tools.exclude_libs import GENERATED_EXCLUDE_LIST

from .LogConsoleWidget import setup_gui_logging
from .BlacklistViewerWidget import BlacklistViewer


class LddDeployerWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.setup_logging()
        self.deploy_process = None
        self.progress_timer = QTimer()
        self.progress_timer.timeout.connect(self._update_progress_animation)
        self.progress_step = 0

    def setup_ui(self):
        """Setup the enhanced LDD deployer UI"""
        self.main_layout = QHBoxLayout(self)

        # Left pane: Parameters and Console
        self.left_pane_layout = QVBoxLayout()

        # Parameters Frame
        self.parameters_groupbox = QGroupBox("LDD Deployment Parameters")
        self.parameters_layout = QVBoxLayout()

        # Binary path
        self.binary_path_label = QLabel("Binary/Shared Library Path:")
        self.binary_path_input = QLineEdit()
        self.binary_path_browse_button = QPushButton("Browse...")
        self.binary_path_browse_button.clicked.connect(self._browse_binary_path)

        binary_layout = QHBoxLayout()
        binary_layout.addWidget(self.binary_path_input)
        binary_layout.addWidget(self.binary_path_browse_button)

        # Deploy path
        self.deploy_path_label = QLabel("Deploy Target Directory:")
        self.deploy_path_input = QLineEdit()
        self.deploy_path_browse_button = QPushButton("Browse...")
        self.deploy_path_browse_button.clicked.connect(self._browse_deploy_path)

        deploy_layout = QHBoxLayout()
        deploy_layout.addWidget(self.deploy_path_input)
        deploy_layout.addWidget(self.deploy_path_browse_button)

        self.parameters_layout.addWidget(self.binary_path_label)
        self.parameters_layout.addLayout(binary_layout)
        self.parameters_layout.addWidget(self.deploy_path_label)
        self.parameters_layout.addLayout(deploy_layout)

        self.parameters_groupbox.setLayout(self.parameters_layout)

        # Enhanced Progress bar with status
        self.progress_groupbox = QGroupBox("Deployment Progress")
        self.progress_layout = QVBoxLayout()

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_status_label = QLabel("")
        self.progress_status_label.setVisible(False)

        self.progress_layout.addWidget(self.progress_bar)
        self.progress_layout.addWidget(self.progress_status_label)
        self.progress_groupbox.setLayout(self.progress_layout)

        # Console Frame
        self.console_groupbox = QGroupBox("Deployment Log")
        self.console_layout = QVBoxLayout()
        self.console_output = QPlainTextEdit()
        self.console_output.setReadOnly(True)
        self.console_layout.addWidget(self.console_output)
        self.console_groupbox.setLayout(self.console_layout)

        self.left_pane_layout.addWidget(self.parameters_groupbox)
        self.left_pane_layout.addWidget(self.progress_groupbox)
        self.left_pane_layout.addWidget(self.console_groupbox, 1)

        # Right pane: Settings and Deploy Button
        self.right_pane_layout = QVBoxLayout()

        # Bundling Settings Frame
        self.settings_groupbox = QGroupBox("Bundling Settings")
        self.settings_layout = QVBoxLayout()

        self.bundle_all_but_core_checkbox = QCheckBox(
            "Bundle all but core (excluding blacklisted libraries)"
        )
        self.bundle_all_but_core_checkbox.setChecked(True)

        self.bundle_everything_checkbox = QCheckBox("Bundle all libraries")

        # Verbosity level
        self.verbose_label = QLabel("Log Level:")
        self.verbose_combobox = QComboBox()
        self.verbose_combobox.addItems(["INFO", "DEBUG", "WARNING", "ERROR"])
        self.verbose_combobox.setCurrentText("INFO")

        # Mutual exclusion for checkboxes
        self.bundle_all_but_core_checkbox.toggled.connect(
            self._handle_bundle_all_but_core_toggled
        )
        self.bundle_everything_checkbox.toggled.connect(
            self._handle_bundle_everything_toggled
        )

        self.settings_layout.addWidget(self.bundle_all_but_core_checkbox)
        self.settings_layout.addWidget(self.bundle_everything_checkbox)
        self.settings_layout.addWidget(self.verbose_label)
        self.settings_layout.addWidget(self.verbose_combobox)

        self.settings_groupbox.setLayout(self.settings_layout)

        # Action Buttons Frame
        self.action_groupbox = QGroupBox("Actions")
        self.action_layout = QVBoxLayout()

        self.show_blacklist_button = QPushButton("Show Blacklisted Libraries")
        self.show_blacklist_button.clicked.connect(self._show_blacklist)

        self.action_layout.addWidget(self.show_blacklist_button)
        self.action_groupbox.setLayout(self.action_layout)

        # Deploy Button
        self.deploy_button = QPushButton("Deploy Libraries with LDD")
        self.deploy_button.setStyleSheet("font-size: 16px; padding: 8px;")
        self.deploy_button.clicked.connect(self._start_deploy)

        self.right_pane_layout.addWidget(self.settings_groupbox)
        self.right_pane_layout.addWidget(self.action_groupbox)
        self.right_pane_layout.addStretch(1)
        self.right_pane_layout.addWidget(self.deploy_button)

        # Add panes to main layout
        self.main_layout.addLayout(self.left_pane_layout, 2)
        self.main_layout.addLayout(self.right_pane_layout, 1)

    def setup_logging(self):
        """Setup logging for this widget"""
        self.custom_logger = CustomLogger("INFO", "LddDeployerWidget")
        setup_gui_logging(self.console_output, self.custom_logger)

    def _browse_binary_path(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Binary File",
            "",
            "All Files (*);;Executables (*);;Shared Libraries (*.so)",
        )
        if file_path:
            self.binary_path_input.setText(file_path)

    def _browse_deploy_path(self):
        dir_path = QFileDialog.getExistingDirectory(
            self, "Select Deployment Target Directory", ""
        )
        if dir_path:
            self.deploy_path_input.setText(dir_path)

    def _show_blacklist(self):
        """Show blacklisted libraries window"""
        self.custom_logger.info("Displaying blacklisted libraries...")
        viewer = BlacklistViewer(GENERATED_EXCLUDE_LIST, parent=self)
        viewer.exec_()

    def _handle_bundle_all_but_core_toggled(self, checked):
        """Handle bundle all but core checkbox"""
        if checked:
            self.bundle_everything_checkbox.setChecked(False)

    def _handle_bundle_everything_toggled(self, checked):
        """Handle bundle everything checkbox"""
        if checked:
            self.bundle_all_but_core_checkbox.setChecked(False)

    def _show_message_box(self, title, message, icon=QMessageBox.Information):
        """Show message box"""
        msg_box = QMessageBox()
        msg_box.setIcon(icon)
        msg_box.setText(message)
        msg_box.setWindowTitle(title)
        msg_box.exec_()

    def _prepare_worker_arguments(
        self,
        binary_path,
        deploy_path,
        bundle_all_but_core,
        bundle_everything,
        log_level,
    ):
        """Prepare arguments for worker process"""
        args = [
            "python3",
            os_path_join(
                os_path_dirname(os_path_dirname(__file__)),
                "core",
                "LddDeployerWorker.py",
            ),
            binary_path,
            deploy_path,
            "--log-level",
            log_level,
        ]

        if bundle_all_but_core and not bundle_everything:
            args.append("--bundle-all-but-core")
        elif bundle_everything:
            args.append("--bundle-everything")

        return args

    @pyqtSlot()
    def _start_deploy(self):
        """Start LDD deployment process using QProcess"""
        binary_path = self.binary_path_input.text().strip()
        deploy_path = self.deploy_path_input.text().strip()

        # Validate inputs
        if not binary_path or not deploy_path:
            self._show_message_box(
                "Error",
                "Please specify both binary path and deploy directory",
                QMessageBox.Critical,
            )
            return

        if not os_path_exists(binary_path):
            self._show_message_box(
                "Error",
                f"Binary file does not exist: {binary_path}",
                QMessageBox.Critical,
            )
            return

        # Create deploy directory if it doesn't exist
        if not os_path_exists(deploy_path):
            try:
                os_makedirs(deploy_path)
                self.custom_logger.info(f"Created deploy directory: {deploy_path}")
            except Exception as e:
                self._show_message_box(
                    "Error",
                    f"Failed to create deploy directory: {str(e)}",
                    QMessageBox.Critical,
                )
                return

        # Get settings
        bundle_all_but_core = self.bundle_all_but_core_checkbox.isChecked()
        bundle_everything = self.bundle_everything_checkbox.isChecked()
        log_level = self.verbose_combobox.currentText()

        # Clear console and start deployment
        self.console_output.clear()
        self._show_progress(True, "Preparing deployment...")
        self.deploy_button.setEnabled(False)

        try:
            # Prepare worker arguments
            worker_args = self._prepare_worker_arguments(
                binary_path,
                deploy_path,
                bundle_all_but_core,
                bundle_everything,
                log_level,
            )

            # Start QProcess
            self.deploy_process = QProcess(self)
            self.deploy_process.readyReadStandardOutput.connect(self._handle_stdout)
            self.deploy_process.readyReadStandardError.connect(self._handle_stderr)
            self.deploy_process.finished.connect(self._deployment_finished)

            # Start the process
            self.deploy_process.start(worker_args[0], worker_args[1:])

            if not self.deploy_process.waitForStarted(3000):
                raise Exception("Failed to start deployment process")

            self.custom_logger.info("🚀 Starting deployment process...")
            self._show_progress(True, "Analyzing dependencies...")

        except Exception as e:
            self._deployment_finished(-1, 1)  # QProcess.CrashExit
            self._show_message_box(
                "Error",
                f"Failed to start deployment: {str(e)}",
                QMessageBox.Critical,
            )

    def _show_progress(self, visible, status=""):
        """Show/hide progress bar with status"""
        self.progress_bar.setVisible(visible)
        self.progress_status_label.setVisible(visible)
        if visible:
            self.progress_status_label.setText(status)
            if not self.progress_timer.isActive():
                self.progress_step = 0
                self.progress_timer.start(200)  # Update every 200ms
        else:
            self.progress_timer.stop()

    def _update_progress_animation(self):
        """Update progress bar animation"""
        if self.progress_bar.isVisible():
            self.progress_step = (self.progress_step + 1) % 100
            self.progress_bar.setValue(self.progress_step)

    @pyqtSlot()
    def _handle_stdout(self):
        """Handle stdout from deployment process"""
        if self.deploy_process is None:
            return

        data = self.deploy_process.readAllStandardOutput()
        stdout = bytes(data).decode("utf8").strip()

        for line in stdout.split("\n"):
            if line.strip():
                # Check for progress updates
                if line.startswith("PROGRESS:"):
                    try:
                        parts = line.split(":", 2)
                        if len(parts) >= 3:
                            progress_value = int(parts[1])
                            message = parts[2]
                            self.progress_bar.setValue(progress_value)
                            self.progress_status_label.setText(
                                f"Copying libraries... ({progress_value}%)"
                            )
                            self.console_output.appendPlainText(message)
                    except (ValueError, IndexError):
                        self.console_output.appendPlainText(line)
                else:
                    self.console_output.appendPlainText(line)
                    # Update status based on message content
                    if "🔍 Starting LDD analysis" in line:
                        self._show_progress(True, "Analyzing dependencies...")
                    elif "📦 Found" in line and "libraries to deploy" in line:
                        self._show_progress(True, "Preparing to copy libraries...")
                    elif "📁 Created directory" in line:
                        self._show_progress(True, "Starting library copy...")

    @pyqtSlot()
    def _handle_stderr(self):
        """Handle stderr from deployment process"""
        if self.deploy_process is None:
            return

        data = self.deploy_process.readAllStandardError()
        stderr = bytes(data).decode("utf8").strip()

        if stderr:
            self.console_output.appendPlainText(f"ERROR: {stderr}")

    @pyqtSlot(int, "QProcess::ExitStatus")
    def _deployment_finished(self, exit_code, exit_status):
        """Handle deployment process completion"""
        self._show_progress(False)
        self.deploy_button.setEnabled(True)

        # Clean up process
        if self.deploy_process:
            self.deploy_process.deleteLater()
            self.deploy_process = None

        # Show result
        if exit_code == 0 and exit_status == 0:  # QProcess.NormalExit
            self._show_message_box("Success", "✅ Deployment completed successfully!")
            self.custom_logger.info("Deployment completed successfully")
        else:
            self._show_message_box(
                "Error", "❌ Deployment failed!", QMessageBox.Critical
            )
            self.custom_logger.error(f"Deployment failed with exit code: {exit_code}")
