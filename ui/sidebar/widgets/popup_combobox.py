"""Popup combobox widget for adding optional properties."""

from PySide6.QtWidgets import QWidget, QPushButton, QMenu, QHBoxLayout, QMessageBox
from PySide6.QtCore import Signal, QPoint, QSize
from PySide6.QtGui import QIcon, QGuiApplication


class PopupCombobox(QWidget):
    """A button that shows a popup menu when clicked, used for adding optional properties."""
    
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
        """Show the popup menu with proper positioning."""
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
        """Add items to the menu."""
        self.menu.clear()
        for item in items:
            action = self.menu.addAction(item)
            action.triggered.connect(lambda checked=False, text=item: self.item_selected.emit(text))
            
    def setText(self, text: str):
        """Set the button text."""
        self.button.setText(text)
        
    def setSize(self, size: QSize):
        """Set the button size."""
        self.button.setFixedSize(size)
        self.button.setIconSize(size)

    def setIcon(self, icon: QIcon):
        """Set the button icon."""
        self.button.setIcon(icon)

    def setToolTip(self, text: str):
        """Set the button tooltip."""
        self.button.setToolTip(text)

    def setStyleSheet(self, style: str):
        """Set the button stylesheet."""
        self.button.setStyleSheet(style)

    def clear(self):
        """Clear all menu items."""
        self.menu.clear()
