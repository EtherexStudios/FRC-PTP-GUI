"""Main sidebar widget for path element management."""

from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QComboBox,
    QGroupBox, QSizePolicy, QSpacerItem, QListWidgetItem, QPushButton,
    QScrollArea
)
from PySide6.QtCore import Qt, Signal, QTimer, QEvent, QSize
from PySide6.QtGui import QIcon
from models.path_model import Path, TranslationTarget, RotationTarget, Waypoint

from .widgets import CustomList, PopupCombobox
from .components import ElementManager, ConstraintManager, PropertyEditor
from .utils import ElementType, SPINNER_METADATA, PATH_CONSTRAINT_KEYS


class Sidebar(QWidget):
    """Main sidebar widget for editing path elements and their properties."""
    
    # Emitted when a list item is selected in the sidebar
    elementSelected = Signal(int)  # index
    # Emitted when attributes are changed through the UI (positions, rotation, etc.)
    modelChanged = Signal()
    # Emitted when structure changes (reorder, type switch)
    modelStructureChanged = Signal()
    # Emitted when user requests deletion via keyboard
    deleteSelectedRequested = Signal()
    # Emitted right before the model is mutated; provides a human-readable description
    aboutToChange = Signal(str)
    # Emitted after the model is mutated; provides a human-readable description
    userActionOccurred = Signal(str)
    
    # Forward constraint preview signals
    constraintRangePreviewRequested = Signal(str, int, int)  # key, start_ordinal, end_ordinal
    constraintRangePreviewCleared = Signal()
    
    def __init__(self, path=Path()):
        super().__init__()
        self.path = path
        self.project_manager = None  # Set externally to access config defaults
        
        # Re-entrancy/visibility guards
        self._suspended: bool = False
        self._ready: bool = False
        # Track last selected index for restoration when paths are reloaded
        self._last_selected_index: int = 0
        
        # Initialize components
        self.element_manager = ElementManager(self)
        self.constraint_manager = ConstraintManager(self)
        self.property_editor = PropertyEditor(self)
        
        # Set up UI
        self._setup_ui()
        
        # Connect component signals
        self._connect_component_signals()
        
        # Project manager will be set externally, so defer component setup
        
        # Initialize data
        self.set_path(path)
        
        # Mark as ready
        self.mark_ready()
        
    def _setup_ui(self):
        """Set up the UI layout and widgets."""
        main_layout = QVBoxLayout(self)
        # Lock the entire sidebar to a fixed width so it doesn't resize
        self.setFixedWidth(300)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        # Top section: Path Elements title bar with add button
        self._create_path_elements_bar(main_layout)
        
        # Elements list
        self.points_list = CustomList()
        # Set size policy to prevent unwanted expansion
        self.points_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # Set a reasonable fixed height to prevent it from expanding/contracting
        self.points_list.setFixedHeight(200)
        # Enable scrolling for long lists
        self.points_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        main_layout.addWidget(self.points_list)
        
        # Connect list signals
        self.points_list.itemSelectionChanged.connect(self.on_item_selected)
        self.points_list.reordered.connect(self.on_points_list_reordered)
        self.points_list.deleteRequested.connect(lambda: self._delete_via_shortcut())

        main_layout.addSpacing(10)  # Add space between list and groupbox

        # Element Properties section
        self._create_properties_section(main_layout)
        
        # Path Constraints section
        self._create_constraints_section(main_layout)
        
    # No stretch at bottom so last expanding sections (properties / constraints) fill space
        
        # Install event filter for constraint preview handling
        self.installEventFilter(self)
        
    def _create_path_elements_bar(self, parent_layout):
        """Create the Path Elements title bar with add button."""
        top_section = QWidget()
        top_layout = QHBoxLayout(top_section)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(20)
        
        # Path Elements title bar
        self.path_elements_bar = QWidget()
        self.path_elements_bar.setObjectName("pathElementsBar")
        self.path_elements_bar.setStyleSheet("""
            QWidget#pathElementsBar {
                background-color: #2f2f2f;
                border: 1px solid #4a4a4a;
                border-radius: 6px;
            }
        """)
        
        path_elements_bar_layout = QHBoxLayout(self.path_elements_bar)
        path_elements_bar_layout.setContentsMargins(8, 0, 8, 0)
        path_elements_bar_layout.setSpacing(8)

        path_elements_label = QLabel("Path Elements")
        path_elements_label.setStyleSheet("""
            font-size: 14px;
            font-weight: bold;
            color: #eeeeee;
            background: transparent;
            border: none;
            padding: 6px 0;
        """)
        path_elements_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        path_elements_bar_layout.addWidget(path_elements_label)
        path_elements_bar_layout.addStretch()
        
        # Add element button
        self.add_element_pop = PopupCombobox()
        self.add_element_pop.setText("Add element")
        self.add_element_pop.setToolTip("Add a path element at the current selection")
        self.add_element_pop.button.setIconSize(QSize(16, 16))
        self.add_element_pop.button.setMinimumHeight(22)
        self.add_element_pop.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.add_element_pop.item_selected.connect(self.on_add_element_selected)
        
        path_elements_bar_layout.addWidget(self.add_element_pop)
        top_layout.addWidget(self.path_elements_bar, 1)
        parent_layout.addWidget(top_section)
        
    def _create_properties_section(self, parent_layout):
        """Create the Element Properties section."""
        # Title bar
        self.title_bar = QWidget()
        self.title_bar.setObjectName("titleBar")
        self.title_bar.setStyleSheet("""
            QWidget#titleBar {
                background-color: #2f2f2f;
                border: 1px solid #4a4a4a;
                border-radius: 6px;
            }
        """)
        title_bar_layout = QHBoxLayout(self.title_bar)
        title_bar_layout.setContentsMargins(10, 0, 10, 0)
        title_bar_layout.setSpacing(0)
        
        title_label = QLabel("Element Properties")
        title_label.setStyleSheet("""
            font-size: 14px; 
            font-weight: bold;
            color: #eeeeee;
            background: transparent;
            border: none;
            padding: 6px 0;
        """)
        title_bar_layout.addWidget(title_label)
        title_bar_layout.addStretch()
        
        parent_layout.addWidget(self.title_bar)
        
        # Form container
        self.form_container = QGroupBox()
        self.form_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.form_container.setStyleSheet("""
            QGroupBox { background-color: #242424; border: 1px solid #3f3f3f; border-radius: 6px; }
            QLabel { color: #f0f0f0; }
            /* Unified rounded boxes for each individual core property row to match constraints */
            QWidget[constraintRow='true'] { background: #2a2a2a; border: 1px solid #3b3b3b; border-radius: 6px; margin: 4px 0; }
        """)
        
        # Main layout for the group box
        group_box_spinner_layout = QVBoxLayout(self.form_container)
        # Match constraints: reduce outer left/right padding; tighter vertical spacing
        group_box_spinner_layout.setContentsMargins(0, 6, 0, 6)
        group_box_spinner_layout.setSpacing(4)

        # Type selector and properties form
        self.core_page = QWidget()
        self.core_page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.core_layout = QFormLayout(self.core_page)
        self.core_layout.setLabelAlignment(Qt.AlignRight)
        # Reduce row spacing to match constraints
        self.core_layout.setVerticalSpacing(4)
        # Remove extra content margins so row widgets align with container padding
        try:
            self.core_layout.setContentsMargins(0, 0, 0, 0)
        except Exception:
            pass
        self.core_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        # Type selector
        self.optional_container = QWidget()
        self.optional_box_layout = QHBoxLayout(self.optional_container)
        self.optional_box_layout.setContentsMargins(0, 0, 0, 0)

        self.type_combo = QComboBox()
        self.type_combo.addItems([e.value for e in ElementType])
        self.type_combo.currentTextChanged.connect(self.on_type_change)
        self.type_label = QLabel("Type:")

        self.optional_box_layout.addWidget(self.type_combo)

        # Put the type selector above the properties (styled like constraint rows)
        header_row = QWidget()
        header_row.setProperty('constraintRow', 'true')
        header_row_layout = QHBoxLayout(header_row)
        # Reduce top/bottom padding inside the combobox bordered box and tighten right padding
        header_row_layout.setContentsMargins(8, 7, 0, 4)
        header_row_layout.setSpacing(6)
        try:
            # Keep natural height; only constrain width/alignment
            header_row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        except Exception:
            pass
        header_row_layout.addWidget(self.type_label)
        header_row_layout.addStretch()
        try:
            self.optional_container.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        except Exception:
            pass
        header_row_layout.addWidget(self.optional_container)
        # Wrap header to enforce same left/right padding as other rows
        header_wrap = QWidget()
        header_wrap_layout = QHBoxLayout(header_wrap)
        header_wrap_layout.setContentsMargins(8, 0, 8, 0)
        header_wrap_layout.setSpacing(0)
        header_wrap_layout.addWidget(header_row)
        group_box_spinner_layout.addWidget(header_wrap)
        self.core_page.setContentsMargins(8, 0, 8, 0)
        group_box_spinner_layout.addWidget(self.core_page)
        
        # Stretch to consume remaining vertical space
        group_box_spinner_layout.addStretch(1)
        self.form_container.setContentsMargins(6, 6, 6, 6)
        
        parent_layout.addWidget(self.form_container)
        
    def _create_constraints_section(self, parent_layout):
        """Create the Path Constraints section."""
        # Constraints title bar
        self.constraints_title_bar = QWidget()
        self.constraints_title_bar.setObjectName("constraintsTitleBar")
        self.constraints_title_bar.setStyleSheet("""
            QWidget#constraintsTitleBar {
                background-color: #2f2f2f;
                border: 1px solid #4a4a4a;
                border-radius: 6px;
            }
        """)
        constraints_title_layout = QHBoxLayout(self.constraints_title_bar)
        constraints_title_layout.setContentsMargins(8, 0, 8, 0)
        constraints_title_layout.setSpacing(8)
        
        constraints_label = QLabel("Path Constraints")
        constraints_label.setStyleSheet("""
            font-size: 14px;
            font-weight: bold;
            color: #eeeeee;
            background: transparent;
            border: none;
            padding: 6px 0;
        """)
        constraints_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        constraints_title_layout.addWidget(constraints_label)
        constraints_title_layout.addStretch()
        
        # Add constraint button
        self.optional_pop = PopupCombobox()
        self.optional_pop.setText("Add constraint")
        self.optional_pop.setToolTip("Add an optional constraint")
        self.optional_pop.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.optional_pop.button.setIconSize(QSize(16, 16))
        self.optional_pop.button.setMinimumHeight(22)
        self.optional_pop.item_selected.connect(self.on_constraint_added)
        
        constraints_title_layout.addWidget(self.optional_pop)
        parent_layout.addWidget(self.constraints_title_bar)

        # Constraints form container (wrapped in scroll area)
        self.constraints_scroll = QScrollArea()
        self.constraints_scroll.setWidgetResizable(True)
        self.constraints_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        try:
            # Keep content anchored to top-left and disallow horizontal panning
            self.constraints_scroll.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        except Exception:
            pass
        self.constraints_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.constraints_scroll.setFrameShape(QScrollArea.NoFrame)

        self.constraints_form_container = QGroupBox()
        self.constraints_form_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.constraints_form_container.setStyleSheet("""
            QGroupBox { background-color: #242424; border: 1px solid #3f3f3f; border-radius: 8px; margin-top: 0px; }
            QLabel { color: #f0f0f0; }
            /* Encompassing container for each ranged constraint type */
            QWidget[constraintGroupContainer='true'] { background: #242a2e; border: 1px solid #3b3b3b; border-radius: 8px; margin: 4px 0; }
            QWidget[constraintGroupContainer='true'][constraintGroup='rotation'] { background: #2a242a; }
            /* Unified rounded boxes for each individual constraint row */
            QWidget[constraintRow='true'] { background: #2a2a2a; border: 1px solid #3b3b3b; border-radius: 6px; margin: 4px 0; }
            QWidget[constraintRow='true'][constraintGroup='translation'] { background: #262f36; }
            QWidget[constraintRow='true'][constraintGroup='rotation'] { background: #30262f; }
            QLabel[constraintGroup] { background: transparent; }
        """)

        inner_widget = QWidget()
        inner_layout = QVBoxLayout(inner_widget)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(0)
        inner_layout.addWidget(self.constraints_form_container)
        self.constraints_scroll.setWidget(inner_widget)
        try:
            # Ensure containers can shrink with the viewport to avoid horizontal clipping
            inner_widget.setMinimumWidth(0)
            self.constraints_form_container.setMinimumWidth(0)
        except Exception:
            pass

        self.constraints_layout = QFormLayout(self.constraints_form_container)
        self.constraints_layout.setLabelAlignment(Qt.AlignRight)
        self.constraints_layout.setVerticalSpacing(4)
        self.constraints_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        # Let this section expand to consume available vertical space while still scrolling internally
        self.constraints_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        parent_layout.addWidget(self.constraints_scroll)

        # Balance vertical expansion dynamically
        form_idx = parent_layout.indexOf(self.form_container)
        constr_idx = parent_layout.indexOf(self.constraints_scroll)
        if form_idx != -1:
            parent_layout.setStretch(form_idx, 1)
        if constr_idx != -1:
            parent_layout.setStretch(constr_idx, 1)

        # Create property controls (includes both core and constraint spinners)
        self.spinners = self.property_editor.create_property_controls(self.core_layout, self.constraints_layout)
        
    def _connect_component_signals(self):
        """Connect signals from components to main sidebar signals."""
        # Element manager signals
        self.element_manager.elementAdded.connect(lambda idx, elem: self.modelStructureChanged.emit())
        self.element_manager.elementRemoved.connect(lambda idx, elem: self.modelStructureChanged.emit())
        self.element_manager.elementTypeChanged.connect(lambda idx, old, new: self.modelStructureChanged.emit())
        self.element_manager.elementsReordered.connect(lambda order: self.modelStructureChanged.emit())
        
        # Constraint manager signals
        self.constraint_manager.constraintAdded.connect(lambda key, val: (self.modelChanged.emit(), self.refresh_current_selection()))
        self.constraint_manager.constraintRemoved.connect(lambda key: (self.modelChanged.emit(), self.refresh_current_selection()))
        self.constraint_manager.constraintValueChanged.connect(lambda key, val: self.modelChanged.emit())
        self.constraint_manager.constraintRangeChanged.connect(lambda key, start, end: self.modelChanged.emit())
        
        # Forward preview signals
        self.constraint_manager.constraintRangePreviewRequested.connect(self.constraintRangePreviewRequested)
        self.constraint_manager.constraintRangePreviewCleared.connect(self.constraintRangePreviewCleared)
        
        # Property editor signals
        self.property_editor.propertyChanged.connect(self.on_attribute_change)
        self.property_editor.propertyRemoved.connect(self.on_attribute_removed)
        self.property_editor.propertyAdded.connect(lambda key: self.on_item_selected())
        
    def set_suspended(self, suspended: bool):
        """Set whether the sidebar is suspended (prevents updates)."""
        self._suspended = bool(suspended)
        
    def mark_ready(self):
        """Mark the sidebar as ready for interaction."""
        self._ready = True
        
    def get_selected_index(self) -> Optional[int]:
        """Get the currently selected element index."""
        row = self.points_list.currentRow()
        if row is None or row < 0:
            return None
        if self.path is None:
            return None
        if row >= len(self.path.path_elements):
            return None
        return row
        
    def select_index(self, index: int):
        """Select an element by index."""
        if index is None:
            return
        if index < 0 or index >= self.points_list.count():
            return
        # Selecting from the elements list should clear any active constraint preview
        try:
            self.constraint_manager.clear_active_preview()
        except Exception:
            pass
        # Defer selection to avoid re-entrancy during fullscreen/layout changes
        QTimer.singleShot(0, lambda i=index: self.points_list.setCurrentRow(i))

    def _check_and_swap_rotation_targets(self):
        """Compatibility shim: call ElementManager rotation ordering logic.

        Older code paths (e.g., main window drag-finish handler) expect the
        Sidebar to expose a private helper for reordering rotation targets
        after drags. The refactor moved that logic into
        ElementManager.check_and_swap_rotation_targets(). Provide this thin
        delegating wrapper so existing calls keep working.
        """
        try:
            if hasattr(self, 'element_manager') and self.element_manager is not None:
                self.element_manager.check_and_swap_rotation_targets()
        except Exception:
            pass
        
    def refresh_current_selection(self):
        """Re-run expose for current selection using current model values."""
        self.on_item_selected()
        
    def hide_spinners(self):
        """Hide all property controls."""
        self.property_editor.hide_all_properties()
        self.type_combo.setVisible(False)
        self.type_label.setVisible(False)
        self.form_container.setVisible(False)
        self.title_bar.setVisible(False)
        # Hide constraints section too
        self.constraints_title_bar.setVisible(False)
        self.constraints_form_container.setVisible(False)
        
    def update_current_values_only(self):
        """Update only the values of visible controls."""
        idx = self.get_selected_index()
        if idx is None or self.path is None:
            return
        element = self.path.get_element(idx)
        self.property_editor.update_values_only(element)
        
    def set_path(self, path: Path):
        """Set the path to edit."""
        self.path = path
        self.element_manager.set_path(path)
        self.constraint_manager.set_path(path)
        
        # Update project managers in components if available
        if hasattr(self, 'project_manager') and self.project_manager:
            self.element_manager.project_manager = self.project_manager
            self.constraint_manager.project_manager = self.project_manager
            self.property_editor.project_manager = self.project_manager
        
        # Rebuild UI
        self.rebuild_points_list()
        
        # Restore UI state if there are elements and one was previously selected
        if self.path and self.path.path_elements:
            # Try to restore the last selected index, or select the first element
            last_selected = getattr(self, '_last_selected_index', 0)
            if last_selected < len(self.path.path_elements):
                self.select_index(last_selected)
                # Force refresh the selection to restore optional spinners
                QTimer.singleShot(0, self.refresh_current_selection)
            else:
                self.select_index(0)
                QTimer.singleShot(0, self.refresh_current_selection)
        else:
            # Clear the UI if no path or no elements
            self.hide_spinners()
            
    def rebuild_points_list(self):
        """Rebuild the elements list widget."""
        self.hide_spinners()
        
        # Remove and delete any existing row widgets to prevent visual artifacts
        try:
            self.points_list.blockSignals(True)
            for i in range(self.points_list.count()):
                item = self.points_list.item(i)
                w = self.points_list.itemWidget(item)
                if w is not None:
                    self.points_list.removeItemWidget(item)
                    w.deleteLater()
            self.points_list.clear()
            
            # Rebuild add-element dropdown items based on selection context
            self._refresh_add_dropdown_items()
            
            if self.path:
                for i, p in enumerate(self.path.path_elements):
                    if isinstance(p, TranslationTarget):
                        name = ElementType.TRANSLATION.value
                    elif isinstance(p, RotationTarget):
                        name = ElementType.ROTATION.value
                    elif isinstance(p, Waypoint):
                        name = ElementType.WAYPOINT.value
                    else:
                        name = "Unknown"

                    # Use an empty QListWidgetItem and render all visuals via a row widget
                    item = QListWidgetItem("")
                    item.setData(Qt.UserRole, i)
                    
                    # Build row widget with label and remove button
                    row_widget = QWidget()
                    row_layout = QHBoxLayout(row_widget)
                    row_layout.setContentsMargins(6, 0, 6, 0)
                    row_layout.setSpacing(6)
                    label = QLabel(name)
                    label.setStyleSheet("color: #f0f0f0;")
                    row_layout.addWidget(label)
                    row_layout.addStretch()
                    
                    remove_btn = QPushButton()
                    remove_btn.setIcon(QIcon("assets/remove_icon.png"))
                    remove_btn.setToolTip("Remove element")
                    remove_btn.setFixedSize(18, 18)
                    remove_btn.setIconSize(QSize(14, 14))
                    remove_btn.setStyleSheet("QPushButton { border: none; } QPushButton:hover { background: #555; border-radius: 3px; }")
                    # Capture current index by default-arg
                    remove_btn.clicked.connect(lambda checked=False, idx_to_remove=i: self._on_remove_element(idx_to_remove))
                    row_layout.addWidget(remove_btn)

                    # Ensure the row height matches the widget
                    item.setSizeHint(row_widget.sizeHint())
                    self.points_list.addItem(item)
                    self.points_list.setItemWidget(item, row_widget)
        finally:
            self.points_list.blockSignals(False)
            
    def on_item_selected(self):
        """Handle selection of an element in the list."""
        try:
            # Guard against re-entrancy and layout instability
            if getattr(self, '_suspended', False) or not getattr(self, '_ready', False):
                return
            
            idx = self.get_selected_index()
            if idx is None or self.path is None:
                self.hide_spinners()
                return
                
            # Clear any active ranged preview when selecting a list element
            try:
                self.constraint_manager.clear_active_preview()
            except Exception:
                pass
            
            # Store the selected index for restoration when paths are reloaded
            self._last_selected_index = idx
            
            # Validate index bounds
            if idx < 0 or idx >= len(self.path.path_elements):
                self.hide_spinners()
                return
            
            # Safely get element
            try:
                element = self.path.get_element(idx)
            except (IndexError, RuntimeError):
                self.hide_spinners()
                return
            
            # Clear and hide existing UI
            self.optional_pop.clear()
            self.hide_spinners()
            
            # Expose element properties
            try:
                self._expose_element(element)
            except (RuntimeError, AttributeError):
                return
            
            # Determine element type safely
            try:
                if isinstance(element, TranslationTarget):
                    current_type = ElementType.TRANSLATION
                elif isinstance(element, RotationTarget):
                    current_type = ElementType.ROTATION
                else:
                    current_type = ElementType.WAYPOINT
            except RuntimeError:
                return
            
            # Rebuild type combo
            try:
                self._rebuild_type_combo_for_index(idx, current_type)
            except (RuntimeError, AttributeError):
                pass
            
            # Refresh add-element options
            try:
                self._refresh_add_dropdown_items()
            except (RuntimeError, AttributeError):
                pass
            
            # Show controls
            try:
                for widget in (self.type_label, self.type_combo, self.form_container, self.title_bar, self.constraints_title_bar, self.constraints_form_container):
                    if widget is not None:
                        widget.setVisible(True)
            except (RuntimeError, AttributeError):
                pass
                
        except Exception as e:
            # Fail safe: keep UI alive
            print(f"Sidebar selection error: {e}")
            self.hide_spinners()
            
    def _expose_element(self, element):
        """Expose properties for the selected element."""
        if element is None:
            return
            
        # Clear constraint range sliders
        self.constraint_manager.clear_range_sliders()
        
        # Get optional properties from property editor
        optional_display_items = self.property_editor.expose_element_properties(element)
        
        # Show path constraints and collect their optional items
        constraint_optional_items = self._expose_path_constraints()
        
        # Combine all optional items
        all_optional_items = optional_display_items + constraint_optional_items
        
        # Update optional dropdown with all items
        if all_optional_items:
            all_optional_items = sorted(list(dict.fromkeys(all_optional_items)))
            self.optional_pop.clear()
            self.optional_pop.add_items(all_optional_items)
        else:
            self.optional_pop.clear()
            
    def _expose_path_constraints(self):
        """Show path-level constraints."""
        optional_display_items = []
        has_constraints = False
        
        if self.path is not None:
            # Ensure constraints object exists
            if not hasattr(self.path, 'constraints') or self.path.constraints is None:
                from models.path_model import Constraints
                self.path.constraints = Constraints()
                
            # Helper: sanitize labels for menu display (strip HTML line breaks)
            def _menu_label_for_key(key: str) -> str:
                meta = SPINNER_METADATA.get(key, {})
                return meta.get('label', key).replace('<br/>', ' ')
                
            for key in PATH_CONSTRAINT_KEYS:
                # Check if constraint is present
                has_constraint = self.constraint_manager.has_constraint(key)
                constraint_value = self.constraint_manager.get_constraint_value(key)
                
                if has_constraint and key in self.spinners:
                    control, label, btn, spin_row = self.spinners[key]
                    
                    # Set value
                    try:
                        control.blockSignals(True)
                        value = constraint_value if constraint_value is not None else 0.0
                        control.setValue(float(value))
                    finally:
                        control.blockSignals(False)
                        
                    # Show controls
                    label.setVisible(True)
                    spin_row.setVisible(True)
                    has_constraints = True
                    
                    # Create range slider for applicable constraints
                    if key in ('max_velocity_meters_per_sec', 'max_acceleration_meters_per_sec2', 
                              'max_velocity_deg_per_sec', 'max_acceleration_deg_per_sec2'):
                        self.constraint_manager.create_range_slider_for_key(
                            key, control, spin_row, label, self.constraints_layout
                        )
                else:
                    display = _menu_label_for_key(key)
                    optional_display_items.append(display)
                    self.property_editor.optional_display_to_key[display] = key

                # For ranged-capable constraints, always provide an option to add another instance
                if key in ('max_velocity_meters_per_sec', 'max_acceleration_meters_per_sec2',
                           'max_velocity_deg_per_sec', 'max_acceleration_deg_per_sec2'):
                    add_more_label = _menu_label_for_key(key) + ' (+)'
                    # Avoid duplicate entry if already added in this pass
                    if add_more_label not in optional_display_items:
                        optional_display_items.append(add_more_label)
                        self.property_editor.optional_display_to_key[add_more_label] = key
                    
        # Return optional items list
        return optional_display_items
            
    def _rebuild_type_combo_for_index(self, idx: int, current_type: ElementType):
        """Rebuild type combo based on allowed types for the element position."""
        if self.path is None:
            return
        is_end = (idx == 0 or idx == len(self.path.path_elements) - 1)
        allowed = [e.value for e in ElementType]
        if is_end and current_type != ElementType.ROTATION:
            allowed = [ElementType.TRANSLATION.value, ElementType.WAYPOINT.value]
        try:
            self.type_combo.blockSignals(True)
            self.type_combo.clear()
            self.type_combo.addItems(allowed)
            self.type_combo.setCurrentText(current_type.value)
        finally:
            self.type_combo.blockSignals(False)
            
    def _refresh_add_dropdown_items(self):
        """Refresh the add element dropdown based on current path state."""
        # Allow adding rotation only if there are at least two translation or waypoint elements
        if self.path is None:
            self.add_element_pop.clear()
            return
        non_rot = sum(1 for e in self.path.path_elements if not isinstance(e, RotationTarget))
        items = [ElementType.TRANSLATION.value, ElementType.WAYPOINT.value]
        if non_rot >= 2:
            items.append(ElementType.ROTATION.value)
        self.add_element_pop.add_items(items)
        
    def _insert_position_from_selection(self) -> int:
        """Get insert position based on current selection."""
        # Insert AFTER the selected row; if nothing selected, append at end
        current_row = self.points_list.currentRow()
        if current_row < 0:
            return len(self.path.path_elements) if self.path else 0
        return current_row + 1
        
    def on_add_element_selected(self, type_text: str):
        """Handle adding a new element."""
        if self.path is None:
            return
            
        new_type = ElementType(type_text)
        insert_pos = self._insert_position_from_selection()
        current_idx = self.get_selected_index()
        
        # Announce about-to-change for undo snapshot
        try:
            self.aboutToChange.emit(f"Add {new_type.value}")
        except Exception:
            pass
            
        # Add element via manager
        new_index = self.element_manager.add_element(new_type, insert_pos, current_idx)
        
        # Rebuild UI and select new element
        self.rebuild_points_list()
        self.select_index(new_index)
        
        try:
            self.userActionOccurred.emit(f"Add {new_type.value}")
        except Exception:
            pass
            
    def _on_remove_element(self, idx_to_remove: int):
        """Handle removing an element."""
        if self.path is None:
            return
        if idx_to_remove < 0 or idx_to_remove >= len(self.path.path_elements):
            return
            
        # Get element for description
        el = self.path.path_elements[idx_to_remove]
        tname = 'Waypoint' if isinstance(el, Waypoint) else 'Rotation' if isinstance(el, RotationTarget) else 'Translation'
        
        # Announce about-to-change for undo snapshot
        try:
            self.aboutToChange.emit(f"Delete {tname}")
        except Exception:
            pass
            
        # Remove via manager
        self.element_manager.remove_element(idx_to_remove)
        
        # Rebuild list and update selection
        self.rebuild_points_list()
        if self.path.path_elements:
            new_sel = min(idx_to_remove, len(self.path.path_elements) - 1)
            self.select_index(new_sel)
            
        try:
            self.userActionOccurred.emit(f"Delete {tname}")
        except Exception:
            pass
            
    def on_type_change(self, value):
        """Handle element type change."""
        idx = self.get_selected_index()
        if idx is None or self.path is None:
            return
            
        new_type = ElementType(value)
        
        # Announce about-to-change
        try:
            self.aboutToChange.emit(f"Change element type to {new_type.value}")
        except Exception:
            pass
            
        # Change type via manager
        if self.element_manager.change_element_type(idx, new_type):
            self.rebuild_points_list()
            self.select_index(idx)
            
            try:
                self.userActionOccurred.emit(f"Change element type to {new_type.value}")
            except Exception:
                pass
                
    def on_points_list_reordered(self):
        """Handle reordering of elements in the list."""
        if self.path is None:
            return
            
        try:
            self.aboutToChange.emit("Reorder elements")
        except Exception:
            pass
            
        # New order by original indices from UI items
        new_order = []
        for i in range(self.points_list.count()):
            item = self.points_list.item(i)
            idx = item.data(Qt.UserRole)
            if isinstance(idx, int):
                new_order.append(idx)
                
        # Apply reorder via manager
        self.element_manager.reorder_elements(new_order)
        
        # Rebuild UI
        self.rebuild_points_list()
        
        try:
            self.userActionOccurred.emit("Reorder elements")
        except Exception:
            pass
            
    def on_attribute_change(self, key, value):
        """Handle property value changes."""
        idx = self.get_selected_index()
        if idx is not None and self.path is not None:
            element = self.path.get_element(idx)
            
            # Build description
            label_text = SPINNER_METADATA.get(key, {}).get('label', key).replace('<br/>', ' ')
            
            # Determine if it's a path constraint
            if key in PATH_CONSTRAINT_KEYS:
                desc = f"Edit Path Constraint: {label_text}"
                try:
                    self.aboutToChange.emit(desc)
                except Exception:
                    pass
                    
                # Update via constraint manager
                self.constraint_manager.update_constraint_value(key, float(value))
            else:
                # Element property
                entity = self._get_entity_name(element)
                desc = f"Edit {entity} {label_text}"
                
                try:
                    self.aboutToChange.emit(desc)
                except Exception:
                    pass
                    
                # Update via property editor
                self.property_editor.set_property_value(key, value, element)
                
            self.modelChanged.emit()
            
            try:
                self.userActionOccurred.emit(desc)
            except Exception:
                pass
                
    def on_attribute_removed(self, key):
        """Handle property removal."""
        idx = self.get_selected_index()
        if idx is None or self.path is None:
            return
            
        element = self.path.get_element(idx)
        label_text = SPINNER_METADATA.get(key, {}).get('label', key).replace('<br/>', ' ')
        desc = f"Remove {label_text}"
        
        try:
            self.aboutToChange.emit(desc)
        except Exception:
            pass
            
        # Check if it's a path constraint
        if key in PATH_CONSTRAINT_KEYS:
            self.constraint_manager.remove_constraint(key)
        else:
            # Set property to None
            self.property_editor.set_property_value(key, None, element)
            
        self.on_item_selected()
        self.modelChanged.emit()
        
        try:
            self.userActionOccurred.emit(desc)
        except Exception:
            pass
            
    def on_constraint_added(self, key):
        """Handle adding a path constraint."""
        if self.path is None:
            return
            
        # Translate display name back to actual key if needed
        real_key = self.property_editor.optional_display_to_key.get(key, key)
        # If user selected a "+" variant manually entered, strip it
        if real_key.endswith(' (+)') and real_key not in self.property_editor.optional_display_to_key:
            real_key = real_key.replace(' (+)', '')
        
        label_text = SPINNER_METADATA.get(real_key, {}).get('label', real_key).replace('<br/>', ' ')
        
        try:
            self.aboutToChange.emit(f"Add {label_text}")
        except Exception:
            pass
        
        # Add constraint via manager
        self.constraint_manager.add_constraint(real_key)
        
        # Refresh UI
        self.refresh_current_selection()
        self.modelChanged.emit()
        
        try:
            self.userActionOccurred.emit(f"Add {label_text}")
        except Exception:
            pass
            
    def _get_entity_name(self, element) -> str:
        """Get a descriptive name for an element type."""
        if isinstance(element, Waypoint):
            return 'Waypoint'
        if isinstance(element, RotationTarget):
            return 'Rotation'
        if isinstance(element, TranslationTarget):
            return 'Translation'
        return 'Element'
        
    def _delete_via_shortcut(self):
        """Handle delete keyboard shortcut."""
        # Emit a deletion request so the owner can handle model + undo coherently
        try:
            self.deleteSelectedRequested.emit()
        except Exception:
            pass
            
    def eventFilter(self, obj, event):
        """Handle events for constraint preview management."""
        try:
            et = event.type()
            
            # Handle clicks to manage constraint preview
            if et == QEvent.MouseButtonPress:
                # If click is on the sidebar itself, determine the child under the cursor
                target_widget = obj
                try:
                    if obj is self:
                        ev = event
                        pos = getattr(ev, 'position', None)
                        if pos is not None:
                            pt = pos().toPoint() if callable(pos) else pos.toPoint()
                        else:
                            pt = getattr(ev, 'pos', lambda: None)()
                        if pt is not None:
                            child = self.childAt(pt)
                            if child is not None:
                                target_widget = child
                except Exception:
                    target_widget = obj

                # Check if clicking on any range-related control
                if self.constraint_manager.is_widget_range_related(target_widget):
                    return False
                
                # Clicked somewhere else → clear overlay
                self.constraint_manager.clear_active_preview()
                return False
                        
        except Exception:
            pass
        return super().eventFilter(obj, event)
        
    # ---- Public helpers for external widgets to control constraint preview ----
    def clear_active_preview(self):
        """Clear active constraint preview."""
        self.constraint_manager.clear_active_preview()
        
    def is_widget_range_related(self, widget: QWidget) -> bool:
        """Check if widget is range-related."""
        return self.constraint_manager.is_widget_range_related(widget)
