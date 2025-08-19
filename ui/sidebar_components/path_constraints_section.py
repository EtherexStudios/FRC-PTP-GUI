"""Path Constraints section of the sidebar."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QFormLayout,
    QDoubleSpinBox, QCheckBox, QPushButton, QSizePolicy
)
from PySide6.QtCore import Signal, Qt, QSize, QTimer, QEvent
from PySide6.QtGui import QIcon
from typing import Dict, Tuple, Optional, List
from .custom_widgets import PopupCombobox, RangeSlider
from models.path_model import Path, RangedConstraint


class PathConstraintsSection(QWidget):
    """Widget for managing path-level constraints."""
    
    # Signals
    modelChanged = Signal()
    aboutToChange = Signal(str)  # description
    userActionOccurred = Signal(str)  # description after change
    constraintAdded = Signal(str)  # key
    constraintRemoved = Signal(str)  # key
    constraintChanged = Signal(str, object)  # key, value
    constraintRangePreviewRequested = Signal(str, int, int)  # key, start, end
    constraintRangePreviewCleared = Signal()
    
    def __init__(self):
        super().__init__()
        self._path: Optional[Path] = None
        self._project_manager = None
        self.spinners: Dict[str, Tuple[QWidget, QLabel, QPushButton, QWidget]] = {}
        self._constraint_field_containers: Dict[str, QWidget] = {}
        self._range_sliders: Dict[str, RangeSlider] = {}
        self._range_slider_rows: Dict[str, QWidget] = {}
        self._active_preview_key: Optional[str] = None
        
        self._init_ui()
        self._setup_constraint_metadata()
        
    def _init_ui(self):
        """Initialize the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Title bar
        self.title_bar = self._create_title_bar()
        layout.addWidget(self.title_bar)
        
        # Constraints container
        self.form_container = self._create_form_container()
        layout.addWidget(self.form_container)
        
    def _create_title_bar(self) -> QWidget:
        """Create the title bar with add button."""
        title_bar = QWidget()
        title_bar.setObjectName("constraintsTitleBar")
        title_bar.setStyleSheet("""
            QWidget#constraintsTitleBar {
                background-color: #2f2f2f;
                border: 1px solid #4a4a4a;
                border-radius: 6px;
            }
        """)
        
        layout = QHBoxLayout(title_bar)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(8)
        
        label = QLabel("Path Constraints")
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
        
        # Add constraint button
        self.optional_pop = PopupCombobox()
        self.optional_pop.setText("Add constraint")
        self.optional_pop.setToolTip("Add an optional constraint")
        self.optional_pop.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.optional_pop.button.setIconSize(QSize(16, 16))
        self.optional_pop.button.setMinimumHeight(22)
        self.optional_pop.item_selected.connect(self._on_constraint_added)
        layout.addWidget(self.optional_pop)
        
        return title_bar
        
    def _create_form_container(self) -> QWidget:
        """Create the constraints form container."""
        container = QGroupBox()
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        container.setStyleSheet("""
            QGroupBox { 
                background-color: #242424; 
                border: 1px solid #3f3f3f; 
                border-radius: 6px; 
            }
            QLabel { color: #f0f0f0; }
        """)
        
        self.constraints_layout = QFormLayout(container)
        self.constraints_layout.setLabelAlignment(Qt.AlignRight)
        self.constraints_layout.setVerticalSpacing(8)
        self.constraints_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        
        return container
        
    def _setup_constraint_metadata(self):
        """Set up constraint metadata and create spinners."""
        self.constraint_metadata = {
            'final_velocity_meters_per_sec': {
                'label': 'Final Velocity (m/s)', 'step': 0.1, 'range': (0, 99999), 
                'removable': True, 'section': 'constraints'
            },
            'max_velocity_meters_per_sec': {
                'label': 'Max Velocity (m/s)', 'step': 0.1, 'range': (0, 99999), 
                'removable': True, 'section': 'constraints'
            },
            'max_acceleration_meters_per_sec2': {
                'label': 'Max Acceleration (m/s²)', 'step': 0.1, 'range': (0, 99999), 
                'removable': True, 'section': 'constraints'
            },
            'max_velocity_deg_per_sec': {
                'label': 'Max Rot Velocity<br/>(deg/s)', 'step': 1.0, 'range': (0, 99999), 
                'removable': True, 'section': 'constraints'
            },
            'max_acceleration_deg_per_sec2': {
                'label': 'Max Rot Acceleration<br/>(deg/s²)', 'step': 1.0, 'range': (0, 99999), 
                'removable': True, 'section': 'constraints'
            }
        }
        
        # Create spinners
        self._create_constraint_spinners()
        
    def _create_constraint_spinners(self):
        """Create spinner controls for constraints."""
        for name, data in self.constraint_metadata.items():
            # Create spinner
            control = QDoubleSpinBox()
            control.setSingleStep(data['step'])
            control.setRange(*data['range'])
            control.setValue(0)
            control.setDecimals(3)
            control.setKeyboardTracking(False)
            control.setMinimumWidth(96)
            control.setMaximumWidth(200)
            control.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            control.valueChanged.connect(lambda v, n=name: self._on_constraint_change(n, v))
            
            # Create label
            label = QLabel(data['label'])
            if '<br/>' in data['label']:
                label.setWordWrap(False)
                label.setTextFormat(Qt.RichText)
            else:
                label.setWordWrap(True)
            label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            label.setToolTip(data['label'].replace('<br/>', ' '))
            label.setMinimumWidth(120)
            
            # Create row with remove button
            spin_row = QWidget()
            spin_row_layout = QHBoxLayout(spin_row)
            spin_row_layout.setContentsMargins(0, 0, 0, 0)
            spin_row_layout.setSpacing(5)
            spin_row.setMinimumHeight(24)
            spin_row.setMaximumHeight(24)
            
            btn = QPushButton()
            btn.setIconSize(QSize(14, 14))
            btn.setFixedSize(16, 16)
            btn.setStyleSheet("QPushButton { border: none; } QPushButton:hover { background: #555; border-radius: 3px; }")
            btn.setIcon(QIcon("assets/remove_icon.png"))
            btn.clicked.connect(lambda checked=False, n=name: self._on_constraint_removed(n))
            
            spin_row_layout.addStretch()
            spin_row_layout.addWidget(control)
            spin_row_layout.addWidget(btn)
            spin_row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            
            # Create field container for potential range slider
            field_container = QWidget()
            vbl = QVBoxLayout(field_container)
            vbl.setContentsMargins(0, 0, 0, 0)
            vbl.setSpacing(3)
            vbl.addWidget(spin_row)
            
            # Install event filter for preview
            try:
                label.setFocusPolicy(Qt.StrongFocus)
                label.installEventFilter(self)
            except Exception:
                pass
                
            self.constraints_layout.addRow(label, field_container)
            self._constraint_field_containers[name] = field_container
            self.spinners[name] = (control, label, btn, spin_row)
            
        # Hide all initially
        self.hide_all_constraints()
        
    def set_path(self, path: Path):
        """Set the path model."""
        self._path = path
        self.update_constraints()
        
    def set_project_manager(self, project_manager):
        """Set project manager for defaults."""
        self._project_manager = project_manager
        
    def hide_all_constraints(self):
        """Hide all constraint controls."""
        for name, (control, label, btn, spin_row) in self.spinners.items():
            label.setVisible(False)
            spin_row.parentWidget().setVisible(False)  # Hide field container
            
    def update_constraints(self):
        """Update constraint display from path model."""
        if self._path is None:
            self.hide_all_constraints()
            self._update_optional_items([])
            return
            
        # Build available constraint list
        available_constraints = []
        shown_constraints = []
        
        if hasattr(self._path, 'constraints') and self._path.constraints is not None:
            c = self._path.constraints
            
            # Check each constraint
            for name in self.constraint_metadata.keys():
                if hasattr(c, name):
                    val = getattr(c, name)
                    # Check for ranged constraints
                    has_range = any(
                        getattr(rc, 'key', None) == name 
                        for rc in (getattr(self._path, 'ranged_constraints', []) or [])
                    )
                    
                    if val is not None or has_range:
                        # Show this constraint
                        self._show_constraint(name, val, has_range)
                        shown_constraints.append(name)
                    else:
                        available_constraints.append(name)
                else:
                    available_constraints.append(name)
        else:
            available_constraints = list(self.constraint_metadata.keys())
            
        # Update add menu
        self._update_optional_items(available_constraints)
        
        # Clear any range sliders for hidden constraints
        for name in list(self._range_sliders.keys()):
            if name not in shown_constraints:
                self._remove_range_slider(name)
                
    def _show_constraint(self, name: str, value: Optional[float], has_range: bool):
        """Show a constraint spinner."""
        if name not in self.spinners:
            return
            
        control, label, btn, field_container = self.spinners[name]
        
        # Get value from ranged constraint if present
        range_val = None
        if has_range:
            try:
                for rc in (getattr(self._path, 'ranged_constraints', []) or []):
                    if getattr(rc, 'key', None) == name:
                        range_val = float(getattr(rc, 'value', None))
                        break
            except Exception:
                range_val = None
                
        # Set spinner value
        control.blockSignals(True)
        shown_value = float(value) if value is not None else (float(range_val) if range_val is not None else 0.0)
        control.setValue(shown_value)
        control.blockSignals(False)
        
        # Show controls
        label.setVisible(True)
        field_container.parentWidget().setVisible(True)
        
        # Add range slider for velocity/acceleration constraints
        if name in ('max_velocity_meters_per_sec', 'max_acceleration_meters_per_sec2',
                   'max_velocity_deg_per_sec', 'max_acceleration_deg_per_sec2'):
            self._ensure_range_slider_for_key(name, control, field_container.children()[1], label)
            
    def _update_optional_items(self, available_keys: List[str]):
        """Update the add constraint menu."""
        self.optional_pop.clear()
        
        if not available_keys:
            return
            
        # Convert keys to display names
        items = []
        self.optional_display_to_key = {}
        
        for key in sorted(available_keys):
            if key in self.constraint_metadata:
                display = self.constraint_metadata[key]['label'].replace('<br/>', ' ')
                items.append(display)
                self.optional_display_to_key[display] = key
                
        self.optional_pop.add_items(items)
        
    def _ensure_range_slider_for_key(self, name: str, control: QDoubleSpinBox, spin_row: QWidget, label_widget: QLabel):
        """Add or update a range slider for a constraint."""
        # Implementation would be similar to the original but simplified
        # For now, skip the complex range slider logic
        pass
        
    def _remove_range_slider(self, name: str):
        """Remove range slider for a constraint."""
        if name in self._range_sliders:
            slider = self._range_sliders[name]
            try:
                parent = slider.parentWidget()
                if parent is not None:
                    parent.layout().removeWidget(slider)
                slider.deleteLater()
            except Exception:
                pass
            del self._range_sliders[name]
            
        if name in self._range_slider_rows:
            del self._range_slider_rows[name]
            
    def _on_constraint_added(self, display_name: str):
        """Handle adding a constraint."""
        # Get actual key from display name
        key = self.optional_display_to_key.get(display_name, display_name)
        self.constraintAdded.emit(key)
        
    def _on_constraint_removed(self, key: str):
        """Handle removing a constraint."""
        self.constraintRemoved.emit(key)
        
    def _on_constraint_change(self, key: str, value: float):
        """Handle constraint value change."""
        self.constraintChanged.emit(key, value)
        
    def clear_active_preview(self):
        """Clear any active constraint preview."""
        try:
            self._active_preview_key = None
            self.constraintRangePreviewCleared.emit()
        except Exception:
            pass
            
    def is_widget_range_related(self, widget: QWidget) -> bool:
        """Check if a widget is part of the constraint UI."""
        try:
            if widget is None:
                return False
                
            # Check sliders
            for slider in self._range_sliders.values():
                if slider is widget or (hasattr(slider, 'isAncestorOf') and slider.isAncestorOf(widget)):
                    return True
                    
            # Check slider containers
            for row in self._range_slider_rows.values():
                if row is widget or (hasattr(row, 'isAncestorOf') and row.isAncestorOf(widget)):
                    return True
                    
            # Check spinners and labels
            for key in self._range_sliders.keys():
                if key in self.spinners:
                    control, label, _, _ = self.spinners[key]
                    for w in (control, label):
                        if w is widget or (hasattr(w, 'isAncestorOf') and w.isAncestorOf(widget)):
                            return True
                            
        except Exception:
            return False
            
        return False
        
    def eventFilter(self, obj, event):
        """Handle events for constraint preview."""
        # Simplified event filter - full implementation would handle preview
        return super().eventFilter(obj, event)