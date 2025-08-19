"""Custom widgets used in the sidebar."""

from PySide6.QtWidgets import (
    QWidget, QListWidget, QListWidgetItem, QPushButton, QMenu, 
    QHBoxLayout, QMessageBox, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QPoint, QSize, QRect, QEvent
from PySide6.QtGui import QIcon, QGuiApplication, QPainter, QColor, QPen
from typing import Optional, Tuple


class CustomList(QListWidget):
    """A custom list widget with drag-and-drop reordering and delete key support."""
    
    reordered = Signal()  # Emitted when items are reordered
    deleteRequested = Signal()  # Emitted when delete key is pressed

    def __init__(self):
        super().__init__()
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDragDropOverwriteMode(False)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QListWidget.InternalMove)
        self.setAcceptDrops(True)

    def dropEvent(self, event):
        super().dropEvent(event)
        # Emit reordered signal after items are reordered
        self.reordered.emit()

    def keyPressEvent(self, event):
        try:
            if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                self.deleteRequested.emit()
                event.accept()
                return
        except Exception:
            pass
        super().keyPressEvent(event)


class PopupCombobox(QWidget):
    """A button that shows a popup menu when clicked."""
    
    item_selected = Signal(str)

    def __init__(self):
        super().__init__()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.button = QPushButton("Add property")
        self.button.setIcon(QIcon("assets/add_icon.png"))
        self.button.setIconSize(QSize(16, 16))
        self.button.setToolTip("Add an optional property")
        self.button.setStyleSheet("QPushButton { border: none; padding: 2px 6px; margin-left: 8px; }")
        self.button.setMinimumHeight(22)

        self.menu = QMenu(self)
        self.button.clicked.connect(self.show_menu)

        layout.addWidget(self.button)
        
    def show_menu(self):
        # Check if menu is empty and show message if so
        if self.menu.isEmpty():
            QMessageBox.information(self, "Constraints", "All constraints added")
            return
            
        # Reset any previous size caps
        try:
            self.menu.setMinimumHeight(0)
            self.menu.setMaximumHeight(16777215)  # effectively unlimited
        except Exception:
            pass

        # Compute available space below the button on the current screen
        global_below = self.button.mapToGlobal(QPoint(0, self.button.height()))
        screen = QGuiApplication.screenAt(global_below)
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        avail_geom = screen.availableGeometry() if screen else None

        # Desired size based on current actions
        desired = self.menu.sizeHint()
        desired_width = max(desired.width(), self.button.width())
        desired_height = desired.height()

        # Space below the button (expand downward when possible)
        if avail_geom is not None:
            space_below = int(avail_geom.bottom() - global_below.y() - 8)  # small margin
            if desired_height <= space_below:
                try:
                    self.menu.setFixedHeight(desired_height)
                except Exception:
                    pass
            else:
                # Cap to available space below; menu will auto-provide scroll arrows if needed
                try:
                    self.menu.setMaximumHeight(max(100, space_below))
                except Exception:
                    pass

        # Ensure the menu is at least as wide as the button
        try:
            self.menu.setMinimumWidth(int(desired_width))
        except Exception:
            pass

        self.menu.popup(global_below)

    def add_items(self, items):
        self.menu.clear()
        for item in items:
            action = self.menu.addAction(item)
            action.triggered.connect(lambda checked=False, text=item: self.item_selected.emit(text))
            
    def setText(self, text: str):
        self.button.setText(text)
        
    def setSize(self, size: QSize):
        self.button.setFixedSize(size)
        self.button.setIconSize(size)

    def setIcon(self, icon: QIcon):
        self.button.setIcon(icon)

    def setToolTip(self, text: str):
        self.button.setToolTip(text)

    def setStyleSheet(self, style: str):
        self.button.setStyleSheet(style)

    def clear(self):
        self.menu.clear()


class RangeSlider(QWidget):
    """A custom range slider widget for selecting value ranges."""
    
    rangeChanged = Signal(int, int)
    interactionFinished = Signal(int, int)

    def __init__(self, minimum: int = 1, maximum: int = 1, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._min = int(minimum)
        self._max = int(maximum)
        self._low = int(minimum)
        self._high = int(maximum)
        self._dragging: Optional[str] = None  # 'low' | 'high' | 'band'
        self._press_value: int = self._low
        self._band_width: int = max(0, self._high - self._low)
        self._press_low: int = self._low
        self.setMinimumHeight(22)
        try:
            self.setEnabled(True)
            self.setFocusPolicy(Qt.StrongFocus)
            self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        except Exception:
            pass
        try:
            from PySide6.QtWidgets import QSizePolicy
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.setMouseTracking(True)
        except Exception:
            pass

    def setRange(self, minimum: int, maximum: int):
        self._min = int(minimum)
        self._max = max(int(maximum), self._min)
        self._low = min(max(self._low, self._min), self._max)
        self._high = min(max(self._high, self._min), self._max)
        self.update()

    def setValues(self, low: int, high: int):
        low = int(low)
        high = int(high)
        if low > high:
            low, high = high, low
        low = min(max(low, self._min), self._max)
        high = min(max(high, self._min), self._max)
        changed = (low != self._low) or (high != self._high)
        self._low, self._high = low, high
        if changed:
            self.rangeChanged.emit(self._low, self._high)
            self.update()

    def _setValuesInternal(self, low: int, high: int):
        """Internal value update without emitting signals - for drag operations"""
        low = int(low)
        high = int(high)
        if low > high:
            low, high = high, low
        low = min(max(low, self._min), self._max)
        high = min(max(high, self._min), self._max)
        self._low, self._high = low, high
        self.update()

    def values(self) -> Tuple[int, int]:
        return self._low, self._high

    def _pos_to_value(self, x: int) -> int:
        rect = self.contentsRect()
        if rect.width() <= 0:
            return self._min
        # Account for padding to match _value_to_pos
        handle_w = max(8, max(3, rect.height() // 6) * 2)
        padding = handle_w // 2
        usable_width = max(1.0, float(rect.width() - 2 * padding))
        ratio = (x - rect.left() - padding) / usable_width
        ratio = max(0.0, min(1.0, ratio))  # Clamp to valid range
        val = self._min + ratio * (self._max - self._min)
        return int(round(val))

    def _value_to_pos(self, v: int) -> int:
        rect = self.contentsRect()
        if self._max == self._min:
            return rect.left()
        # Add padding to prevent handle clipping at edges
        handle_w = max(8, max(3, rect.height() // 6) * 2)
        padding = handle_w // 2
        usable_width = max(1, rect.width() - 2 * padding)
        ratio = (float(v) - self._min) / float(self._max - self._min)
        return int(rect.left() + padding + ratio * usable_width)

    def sizeHint(self):
        try:
            from PySide6.QtCore import QSize
            return QSize(200, max(22, self.minimumHeight()))
        except Exception:
            return super().sizeHint()

    def paintEvent(self, event):
        painter = QPainter(self)
        rect = self.contentsRect()
        track_h = max(3, rect.height() // 6)
        cy = rect.center().y()
        # Track
        pen = QPen(QColor('#666666'), 1)
        painter.setPen(pen)
        painter.setBrush(QColor('#444444'))
        painter.drawRect(QRect(rect.left(), cy - track_h // 2, rect.width(), track_h))
        # Tick marks at integer positions
        try:
            total = max(1, self._max - self._min)
            # Limit number of ticks to avoid clutter (aim ~20 max)
            step = 1
            if total > 20:
                # choose a step that results in ~20 ticks
                step = max(1, (total // 20))
            painter.setPen(QPen(QColor('#aaaaaa'), 1))
            tick_h = max(4, track_h)
            for v in range(self._min, self._max + 1, step):
                x = self._value_to_pos(v)
                painter.drawLine(x, cy - tick_h, x, cy + tick_h)
        except Exception:
            pass
        # Selected range
        x1 = self._value_to_pos(self._low)
        x2 = self._value_to_pos(self._high)
        painter.setBrush(QColor('#15c915'))
        painter.setPen(Qt.NoPen)
        painter.drawRect(QRect(min(x1, x2), cy - track_h // 2, abs(x2 - x1), track_h))
        # Handles
        handle_w = max(8, track_h * 2)
        painter.setBrush(QColor('#dddddd'))
        painter.setPen(QPen(QColor('#222222'), 1))
        painter.drawRect(QRect(x1 - handle_w // 2, cy - track_h, handle_w, track_h * 2))
        painter.drawRect(QRect(x2 - handle_w // 2, cy - track_h, handle_w, track_h * 2))

    def mousePressEvent(self, event):
        x = int(event.position().x() if hasattr(event, 'position') else event.x())
        y = int(event.position().y() if hasattr(event, 'position') else event.y())
        x1 = self._value_to_pos(self._low)
        x2 = self._value_to_pos(self._high)
        if x1 > x2:
            x1, x2 = x2, x1
        rect = self.contentsRect()
        cy = rect.center().y()
        track_h = max(3, rect.height() // 6)
        handle_w = max(8, track_h * 2)
        # Make clickable area larger than visual handle for easier dragging
        click_padding = 4
        low_rect = QRect(x1 - handle_w // 2 - click_padding, cy - track_h - click_padding, 
                       handle_w + 2 * click_padding, track_h * 2 + 2 * click_padding)
        high_rect = QRect(x2 - handle_w // 2 - click_padding, cy - track_h - click_padding, 
                        handle_w + 2 * click_padding, track_h * 2 + 2 * click_padding)
        if low_rect.contains(x, y):
            self._dragging = 'low'
            self._setValuesInternal(self._pos_to_value(x), self._high)
        elif high_rect.contains(x, y):
            self._dragging = 'high'
            self._setValuesInternal(self._low, self._pos_to_value(x))
        elif x1 <= x <= x2:
            # Drag band
            self._dragging = 'band'
            self._press_value = self._pos_to_value(x)
            self._band_width = max(0, self._high - self._low)
            self._press_low = self._low
        else:
            # Click on track outside -> move nearest handle
            if abs(x - x1) <= abs(x - x2):
                self._dragging = 'low'
                self._setValuesInternal(self._pos_to_value(x), self._high)
            else:
                self._dragging = 'high'
                self._setValuesInternal(self._low, self._pos_to_value(x))
        # Accept event, focus, and emit preview
        try:
            event.accept()
        except Exception:
            pass
        try:
            self.setFocus(Qt.MouseFocusReason)
        except Exception:
            pass
        try:
            self.rangeChanged.emit(self._low, self._high)
        except Exception:
            pass

    def mouseMoveEvent(self, event):
        if not self._dragging:
            return
        x = int(event.position().x() if hasattr(event, 'position') else event.x())
        if self._dragging == 'low':
            self._setValuesInternal(self._pos_to_value(x), self._high)
        elif self._dragging == 'high':
            self._setValuesInternal(self._low, self._pos_to_value(x))
        elif self._dragging == 'band':
            curr_val = self._pos_to_value(x)
            delta = curr_val - self._press_value
            new_low = self._press_low + delta
            new_high = new_low + self._band_width
            # Clamp to bounds
            if new_low < self._min:
                new_low = self._min
                new_high = self._band_width + new_low
            if new_high > self._max:
                new_high = self._max
                new_low = new_high - self._band_width
            self._setValuesInternal(int(new_low), int(new_high))
        try:
            event.accept()
        except Exception:
            pass

    def mouseReleaseEvent(self, event):
        # Finalize drag, emit signals to update model and show preview
        try:
            event.accept()
        except Exception:
            pass
        
        # Only emit signals if we were actually dragging
        was_dragging = self._dragging is not None
        self._dragging = None
        
        if was_dragging:
            try:
                self.rangeChanged.emit(self._low, self._high)
            except Exception:
                pass
            try:
                self.interactionFinished.emit(self._low, self._high)
            except Exception:
                pass