from __future__ import annotations

from typing import Dict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QGroupBox, QVBoxLayout, QFormLayout, QLabel, QComboBox

from .sidebar_widgets import ElementType


class SidebarCore(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.container = QGroupBox()
        self.container.setSizePolicy(self.sizePolicy())
        self.container.setStyleSheet(
            """
            QGroupBox { background-color: #242424; border: 1px solid #3f3f3f; border-radius: 6px; }
            QLabel { color: #f0f0f0; }
            """
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        outer.addWidget(self.container)

        self.form_layout = QFormLayout(self.container)
        self.form_layout.setLabelAlignment(Qt.AlignRight)
        self.form_layout.setVerticalSpacing(8)
        self.form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        # Header row for type selector
        self.type_label = QLabel("Type:")
        self.type_combo = QComboBox()
        self.type_combo.addItems([e.value for e in ElementType])

    def form(self) -> QFormLayout:
        return self.form_layout

    def set_type(self, et: ElementType) -> None:
        try:
            self.type_combo.blockSignals(True)
            idx = self.type_combo.findText(et.value)
            if idx >= 0:
                self.type_combo.setCurrentIndex(idx)
        finally:
            self.type_combo.blockSignals(False)

