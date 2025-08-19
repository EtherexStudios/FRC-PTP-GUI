"""Path Elements section of the sidebar."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy, QListWidgetItem
)
from PySide6.QtCore import Signal, QSize
from typing import Optional, List
from .custom_widgets import CustomList, PopupCombobox
from models.path_model import Path, TranslationTarget, RotationTarget, Waypoint


class PathElementsSection(QWidget):
    """Widget for the path elements list and controls."""
    
    # Signals
    elementSelected = Signal(int)  # index
    deleteRequested = Signal()
    addElementRequested = Signal(str)  # element type
    reordered = Signal()
    
    def __init__(self):
        super().__init__()
        self._path: Optional[Path] = None
        self._suspended = False
        self._ready = False
        self._last_selected_index = 0
        
        self._init_ui()
        
    def _init_ui(self):
        """Initialize the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Title bar
        self.title_bar = self._create_title_bar()
        layout.addWidget(self.title_bar)
        
        # Elements list
        self.points_list = CustomList()
        self.points_list.itemSelectionChanged.connect(self._on_item_selected)
        self.points_list.reordered.connect(self._on_list_reordered)
        self.points_list.deleteRequested.connect(lambda: self.deleteRequested.emit())
        layout.addWidget(self.points_list)
        
    def _create_title_bar(self) -> QWidget:
        """Create the title bar with label and add button."""
        title_bar = QWidget()
        title_bar.setObjectName("pathElementsBar")
        title_bar.setStyleSheet("""
            QWidget#pathElementsBar {
                background-color: #2f2f2f;
                border: 1px solid #4a4a4a;
                border-radius: 6px;
            }
        """)
        
        layout = QHBoxLayout(title_bar)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(8)
        
        # Label
        label = QLabel("Path Elements")
        label.setStyleSheet("""
            font-size: 14px;
            font-weight: bold;
            color: #eeeeee;
            background: transparent;
            border: none;
            padding: 6px 0;
        """)
        label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        layout.addWidget(label)
        layout.addStretch()
        
        # Add element button
        self.add_element_pop = PopupCombobox()
        self.add_element_pop.setText("Add element")
        self.add_element_pop.setToolTip("Add a path element at the current selection")
        self.add_element_pop.button.setIconSize(QSize(16, 16))
        self.add_element_pop.button.setMinimumHeight(22)
        self.add_element_pop.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.add_element_pop.item_selected.connect(self._on_add_element_selected)
        layout.addWidget(self.add_element_pop)
        
        return title_bar
        
    def set_path(self, path: Path):
        """Set the path model."""
        self._path = path
        self.rebuild_list()
        
    def set_suspended(self, suspended: bool):
        """Set whether updates are suspended."""
        self._suspended = suspended
        
    def mark_ready(self):
        """Mark the section as ready."""
        self._ready = True
        
    def rebuild_list(self):
        """Rebuild the elements list from the path model."""
        if self._path is None:
            self.points_list.clear()
            return
            
        self.points_list.clear()
        for i, element in enumerate(self._path.path_elements):
            item_text = self._get_element_display_text(i, element)
            item = QListWidgetItem(item_text)
            self.points_list.addItem(item)
            
        # Restore selection
        count = self.points_list.count()
        if count > 0:
            idx_to_select = min(self._last_selected_index, count - 1)
            self.points_list.setCurrentRow(idx_to_select)
            
        self._refresh_add_dropdown_items()
        
    def _get_element_display_text(self, index: int, element) -> str:
        """Get display text for an element."""
        if isinstance(element, TranslationTarget):
            return f"{index + 1}. Translation"
        elif isinstance(element, RotationTarget):
            return f"{index + 1}. Rotation"
        elif isinstance(element, Waypoint):
            return f"{index + 1}. Waypoint"
        return f"{index + 1}. Unknown"
        
    def _refresh_add_dropdown_items(self):
        """Update the add element dropdown options."""
        if self._path is None:
            self.add_element_pop.clear()
            return
            
        selected_idx = self.get_selected_index()
        if selected_idx is None:
            # No selection - can only add to end
            items = ["Translation at end", "Waypoint at end"]
            # Can add rotation at end only if there are at least 2 elements
            if len(self._path.path_elements) >= 2:
                items.append("Rotation at end")
        else:
            # Have selection - can add before or after
            items = []
            can_add_rotation_before = selected_idx > 0
            can_add_rotation_after = selected_idx < len(self._path.path_elements) - 1
            
            items.extend(["Translation before", "Translation after"])
            items.extend(["Waypoint before", "Waypoint after"])
            
            if can_add_rotation_before:
                items.append("Rotation before")
            if can_add_rotation_after:
                items.append("Rotation after")
                
        self.add_element_pop.add_items(items)
        
    def get_selected_index(self) -> Optional[int]:
        """Get the currently selected element index."""
        row = self.points_list.currentRow()
        if row is None or row < 0:
            return None
        if self._path is None:
            return None
        if row >= len(self._path.path_elements):
            return None
        return row
        
    def select_index(self, index: int):
        """Select an element by index."""
        if index < 0 or index >= self.points_list.count():
            return
        self.points_list.setCurrentRow(index)
        
    def _on_item_selected(self):
        """Handle item selection."""
        if self._suspended or not self._ready:
            return
            
        idx = self.get_selected_index()
        if idx is None:
            return
            
        self._last_selected_index = idx
        self._refresh_add_dropdown_items()
        self.elementSelected.emit(idx)
        
    def _on_list_reordered(self):
        """Handle list reordering."""
        self.reordered.emit()
        
    def _on_add_element_selected(self, option: str):
        """Handle add element menu selection."""
        self.addElementRequested.emit(option)