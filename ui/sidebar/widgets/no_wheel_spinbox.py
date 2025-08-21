from PySide6.QtWidgets import QDoubleSpinBox
from PySide6.QtCore import Qt


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox that ignores mouse wheel events to prevent accidental value changes."""

    def wheelEvent(self, event):  # type: ignore[override]
        # Ignore wheel events unless the spinbox has explicit focus and Ctrl is held
        try:
            if self.hasFocus() and (event.modifiers() & Qt.ControlModifier):
                return super().wheelEvent(event)
        except Exception:
            pass
        event.ignore()


