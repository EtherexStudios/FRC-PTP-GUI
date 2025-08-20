"""Custom list widget for draggable path elements."""

from PySide6.QtWidgets import QListWidget
from PySide6.QtCore import Qt, Signal


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
