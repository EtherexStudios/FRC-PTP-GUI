"""Element Properties section of the sidebar."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QFormLayout,
    QComboBox, QDoubleSpinBox, QCheckBox, QPushButton, QSizePolicy
)
from PySide6.QtCore import Signal, Qt, QSize
from PySide6.QtGui import QIcon
from typing import Dict, Tuple, Optional, Any
import math
from enum import Enum
from models.path_model import TranslationTarget, RotationTarget, Waypoint


class ElementType(Enum):
    TRANSLATION = 'translation'
    ROTATION = 'rotation'  
    WAYPOINT = 'waypoint'


class ElementPropertiesSection(QWidget):
    """Widget for displaying and editing element properties."""
    
    # Signals
    modelChanged = Signal()
    aboutToChange = Signal(str)  # description of change
    userActionOccurred = Signal(str)  # description after change
    attributeRemoved = Signal(str)  # key
    typeChanged = Signal(str)  # new type value
    attributeChanged = Signal(str, object)  # key, value
    
    def __init__(self):
        super().__init__()
        self._element = None
        self._element_index = None
        self._project_manager = None
        self.spinners: Dict[str, Tuple[QWidget, QLabel, QPushButton, QWidget]] = {}
        
        self._init_ui()
        self._setup_spinner_metadata()
        
    def _init_ui(self):
        """Initialize the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Title bar
        self.title_bar = self._create_title_bar()
        layout.addWidget(self.title_bar)
        
        # Properties container
        self.form_container = self._create_form_container()
        layout.addWidget(self.form_container)
        
    def _create_title_bar(self) -> QWidget:
        """Create the title bar."""
        title_bar = QWidget()
        title_bar.setObjectName("titleBar")
        title_bar.setStyleSheet("""
            QWidget#titleBar {
                background-color: #2f2f2f;
                border: 1px solid #4a4a4a;
                border-radius: 6px;
            }
        """)
        
        layout = QHBoxLayout(title_bar)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(0)
        
        label = QLabel("Element Properties")
        label.setStyleSheet("""
            font-size: 14px; 
            font-weight: bold;
            color: #eeeeee;
            background: transparent;
            border: none;
            padding: 6px 0;
        """)
        layout.addWidget(label)
        layout.addStretch()
        
        return title_bar
        
    def _create_form_container(self) -> QWidget:
        """Create the properties form container."""
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
        
        # Main layout
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)
        
        # Type selector row
        header_row = QWidget()
        header_layout = QHBoxLayout(header_row)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)
        
        self.type_label = QLabel("Type:")
        header_layout.addWidget(self.type_label)
        
        # Type combo container
        self.optional_container = QWidget()
        optional_layout = QHBoxLayout(self.optional_container)
        optional_layout.setContentsMargins(0, 0, 0, 0)
        
        self.type_combo = QComboBox()
        self.type_combo.addItems([e.value for e in ElementType])
        self.type_combo.currentTextChanged.connect(self._on_type_change)
        optional_layout.addWidget(self.type_combo)
        
        header_layout.addWidget(self.optional_container, 1)
        layout.addWidget(header_row)
        
        # Core properties page
        self.core_page = QWidget()
        self.core_page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.core_layout = QFormLayout(self.core_page)
        self.core_layout.setLabelAlignment(Qt.AlignRight)
        self.core_layout.setVerticalSpacing(8)
        self.core_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        layout.addWidget(self.core_page)
        
        layout.addStretch(1)
        
        return container
        
    def _setup_spinner_metadata(self):
        """Set up the spinner metadata and create controls."""
        # Define metadata for all spinners
        self.spinner_metadata = {
            'rotation_degrees': {
                'label': 'Rotation (deg)', 'step': 1.0, 'range': (-180.0, 180.0), 
                'removable': False, 'section': 'core'
            },
            'x_meters': {
                'label': 'X (m)', 'step': 0.05, 'range': (0.0, 16.54), 
                'removable': False, 'section': 'core'
            },
            'y_meters': {
                'label': 'Y (m)', 'step': 0.05, 'range': (0.0, 8.21), 
                'removable': False, 'section': 'core'
            },
            'intermediate_handoff_radius_meters': {
                'label': 'Handoff Radius (m)', 'step': 0.05, 'range': (0, 99999), 
                'removable': False, 'section': 'core'
            },
            'rotation_position_ratio': {
                'label': 'Rotation Pos (0–1)', 'step': 0.01, 'range': (0.0, 1.0), 
                'removable': False, 'section': 'core'
            },
            'profiled_rotation': {
                'label': 'Profiled Rotation', 'type': 'checkbox', 
                'removable': False, 'section': 'core'
            },
        }
        
        # Map for degrees to radians conversion
        self.degrees_to_radians_attr_map = {
            'rotation_degrees': 'rotation_radians'
        }
        
        # Create spinners
        self._create_spinners()
        
    def _create_spinners(self):
        """Create all spinner controls."""
        for name, data in self.spinner_metadata.items():
            control_type = data.get('type', 'spinner')
            
            # Create control
            if control_type == 'checkbox':
                control = QCheckBox()
                control.setChecked(True if name == 'profiled_rotation' else False)
                control.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                control.toggled.connect(lambda v, n=name: self._on_attribute_change(n, v))
            else:
                control = QDoubleSpinBox()
                control.setSingleStep(data['step'])
                control.setRange(*data['range'])
                control.setValue(0)
                control.setDecimals(3)
                control.setKeyboardTracking(False)
                control.setMinimumWidth(96)
                control.setMaximumWidth(200)
                control.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                control.valueChanged.connect(lambda v, n=name: self._on_attribute_change(n, v))
            
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
            
            # Create row container with button
            spin_row = QWidget()
            spin_row_layout = QHBoxLayout(spin_row)
            spin_row_layout.setContentsMargins(0, 0, 0, 0)
            spin_row_layout.setSpacing(5)
            spin_row.setMinimumHeight(24)
            spin_row.setMaximumHeight(24)
            
            # Remove button
            btn = QPushButton()
            btn.setIconSize(QSize(14, 14))
            btn.setFixedSize(16, 16)
            btn.setStyleSheet("QPushButton { border: none; } QPushButton:hover { background: #555; border-radius: 3px; }")
            
            if data.get('removable', True):
                btn.setIcon(QIcon("assets/remove_icon.png"))
                btn.clicked.connect(lambda checked=False, n=name: self._on_attribute_removed(n))
            else:
                btn.setIcon(QIcon())
                btn.setEnabled(False)
            
            spin_row_layout.addStretch()
            spin_row_layout.addWidget(control)
            spin_row_layout.addWidget(btn)
            spin_row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            
            # Add to layout
            if data.get('section') == 'core':
                self.core_layout.addRow(label, spin_row)
            
            self.spinners[name] = (control, label, btn, spin_row)
            
        # Hide all spinners initially
        self.hide_all_spinners()
        
    def set_project_manager(self, project_manager):
        """Set the project manager for accessing defaults."""
        self._project_manager = project_manager
        
    def set_element(self, element, index: int):
        """Set the element to display."""
        self._element = element
        self._element_index = index
        self._update_display()
        
    def hide_all_spinners(self):
        """Hide all spinner controls."""
        for name, (spin, label, btn, spin_row) in self.spinners.items():
            label.setVisible(False)
            spin_row.setVisible(False)
        self.type_combo.setVisible(False)
        self.type_label.setVisible(False)
        self.form_container.setVisible(False)
        self.title_bar.setVisible(False)
        
    def _update_display(self):
        """Update the display for the current element."""
        if self._element is None:
            self.hide_all_spinners()
            return
            
        # Show containers
        self.form_container.setVisible(True)
        self.title_bar.setVisible(True)
        self.type_combo.setVisible(True)
        self.type_label.setVisible(True)
        
        # Update type combo
        if isinstance(self._element, TranslationTarget):
            current_type = ElementType.TRANSLATION
        elif isinstance(self._element, RotationTarget):
            current_type = ElementType.ROTATION
        else:
            current_type = ElementType.WAYPOINT
            
        self.type_combo.blockSignals(True)
        self.type_combo.setCurrentText(current_type.value)
        self.type_combo.blockSignals(False)
        
        # Show relevant spinners
        self._expose_element(self._element)
        
    def _expose_element(self, element):
        """Show spinners for the given element."""
        # Hide all first
        for name, (control, label, btn, spin_row) in self.spinners.items():
            label.setVisible(False)
            spin_row.setVisible(False)
            
        if isinstance(element, Waypoint):
            # Position from translation_target
            self._show_attr(element.translation_target, 'x_meters')
            self._show_attr(element.translation_target, 'y_meters')
            # Rotation from rotation_target
            self._show_deg_attr(element.rotation_target, 'rotation_degrees')
            # Profiled rotation
            self._show_attr(element.rotation_target, 'profiled_rotation')
            # Handoff radius
            self._show_handoff_radius(element.translation_target)
            
        elif isinstance(element, TranslationTarget):
            self._show_attr(element, 'x_meters')
            self._show_attr(element, 'y_meters')
            self._show_handoff_radius(element)
            
        elif isinstance(element, RotationTarget):
            self._show_deg_attr(element, 'rotation_degrees')
            self._show_attr(element, 'profiled_rotation')
            # Rotation position ratio
            if 'rotation_position_ratio' in self.spinners:
                control, label, btn, spin_row = self.spinners['rotation_position_ratio']
                control.blockSignals(True)
                control.setValue(float(getattr(element, 't_ratio', 0.0)))
                control.blockSignals(False)
                label.setVisible(True)
                spin_row.setVisible(True)
                
    def _show_attr(self, attr_owner, name: str):
        """Show an attribute spinner."""
        if name not in self.spinners:
            return
        control, label, btn, spin_row = self.spinners[name]
        
        if hasattr(attr_owner, name):
            value = getattr(attr_owner, name)
            if value is not None:
                control.blockSignals(True)
                if isinstance(control, QCheckBox):
                    control.setChecked(bool(value))
                else:
                    control.setValue(float(value))
                control.blockSignals(False)
                label.setVisible(True)
                spin_row.setVisible(True)
                
    def _show_deg_attr(self, owner, deg_name: str):
        """Show a degrees-based attribute."""
        if deg_name not in self.spinners:
            return
        model_attr = self.degrees_to_radians_attr_map.get(deg_name)
        if not model_attr:
            return
            
        control, label, btn, spin_row = self.spinners[deg_name]
        if hasattr(owner, model_attr):
            value = getattr(owner, model_attr)
            if value is not None:
                control.blockSignals(True)
                control.setValue(math.degrees(value))
                control.blockSignals(False)
                label.setVisible(True)
                spin_row.setVisible(True)
            elif deg_name == 'rotation_degrees':
                # Default to 0 for rotation
                control.blockSignals(True)
                control.setValue(0.0)
                control.blockSignals(False)
                label.setVisible(True)
                spin_row.setVisible(True)
                
    def _show_handoff_radius(self, element):
        """Show handoff radius spinner with default from config."""
        if 'intermediate_handoff_radius_meters' not in self.spinners:
            return
            
        control, label, btn, spin_row = self.spinners['intermediate_handoff_radius_meters']
        val = getattr(element, 'intermediate_handoff_radius_meters', None)
        
        # Use default from config if None
        if val is None:
            try:
                if self._project_manager:
                    val = self._project_manager.get_default_optional_value('intermediate_handoff_radius_meters')
                val = val if val is not None else 0.0
            except Exception:
                val = 0.0
                
        control.blockSignals(True)
        control.setValue(float(val))
        control.blockSignals(False)
        label.setVisible(True)
        spin_row.setVisible(True)
        
    def update_values_only(self):
        """Update spinner values without changing visibility."""
        if self._element is None:
            return
            
        # Helper to update control value
        def set_control_value(name: str, value):
            if name not in self.spinners:
                return
            control, _, _, _ = self.spinners[name]
            if not control.isVisible():
                return
            control.blockSignals(True)
            if isinstance(control, QCheckBox):
                control.setChecked(bool(value))
            else:
                control.setValue(float(value))
            control.blockSignals(False)
            
        # Update based on element type
        if isinstance(self._element, Waypoint):
            set_control_value('x_meters', self._element.translation_target.x_meters)
            set_control_value('y_meters', self._element.translation_target.y_meters)
            if self._element.rotation_target.rotation_radians is not None:
                set_control_value('rotation_degrees', math.degrees(self._element.rotation_target.rotation_radians))
            set_control_value('profiled_rotation', getattr(self._element.rotation_target, 'profiled_rotation', True))
            
            # Handoff radius
            val = self._element.translation_target.intermediate_handoff_radius_meters
            if val is None and self._project_manager:
                val = self._project_manager.get_default_optional_value('intermediate_handoff_radius_meters')
            set_control_value('intermediate_handoff_radius_meters', float(val or 0.0))
            
        elif isinstance(self._element, TranslationTarget):
            set_control_value('x_meters', self._element.x_meters)
            set_control_value('y_meters', self._element.y_meters)
            
            # Handoff radius
            val = self._element.intermediate_handoff_radius_meters
            if val is None and self._project_manager:
                val = self._project_manager.get_default_optional_value('intermediate_handoff_radius_meters')
            set_control_value('intermediate_handoff_radius_meters', float(val or 0.0))
            
        elif isinstance(self._element, RotationTarget):
            if self._element.rotation_radians is not None:
                set_control_value('rotation_degrees', math.degrees(self._element.rotation_radians))
            set_control_value('profiled_rotation', getattr(self._element, 'profiled_rotation', True))
            set_control_value('rotation_position_ratio', float(getattr(self._element, 't_ratio', 0.0)))
            
    def _on_type_change(self, value: str):
        """Handle element type change."""
        self.typeChanged.emit(value)
        
    def _on_attribute_change(self, key: str, value):
        """Handle attribute value change."""
        self.attributeChanged.emit(key, value)
        
    def _on_attribute_removed(self, key: str):
        """Handle attribute removal."""
        self.attributeRemoved.emit(key)
        
    @classmethod
    def clamp_from_metadata(cls, key: str, value: float) -> float:
        """Clamp a value based on metadata range."""
        # This would need access to the metadata - for now just return value
        # In full implementation, this would use the spinner_metadata
        return value