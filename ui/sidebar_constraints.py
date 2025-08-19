from __future__ import annotations

from typing import Dict

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QGroupBox, QVBoxLayout, QFormLayout, QLabel

from .sidebar_widgets import RangeSlider


class SidebarConstraints(QWidget):
    rangeChanged = Signal(str, int, int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.container = QGroupBox()
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

        self._sliders: Dict[str, RangeSlider] = {}

    def form(self) -> QFormLayout:
        return self.form_layout

    def ensure_slider(self, key: str, low: int, high: int, total: int, label_widget: QLabel, field_container: QWidget) -> RangeSlider:
        slider = self._sliders.get(key)
        if slider is None:
            slider = RangeSlider(1, total)
            slider.setValues(low, high)
            slider.rangeChanged.connect(lambda l, h, k=key: self.rangeChanged.emit(k, l, h))
            self._sliders[key] = slider
        else:
            slider.setRange(1, total)
            slider.setValues(low, high)
        return slider

