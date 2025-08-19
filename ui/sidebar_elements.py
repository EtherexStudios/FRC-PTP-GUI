from __future__ import annotations

from typing import List

from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy, QListWidgetItem

from .sidebar_widgets import CustomList, PopupCombobox


class SidebarElements(QWidget):
    addElementSelected = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        # Title bar with add-element dropdown
        self.path_elements_bar = QWidget()
        self.path_elements_bar.setObjectName("pathElementsBar")
        self.path_elements_bar.setStyleSheet(
            """
            QWidget#pathElementsBar {
                background-color: #2f2f2f;
                border: 1px solid #4a4a4a;
                border-radius: 6px;
            }
            """
        )
        bar_layout = QHBoxLayout(self.path_elements_bar)
        bar_layout.setContentsMargins(8, 0, 8, 0)
        bar_layout.setSpacing(8)

        label = QLabel("Path Elements")
        label.setStyleSheet(
            """
            font-size: 14px;
            font-weight: bold;
            color: #eeeeee;
            background: transparent;
            border: none;
            padding: 6px 0;
            """
        )
        label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        bar_layout.addWidget(label)
        bar_layout.addStretch()

        self.add_element_pop = PopupCombobox()
        self.add_element_pop.setText("Add element")
        self.add_element_pop.button.setIconSize(QSize(16, 16))
        self.add_element_pop.button.setMinimumHeight(22)
        self.add_element_pop.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.add_element_pop.item_selected.connect(self.addElementSelected.emit)
        bar_layout.addWidget(self.add_element_pop)

        outer.addWidget(self.path_elements_bar)

        # Elements list
        self.points_list = CustomList()
        outer.addWidget(self.points_list)

    def set_add_items(self, items: List[str]) -> None:
        self.add_element_pop.clear()
        self.add_element_pop.add_items(items)

    def rebuild(self, item_names: List[str]) -> None:
        self.points_list.clear()
        for name in item_names:
            self.points_list.addItem(QListWidgetItem(name))

    def select_index(self, index: int) -> None:
        if index is None or index < 0 or index >= self.points_list.count():
            return
        try:
            self.points_list.setCurrentRow(index)
        except Exception:
            pass

    def get_selected_index(self) -> int | None:
        row = self.points_list.currentRow()
        return row if row >= 0 else None

