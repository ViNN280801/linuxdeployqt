#!/usr/bin/env python3

from PyQt5.QtCore import Qt, QProcess
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QCheckBox,
    QPlainTextEdit,
    QMessageBox,
    QFileDialog,
    QComboBox,
)

from logger.logger import Logger as CustomLogger
from tools.exclude_libs import GENERATED_EXCLUDE_LIST

from .LogConsoleWidget import setup_gui_logging
from .BlacklistViewerWidget import BlacklistViewer
from ..core.DeployCommandComposer import DeployCommandComposer


class QtDeployerWidget(QWidget):
    """Qt Deployer widget with full functionality"""

    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.setup_logging()
        self.deploy_process = None

    def setup_ui(self):
        """Setup the Qt deployer UI"""
        self.main_layout = QHBoxLayout(self)

        # Left pane: Parameters and Console
        self.left_pane_layout = QVBoxLayout()

        # Parameters Frame
        self.parameters_groupbox = QGroupBox("Deployment Parameters")
        self.parameters_layout = QVBoxLayout()

        self.binary_path_label = QLabel("Application Binary / Shared Library Path:")
        self.binary_path_input = QLineEdit()
        self.binary_path_browse_button = QPushButton("Browse...")
        self.binary_path_browse_button.clicked.connect(self._browse_binary_path)

        self.deploy_path_label = QLabel("Deployment Target Directory:")
        self.deploy_path_input = QLineEdit()
        self.deploy_path_browse_button = QPushButton("Browse...")
        self.deploy_path_browse_button.clicked.connect(self._browse_deploy_path)

        self.parameters_layout.addWidget(self.binary_path_label)
        self.parameters_layout.addWidget(self.binary_path_input)
        self.parameters_layout.addWidget(self.binary_path_browse_button)
        self.parameters_layout.addWidget(self.deploy_path_label)
        self.parameters_layout.addWidget(self.deploy_path_input)
        self.parameters_layout.addWidget(self.deploy_path_browse_button)

        self.qml_dir_label = QLabel("QML Directories (comma-separated):")
        self.qml_dir_input = QLineEdit()

        self.qt_path_label = QLabel("Explicit Qt Installation Path:")
        self.qt_path_input = QLineEdit()
        self.qt_path_browse_button = QPushButton("Browse...")
        self.qt_path_browse_button.clicked.connect(self._browse_qt_path)

        self.desktop_file_label = QLabel(".desktop File Path*:")
        self.desktop_file_input = QLineEdit()
        self.desktop_file_browse_button = QPushButton("Browse...")
        self.desktop_file_browse_button.clicked.connect(self._browse_desktop_file)

        self.icon_file_label = QLabel("Application Icon File Path*:")
        self.icon_file_input = QLineEdit()
        self.icon_file_browse_button = QPushButton("Browse...")
        self.icon_file_browse_button.clicked.connect(self._browse_icon_file)

        self.apprun_file_label = QLabel("Custom AppRun Script File Path (optional):")
        self.apprun_file_input = QLineEdit()
        self.apprun_file_browse_button = QPushButton("Browse...")
        self.apprun_file_browse_button.clicked.connect(self._browse_apprun_file)

        self.parameters_layout.addWidget(self.qml_dir_label)
        self.parameters_layout.addWidget(self.qml_dir_input)
        self.parameters_layout.addWidget(self.qt_path_label)
        self.parameters_layout.addWidget(self.qt_path_input)
        self.parameters_layout.addWidget(self.qt_path_browse_button)
        self.parameters_layout.addWidget(self.desktop_file_label)
        self.parameters_layout.addWidget(self.desktop_file_input)
        self.parameters_layout.addWidget(self.desktop_file_browse_button)
        self.parameters_layout.addWidget(self.icon_file_label)
        self.parameters_layout.addWidget(self.icon_file_input)
        self.parameters_layout.addWidget(self.icon_file_browse_button)
        self.parameters_layout.addWidget(self.apprun_file_label)
        self.parameters_layout.addWidget(self.apprun_file_input)
        self.parameters_layout.addWidget(self.apprun_file_browse_button)

        self.parameters_groupbox.setLayout(self.parameters_layout)

        # Console Frame
        self.console_groupbox = QGroupBox("Deployment Log")
        self.console_layout = QVBoxLayout()
        self.console_output = QPlainTextEdit()
        self.console_output.setReadOnly(True)
        self.console_layout.addWidget(self.console_output)
        self.console_groupbox.setLayout(self.console_layout)

        self.left_pane_layout.addWidget(self.parameters_groupbox)
        self.left_pane_layout.addWidget(self.console_groupbox, 1)

        # Right pane: Settings and Deploy Button
        self.right_pane_layout = QVBoxLayout()

        # Settings Frame
        self.settings_groupbox = QGroupBox("Bundling Settings")
        self.settings_layout = QVBoxLayout()

        self.bundle_all_but_core_checkbox = QCheckBox(
            "Bundle all but core (excluding blacklisted libraries)"
        )
        self.bundle_all_but_core_checkbox.setChecked(True)
        self.bundle_everything_checkbox = QCheckBox("Bundle all libraries")

        self.bundle_non_qt_libs_checkbox = QCheckBox(
            "Bundle non-Qt libraries (default: enabled)"
        )
        self.bundle_non_qt_libs_checkbox.setChecked(True)

        self.no_strip_checkbox = QCheckBox("Don't strip binaries")
        self.always_overwrite_checkbox = QCheckBox("Always overwrite existing files")
        self.always_overwrite_checkbox.setChecked(True)

        # Verbosity level
        self.verbose_label = QLabel("Verbosity Level:")
        self.verbose_combobox = QComboBox()
        self.verbose_combobox.addItems(
            ["0 (Warnings & Errors)", "1 (Info & Success)", "2 (Debug)"]
        )
        self.verbose_combobox.setCurrentIndex(1)

        # Mutual exclusion for checkboxes
        self.bundle_all_but_core_checkbox.toggled.connect(
            self._handle_bundle_all_but_core_toggled
        )
        self.bundle_everything_checkbox.toggled.connect(
            self._handle_bundle_everything_toggled
        )

        self.settings_layout.addWidget(self.bundle_all_but_core_checkbox)
        self.settings_layout.addWidget(self.bundle_everything_checkbox)
        self.settings_layout.addWidget(self.bundle_non_qt_libs_checkbox)
        self.settings_layout.addWidget(self.no_strip_checkbox)
        self.settings_layout.addWidget(self.always_overwrite_checkbox)
        self.settings_layout.addWidget(self.verbose_label)
        self.settings_layout.addWidget(self.verbose_combobox)

        self.settings_groupbox.setLayout(self.settings_layout)

        # Action Buttons
        self.action_groupbox = QGroupBox("Actions")
        self.action_layout = QVBoxLayout()

        self.show_desktop_example_button = QPushButton("Show .desktop File Example")
        self.show_desktop_example_button.clicked.connect(
            self._show_desktop_file_example
        )

        self.show_icon_help_button = QPushButton("Show Icon Requirements")
        self.show_icon_help_button.clicked.connect(self._show_icon_help)

        self.show_version_button = QPushButton("Show Version")
        self.show_version_button.clicked.connect(self._show_version)

        self.show_blacklist_button = QPushButton("Show Blacklist")
        self.show_blacklist_button.clicked.connect(self._show_blacklist)

        self.action_layout.addWidget(self.show_desktop_example_button)
        self.action_layout.addWidget(self.show_icon_help_button)
        self.action_layout.addWidget(self.show_version_button)
        self.action_layout.addWidget(self.show_blacklist_button)
        self.action_groupbox.setLayout(self.action_layout)

        # Deploy Button
        self.deploy_button = QPushButton("Deploy Dependencies")
        self.deploy_button.setStyleSheet("font-size: 18px; padding: 10px;")
        self.deploy_button.clicked.connect(self._start_deploy)

        self.right_pane_layout.addWidget(self.settings_groupbox)
        self.right_pane_layout.addWidget(self.action_groupbox)
        self.right_pane_layout.addStretch(1)
        self.right_pane_layout.addWidget(self.deploy_button)

        self.main_layout.addLayout(self.left_pane_layout, 2)
        self.main_layout.addLayout(self.right_pane_layout, 1)

    def setup_logging(self):
        """Setup logging for this widget"""
        self.custom_logger = CustomLogger("INFO", "QtDeployerWidget")
        setup_gui_logging(self.console_output, self.custom_logger)

    def _browse_binary_path(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Application Binary or Shared Library",
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

    def _browse_qt_path(self):
        dir_path = QFileDialog.getExistingDirectory(
            self, "Select Qt Installation Directory", ""
        )
        if dir_path:
            self.qt_path_input.setText(dir_path)

    def _browse_desktop_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select .desktop File", "", "Desktop Files (*.desktop)"
        )
        if file_path:
            self.desktop_file_input.setText(file_path)

    def _browse_icon_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Application Icon File", "", "Image Files (*.png *.svg *.ico)"
        )
        if file_path:
            self.icon_file_input.setText(file_path)

    def _browse_apprun_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select AppRun Script File", "", "All Files (*)"
        )
        if file_path:
            self.apprun_file_input.setText(file_path)

    def _show_desktop_file_example(self):
        example_content = """[Desktop Entry]
Type=Application
Name=YourAppName
Comment=Brief description of your application
Exec=YourAppName
Icon=your-app-icon
Categories=Office;Utility;
Terminal=false
StartupNotify=true
MimeType=application/pdf;text/html;
"""
        message = f"""Example .desktop file content:

<pre><code>{example_content}</code></pre>

Save this content to a file like 'myapp.desktop' and use --desktop-file myapp.desktop"""
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Information)
        msg_box.setText(message)
        msg_box.setTextFormat(Qt.TextFormat.RichText)
        msg_box.setWindowTitle("Desktop File Example")
        msg_box.exec_()

    def _show_icon_help(self):
        message = """Icon file requirements:
   • Supported formats: PNG, SVG, ICO
   • Recommended size: 128x128 or higher
   • Should be square aspect ratio
   • Example: --icon resources/myapp.png"""
        self._show_message_box("Icon Requirements", message)

    def _show_version(self):
        self.custom_logger.info("linuxdeployqt-python version 1.0.0")
        self._show_message_box("Version", "linuxdeployqt-python version 1.0.0")

    def _show_blacklist(self):
        self.custom_logger.info("Displaying blacklisted libraries...")
        viewer = BlacklistViewer(GENERATED_EXCLUDE_LIST)
        viewer.exec_()

    def _handle_bundle_all_but_core_toggled(self, checked):
        if checked:
            self.bundle_everything_checkbox.setChecked(False)

    def _handle_bundle_everything_toggled(self, checked):
        if checked:
            self.bundle_all_but_core_checkbox.setChecked(False)

    def _show_message_box(self, title, message, icon=QMessageBox.Information):
        msg_box = QMessageBox()
        msg_box.setIcon(icon)
        msg_box.setText(message)
        msg_box.setWindowTitle(title)
        msg_box.exec_()

    def _start_deploy(self):
        """Handle deployment process when deploy button is clicked"""
        # Get all parameters from UI
        binary_path = self.binary_path_input.text().strip()
        deploy_path = self.deploy_path_input.text().strip()
        qml_dirs = [
            d.strip() for d in self.qml_dir_input.text().split(",") if d.strip()
        ]
        desktop_file = self.desktop_file_input.text().strip()
        icon_file = self.icon_file_input.text().strip()
        apprun_file = (
            self.apprun_file_input.text().strip()
            if self.apprun_file_input.text().strip()
            else None
        )
        qt_path = (
            self.qt_path_input.text().strip()
            if self.qt_path_input.text().strip()
            else None
        )

        # Get settings from checkboxes
        bundle_non_qt_libs = self.bundle_non_qt_libs_checkbox.isChecked()
        no_strip = self.no_strip_checkbox.isChecked()
        always_overwrite = self.always_overwrite_checkbox.isChecked()
        verbose_level = self.verbose_combobox.currentIndex()

        # Validate required fields
        if not all([binary_path, deploy_path, desktop_file, icon_file]):
            self._show_message_box(
                "Error", "Please fill all required fields", QMessageBox.Critical
            )
            return

        self.deploy_process = QProcess()
        self.deploy_process.readyReadStandardOutput.connect(self._handle_stdout)
        self.deploy_process.readyReadStandardError.connect(self._handle_stderr)
        self.deploy_process.finished.connect(self._handle_process_finished)

        composer = DeployCommandComposer(verbose_level=verbose_level)
        cmd = composer.compose_command(
            binary_path=binary_path,
            deploy_path=deploy_path,
            qml_dirs=qml_dirs,
            desktop_file=desktop_file,
            icon_file=icon_file,
            apprun_file=apprun_file,
            qt_path=qt_path,
            bundle_non_qt_libs=bundle_non_qt_libs,
            no_strip=no_strip,
            always_overwrite=always_overwrite,
        )

        self.deploy_process.start(cmd[0], cmd[1:])
        self.custom_logger.debug(f"Executing command: {' '.join(cmd)}")

    def _handle_stdout(self):
        if self.deploy_process is None:
            return
        data = self.deploy_process.readAllStandardOutput()
        stdout = bytes(data).decode("utf8")
        self.console_output.appendPlainText(stdout)

    def _handle_stderr(self):
        if self.deploy_process is None:
            return
        data = self.deploy_process.readAllStandardError()
        stderr = bytes(data).decode("utf8")
        self.console_output.appendPlainText(stderr)

    def _handle_process_finished(self, exit_code, exit_status):
        if exit_code == 0:
            self._show_message_box("Success", "Deployment completed successfully!")
        else:
            self._show_message_box("Error", "Deployment failed!", QMessageBox.Critical)
        self.deploy_process = None
