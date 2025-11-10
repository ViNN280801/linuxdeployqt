#!/usr/bin/env python3

from PyQt5.QtCore import pyqtSlot
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QTabWidget,
    QShortcut,
)

from .components.QtDeployerWidget import QtDeployerWidget
from .components.LddDeployerWidget import LddDeployerWidget
from .components.ElfPatcherWidget import ElfPatcherWidget


class DependencyDeployerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dependency Deployer for linuxdeployqt-python")
        self.setGeometry(100, 100, 1200, 800)

        # Setup keyboard shortcuts
        self.close_shortcut_w = QShortcut(QKeySequence("Ctrl+W"), self)
        self.close_shortcut_w.activated.connect(self._close_window)

        self.close_shortcut_q = QShortcut(QKeySequence("Ctrl+Q"), self)
        self.close_shortcut_q.activated.connect(self._close_window)

        # Setup UI
        self.setup_ui()

    def setup_ui(self):
        """Setup the main UI with tabbed interface"""
        # Create central widget
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        # Create main layout
        self.main_layout = QVBoxLayout(self.central_widget)

        # Create tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.North)
        self.tab_widget.setDocumentMode(True)

        # Create deployer widgets
        self.qt_deployer_widget = QtDeployerWidget()
        self.ldd_deployer_widget = LddDeployerWidget()
        self.elf_patcher_widget = ElfPatcherWidget()

        # Tabs
        self.tab_widget.addTab(self.qt_deployer_widget, "Qt Deployer")
        self.tab_widget.addTab(self.ldd_deployer_widget, "LDD Deployer")
        self.tab_widget.addTab(self.elf_patcher_widget, "ELF Patcher")

        # Add tab widget to main layout
        self.main_layout.addWidget(self.tab_widget)

    @pyqtSlot()
    def _close_window(self):
        """Close the application window"""
        self.close()
