"""Range slider widget for constraint range selection."""

from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtCore import Signal, Qt, QRect, QSize
from PySide6.QtGui import QPainter, QColor, QPen
from typing import Optional, Tuple


class RangeSlider(QWidget):
    """A custom range slider widget for selecting a range between min and max values."""
    
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
        # Minimum number of notches the handles must be apart. 1 prevents overlap.
        self._min_separation: int = 1
        self.setMinimumHeight(22)
        
        try:
            self.setEnabled(True)
            self.setFocusPolicy(Qt.StrongFocus)
            self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        except Exception:
            pass
            
        try:
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.setMouseTracking(True)
        except Exception:
            pass

    def setRange(self, minimum: int, maximum: int):
        """Set the range of the slider."""
        self._min = int(minimum)
        self._max = max(int(maximum), self._min)
        self._low = min(max(self._low, self._min), self._max)
        self._high = min(max(self._high, self._min), self._max)
        # Enforce minimum separation after range change
        self._low, self._high = self._apply_min_separation(self._low, self._high)
        self.update()

    def setMinimumSeparation(self, separation: int):
        """Set the minimum required separation (in notches) between handles."""
        self._min_separation = max(0, int(separation))
        # Re-apply constraint to current values
        self._low, self._high = self._apply_min_separation(self._low, self._high)
        self.update()

    def setValues(self, low: int, high: int):
        """Set the current range values."""
        low = int(low)
        high = int(high)
        if low > high:
            low, high = high, low
        low = min(max(low, self._min), self._max)
        high = min(max(high, self._min), self._max)
        low, high = self._apply_min_separation(low, high)
        changed = (low != self._low) or (high != self._high)
        self._low, self._high = low, high
        if changed:
            self.rangeChanged.emit(self._low, self._high)
            self.update()

    def _setValuesInternal(self, low: int, high: int):
        """Internal value update without emitting signals - for drag operations."""
        low = int(low)
        high = int(high)
        if low > high:
            low, high = high, low
        low = min(max(low, self._min), self._max)
        high = min(max(high, self._min), self._max)
        low, high = self._apply_min_separation(low, high)
        self._low, self._high = low, high
        self.update()

    def _apply_min_separation(self, low: int, high: int) -> Tuple[int, int]:
        """Ensure that high - low >= effective minimum separation.
        Attempts to resolve according to the drag context for natural behavior.
        """
        # Effective separation cannot exceed the available span
        total_span = max(0, self._max - self._min)
        sep = min(max(0, self._min_separation), total_span)
        if sep <= 0:
            return low, high
        if (high - low) >= sep:
            return low, high

        # Need to adjust values to satisfy separation
        if self._dragging == 'low':
            # Keep high as requested, move low leftwards
            high = min(high, self._max)
            low = min(high - sep, self._max - sep)
            low = max(low, self._min)
        elif self._dragging == 'high':
            # Keep low as requested, move high rightwards
            low = max(low, self._min)
            high = max(low + sep, self._min + sep)
            high = min(high, self._max)
        elif self._dragging == 'band':
            # Maintain at least sep width while respecting bounds
            low = max(low, self._min)
            # Prefer expanding to the right if possible
            if low + sep <= self._max:
                high = low + sep
            else:
                high = self._max
                low = max(self._min, high - sep)
        else:
            # No specific drag context (programmatic set). Prefer expanding upwards.
            low = max(low, self._min)
            if low + sep <= self._max:
                high = low + sep
            else:
                high = self._max
                low = max(self._min, high - sep)
        return int(low), int(high)

    def values(self) -> Tuple[int, int]:
        """Get the current range values."""
        return self._low, self._high

    def _pos_to_value(self, x: int) -> int:
        """Convert a pixel position to a value."""
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
        """Convert a value to a pixel position."""
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
        """Provide a size hint for the widget."""
        try:
            return QSize(200, max(22, self.minimumHeight()))
        except Exception:
            return super().sizeHint()

    def paintEvent(self, event):
        """Paint the range slider."""
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
        """Handle mouse press events to start dragging."""
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
        """Handle mouse move events during dragging."""
        if not self._dragging:
            return
        x = int(event.position().x() if hasattr(event, 'position') else event.x())
        prev_low, prev_high = self._low, self._high
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
        # Emit live update if values changed
        if self._low != prev_low or self._high != prev_high:
            try:
                self.rangeChanged.emit(self._low, self._high)
            except Exception:
                pass
        try:
            event.accept()
        except Exception:
            pass

    def mouseReleaseEvent(self, event):
        """Handle mouse release events to finish dragging."""
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
