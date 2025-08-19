from __future__ import annotations

from typing import Dict, Tuple

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
        self._rows: Dict[str, QWidget] = {}

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

    # New helpers to mirror Sidebar inline range slider management
    def clear_inline_sliders(self) -> None:
        for k, slider in list(self._sliders.items()):
            try:
                parent = slider.parentWidget()
                if parent is not None and parent.layout() is not None:
                    try:
                        parent.layout().removeWidget(slider)
                    except Exception:
                        pass
                slider.deleteLater()
            except Exception:
                pass
            self._sliders.pop(k, None)
            self._rows.pop(k, None)

    def ensure_inline_slider(self, key: str, total: int, low: int, high: int, spin_row: QWidget, label_widget: QLabel) -> None:
        container = self._rows.get(key)
        if container is None:
            container = QWidget()
            from PySide6.QtWidgets import QVBoxLayout
            vbox = QVBoxLayout(container)
            vbox.setContentsMargins(0, 0, 0, 0)
            vbox.setSpacing(3)
            vbox.addWidget(spin_row)
            self._rows[key] = container
            self.form_layout.addRow(label_widget, container)
        vbox = container.layout()
        slider = self._sliders.get(key)
        if slider is None:
            slider = RangeSlider(1, total)
            self._sliders[key] = slider
            slider.rangeChanged.connect(lambda _l, _h, k=key: self.rangeChanged.emit(k, _l, _h))
        slider.setRange(1, max(1, total))
        slider.setValues(low, high)
        try:
            # Deduplicate
            for i in reversed(range(vbox.count())):
                w = vbox.itemAt(i).widget()
                if isinstance(w, RangeSlider) and w is not slider:
                    vbox.removeWidget(w)
                    w.deleteLater()
        except Exception:
            pass
        try:
            vbox.removeWidget(spin_row)
        except Exception:
            pass
        vbox.insertWidget(0, spin_row)
        if slider.parentWidget() is not container:
            try:
                slider.setParent(container)
            except Exception:
                pass
        vbox.insertWidget(1, slider)

