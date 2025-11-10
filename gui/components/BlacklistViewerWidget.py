from PyQt5.QtGui import QKeySequence
from PyQt5.QtCore import pyqtSlot
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QShortcut,
)


class BlacklistViewer(QDialog):
    def __init__(self, blacklist_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Blacklisted Libraries")
        self.setGeometry(200, 200, 800, 600)

        self.main_layout = QVBoxLayout(self)

        self.table_widget = QTableWidget()
        self.main_layout.addWidget(self.table_widget)

        self._populate_table(blacklist_data)

        # Set up shortcuts for closing the window
        self.close_shortcut_w = QShortcut(QKeySequence("Ctrl+W"), self)
        self.close_shortcut_w.activated.connect(self._close_window)

        self.close_shortcut_q = QShortcut(QKeySequence("Ctrl+Q"), self)
        self.close_shortcut_q.activated.connect(self._close_window)

    @pyqtSlot()
    def _close_window(self):
        self.close()

    def _populate_table(self, blacklist_data):
        num_columns = 6
        num_rows = (len(blacklist_data) + num_columns - 1) // num_columns

        self.table_widget.setRowCount(num_rows)
        self.table_widget.setColumnCount(num_columns)
        self.table_widget.setHorizontalHeaderLabels(
            [f"Column {i+1}" for i in range(num_columns)]
        )

        # Show and set row numbers
        vertical_header = self.table_widget.verticalHeader()
        if vertical_header is not None:
            vertical_header.setVisible(True)
            vertical_header.setSectionResizeMode(QHeaderView.Fixed)
            row_labels = [f"Row {i+1}" for i in range(num_rows)]
            self.table_widget.setVerticalHeaderLabels(row_labels)

        # Resize columns to fit content
        horizontal_header = self.table_widget.horizontalHeader()
        if horizontal_header is not None:
            horizontal_header.setSectionResizeMode(QHeaderView.Stretch)

        row = 0
        col = 0
        for item in blacklist_data:
            table_item = QTableWidgetItem(str(item))
            self.table_widget.setItem(row, col, table_item)
            col += 1
            if col >= num_columns:
                col = 0
                row += 1
