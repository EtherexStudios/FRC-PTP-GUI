"""Custom list widget for draggable path elements."""

from PySide6.QtWidgets import QListWidget
from PySide6.QtCore import Qt, Signal, QTimer


class PersistentCustomList(QListWidget):
    """A CustomList that automatically remembers and restores its scroll position."""

    reordered = Signal()  # Emitted when items are reordered via drag-and-drop
    deleteRequested = Signal()  # Emitted when delete key is pressed

    def __init__(self):
        super().__init__()
        self._last_scroll_value = 0
        self._suppress_scroll_events = False
        self._preserve_scroll = False
        self._auto_scroll_disabled = False
        self.verticalScrollBar().valueChanged.connect(self._on_scroll_changed)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDragDropOverwriteMode(False)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QListWidget.InternalMove)  # InternalMove for flat reordering
        self.setAcceptDrops(True)

    def _on_scroll_changed(self, value):
        """Remember the scroll position when it changes."""
        if not self._suppress_scroll_events and not self._auto_scroll_disabled:
            self._last_scroll_value = value
            # print(f"PersistentCustomList: Scroll position changed to {value}")

    def begin_scroll_preservation(self):
        """Start preserving scroll position during bulk operations."""
        self._preserve_scroll = True
        self._last_scroll_value = self.verticalScrollBar().value()
        # print(f"PersistentCustomList: Beginning scroll preservation at {self._last_scroll_value}")

    def end_scroll_preservation(self):
        """End scroll preservation and restore position."""
        self._preserve_scroll = False
        self.restore_scroll_position()

    def restore_scroll_position(self):
        """Restore the remembered scroll position."""
        if hasattr(self, '_last_scroll_value'):
            current_value = self.verticalScrollBar().value()
            if current_value != self._last_scroll_value:
                # print(f"PersistentCustomList: Restoring scroll from {current_value} to {self._last_scroll_value}")
                self._suppress_scroll_events = True
                self.verticalScrollBar().setValue(self._last_scroll_value)
                self._suppress_scroll_events = False
                # Force another restoration in case Qt overrides it
                QTimer.singleShot(0, lambda: self._force_restore_scroll())
                return True
        return False

    def _force_restore_scroll(self):
        """Force restore scroll position after a delay."""
        if hasattr(self, '_last_scroll_value') and not self._preserve_scroll:
            current_value = self.verticalScrollBar().value()
            if current_value != self._last_scroll_value:
                # print(f"PersistentCustomList: Force restoring scroll from {current_value} to {self._last_scroll_value}")
                self.verticalScrollBar().setValue(self._last_scroll_value)

    def setCurrentRow(self, row):
        """Override setCurrentRow to prevent auto-scrolling when disabled."""
        if self._auto_scroll_disabled:
            # Temporarily disable auto-scrolling and suppress scroll events
            old_auto_scroll = bool(self.doAutoScroll())
            self.setAutoScroll(False)
            self._suppress_scroll_events = True

            # Capture current scroll position
            current_scroll = self.verticalScrollBar().value()

            super().setCurrentRow(row)

            # Force restore scroll position and re-enable features
            self.verticalScrollBar().setValue(current_scroll)
            self.setAutoScroll(old_auto_scroll)
            self._suppress_scroll_events = False
        else:
            super().setCurrentRow(row)

    def disable_auto_scroll_temporarily(self):
        """Disable auto-scrolling for subsequent operations."""
        self._auto_scroll_disabled = True

    def enable_auto_scroll(self):
        """Re-enable auto-scrolling."""
        self._auto_scroll_disabled = False

    def dropEvent(self, event):
        """Handle drop events to emit reordered signal."""
        super().dropEvent(event)
        # Do not mutate item data or text here; items already reordered visually.
        # Emitting reordered lets the owner update the underlying model.
        self.reordered.emit()

    def keyPressEvent(self, event):
        """Handle key press events to support delete operations."""
        try:
            if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                self.deleteRequested.emit()
                event.accept()
                return
        except Exception:
            pass
        super().keyPressEvent(event)


class CustomList(QListWidget):
    """A customized QListWidget that supports drag-and-drop reordering and delete operations."""
    
    reordered = Signal()  # Emitted when items are reordered via drag-and-drop
    deleteRequested = Signal()  # Emitted when delete key is pressed

    def __init__(self):
        super().__init__()
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDragDropOverwriteMode(False)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QListWidget.InternalMove)  # InternalMove for flat reordering
        self.setAcceptDrops(True)

    def dropEvent(self, event):
        """Handle drop events to emit reordered signal."""
        super().dropEvent(event)
        # Do not mutate item data or text here; items already reordered visually.
        # Emitting reordered lets the owner update the underlying model.
        self.reordered.emit()

    def keyPressEvent(self, event):
        """Handle key press events to support delete operations."""
        try:
            if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                self.deleteRequested.emit()
                event.accept()
                return
        except Exception:
            pass
        super().keyPressEvent(event)
