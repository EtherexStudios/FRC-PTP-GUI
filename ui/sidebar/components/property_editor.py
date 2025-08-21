"""Property editor component for managing element properties and spinners."""

import math
from typing import Dict, Any, Optional, Tuple
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget, QDoubleSpinBox, QCheckBox, QLabel, QPushButton, QHBoxLayout, QFormLayout, QSizePolicy, QFrame
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon
from models.path_model import TranslationTarget, RotationTarget, Waypoint
from ..utils import SPINNER_METADATA, DEGREES_TO_RADIANS_ATTR_MAP, clamp_from_metadata
from ..widgets import NoWheelDoubleSpinBox
from ..utils.constants import NON_RANGED_CONSTRAINT_KEYS


class PropertyEditor(QObject):
    """Manages property editing UI for path elements."""
    
    # Signals
    propertyChanged = Signal(str, object)  # key, value
    propertyRemoved = Signal(str)  # key
    propertyAdded = Signal(str)  # key
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.project_manager = None  # Set externally for config access
        
        # Store references to spinners and their UI elements
        self.spinners: Dict[str, Tuple[Any, QLabel, QPushButton, QWidget]] = {}
        
        # Map of display names to actual keys for optional properties
        self.optional_display_to_key: Dict[str, str] = {}
        
    def create_property_controls(self, form_layout: QFormLayout, constraints_layout: QFormLayout) -> Dict[str, Tuple[Any, QLabel, QPushButton, QWidget]]:
        """Create all property control widgets."""
        spinners: Dict[str, Tuple[Any, QLabel, QPushButton, QWidget]] = {}
        constraint_row_index = 0
        CONSTRAINT_LABEL_WIDTH = 170

        for name, data in SPINNER_METADATA.items():
            control_type = data.get('type', 'spinner')
            if control_type == 'checkbox':
                control = QCheckBox()
                control.setChecked(True if name == 'profiled_rotation' else False)
                control.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                control.toggled.connect(lambda v, n=name: self._on_value_changed(n, v))
            else:
                control = NoWheelDoubleSpinBox()
                control.setSingleStep(data['step'])
                control.setRange(*data['range'])
                control.setValue(0)
                try:
                    control.setDecimals(3)
                except Exception:
                    pass
                try:
                    control.setKeyboardTracking(False)
                except Exception:
                    pass
                control.setMinimumWidth(96)
                control.setMaximumWidth(200)
                control.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                control.valueChanged.connect(lambda v, n=name: self._on_value_changed(n, v))
            # Label
            label_text = data['label'].replace('<br/>', ' ')
            label = QLabel(label_text)
            # Disable wrapping so text is one row
            try:
                label.setWordWrap(False)
                label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            except Exception:
                pass
            label.setMinimumHeight(24)
            label.setToolTip(label_text)

            # Row container
            spin_row = QWidget()
            spin_row_layout = QHBoxLayout(spin_row)
            spin_row_layout.setContentsMargins(0, 0, 0, 0)
            spin_row_layout.setSpacing(5)
            spin_row.setMinimumHeight(28)
            spin_row.setMaximumHeight(28)

            # Remove button
            btn = QPushButton()
            btn.setIconSize(QSize(14, 14))
            btn.setFixedSize(16, 16)
            btn.setStyleSheet("QPushButton { border: none; } QPushButton:hover { background: #555; border-radius: 3px; }")
            if data.get('removable', True):
                btn.setIcon(QIcon("assets/remove_icon.png"))
                btn.clicked.connect(lambda checked=False, n=name: self._on_property_removed(n))
            else:
                btn.setIcon(QIcon())
                btn.setEnabled(False)

            spin_row_layout.addWidget(control)
            spin_row_layout.addWidget(btn)
            spin_row_layout.addStretch()
            spin_row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

            # Section placement & grouping
            section = data.get('section', 'core')
            if section == 'core':
                # Fixed label width for core rows
                label.setMinimumWidth(CONSTRAINT_LABEL_WIDTH)
                label.setMaximumWidth(CONSTRAINT_LABEL_WIDTH)
                label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
                form_layout.addRow(label, spin_row)
            elif section == 'constraints':
                if constraint_row_index < 3:
                    group_name = 'nonranged'
                    index_in_group = constraint_row_index
                    group_size = 3
                elif constraint_row_index < 5:
                    group_name = 'translation'
                    index_in_group = constraint_row_index - 3
                    group_size = 2
                else:
                    group_name = 'rotation'
                    index_in_group = constraint_row_index - 5
                    group_size = 2

                pos = 'mid'
                if index_in_group == 0:
                    pos = 'first'
                if index_in_group == group_size - 1:
                    pos = 'last' if pos != 'first' else 'single'
                # For non-ranged constraints, build a single combined row spanning both columns.
                if name in NON_RANGED_CONSTRAINT_KEYS:
                    try:
                        from PySide6.QtWidgets import QHBoxLayout as _QHBox
                        combined_row = QWidget()
                        combined_layout = _QHBox(combined_row)
                        # Match ranged row padding and spacing (add a bit more bottom padding)
                        combined_layout.setContentsMargins(8, 8, 8, 8)
                        combined_layout.setSpacing(6)
                        try:
                            combined_row.setMinimumHeight(32)
                            combined_row.setMaximumHeight(44)
                            combined_row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                        except Exception:
                            pass
                        label.setParent(combined_row)
                        try:
                            label.setMinimumWidth(80)
                            label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
                        except Exception:
                            pass
                        combined_layout.addWidget(label)
                        try:
                            control.setMinimumWidth(70)
                            control.setMaximumWidth(70)
                            control.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
                        except Exception:
                            pass
                        try:
                            # Favor giving some space to the label before control/button
                            combined_layout.setStretch(0, 1)
                            combined_layout.setStretch(1, 0)
                        except Exception:
                            pass
                        combined_layout.addWidget(control)
                        combined_layout.addWidget(btn)
                        combined_layout.addStretch()
                        combined_row.setProperty('constraintGroup', group_name)
                        combined_row.setProperty('constraintRow', 'true')
                        constraints_layout.addRow(combined_row)
                        spin_row = combined_row
                    except Exception:
                        constraints_layout.addRow(label, spin_row)
                else:
                    # Ranged-capable constraints keep traditional two-column row.
                    # Apply styling to the row only to avoid label clipping.
                    spin_row.setProperty('constraintGroup', group_name)
                    spin_row.setProperty('groupPos', pos)
                    constraints_layout.addRow(label, spin_row)
                constraint_row_index += 1

            spinners[name] = (control, label, btn, spin_row)

        self.spinners = spinners
        return spinners
        
    def hide_all_properties(self):
        """Hide all property controls."""
        for name, (spin, label, btn, spin_row) in self.spinners.items():
            label.setVisible(False)
            spin_row.setVisible(False)
            
    def expose_element_properties(self, element: Any) -> list:
        """Show properties for the given element and return list of optional properties."""
        if element is None:
            return []
            
        # Reset and hide all first
        self.hide_all_properties()
        optional_display_items = []
        self.optional_display_to_key = {}
        
        # Helper: sanitize labels for menu display (strip HTML line breaks)
        def _menu_label_for_key(key: str) -> str:
            meta = SPINNER_METADATA.get(key, {})
            return meta.get('label', key).replace('<br/>', ' ')
            
        # Helper: show or queue a direct attribute
        def show_attr(attr_owner, name, convert_deg=False):
            if name not in self.spinners:
                return False
            control, label, btn, spin_row = self.spinners[name]
            if hasattr(attr_owner, name):
                value = getattr(attr_owner, name)
                if value is not None:
                    try:
                        control.blockSignals(True)
                        if isinstance(control, QCheckBox):
                            control.setChecked(bool(value))
                        else:
                            shown = math.degrees(value) if convert_deg else value
                            control.setValue(shown)
                    finally:
                        control.blockSignals(False)
                    label.setVisible(True)
                    spin_row.setVisible(True)
                    return True
                else:
                    display = _menu_label_for_key(name)
                    optional_display_items.append(display)
                    self.optional_display_to_key[display] = name
            return False

        # Helper: show a degrees-based attribute mapped from radians on model
        def show_deg_attr(owner, deg_name):
            if deg_name not in self.spinners:
                return False
            model_attr = DEGREES_TO_RADIANS_ATTR_MAP.get(deg_name)
            if not model_attr:
                return False
            control, label, btn, spin_row = self.spinners[deg_name]
            if hasattr(owner, model_attr):
                value = getattr(owner, model_attr)
                if value is not None:
                    try:
                        control.blockSignals(True)
                        control.setValue(math.degrees(value))
                    finally:
                        control.blockSignals(False)
                    label.setVisible(True)
                    spin_row.setVisible(True)
                    return True
                else:
                    # Only force-show default for rotation_degrees; for limits queue as optional
                    if deg_name == 'rotation_degrees':
                        try:
                            control.blockSignals(True)
                            control.setValue(0.0)
                        finally:
                            control.blockSignals(False)
                        label.setVisible(True)
                        spin_row.setVisible(True)
                        return True
                    else:
                        display = _menu_label_for_key(deg_name)
                        optional_display_items.append(display)
                        self.optional_display_to_key[display] = deg_name
            return False
            
        # Decide which owners contribute which fields
        if isinstance(element, Waypoint):
            # Position from translation_target
            show_attr(element.translation_target, 'x_meters')
            show_attr(element.translation_target, 'y_meters')
            # Rotation degrees from rotation_target
            show_deg_attr(element.rotation_target, 'rotation_degrees')
            # Profiled rotation from rotation_target
            show_attr(element.rotation_target, 'profiled_rotation')
            # Core handoff radius (force-visible for Waypoints)
            self._show_handoff_radius(element.translation_target)
        elif isinstance(element, TranslationTarget):
            show_attr(element, 'x_meters')
            show_attr(element, 'y_meters')
            # Core handoff radius for TranslationTarget
            self._show_handoff_radius(element)
        elif isinstance(element, RotationTarget):
            show_deg_attr(element, 'rotation_degrees')
            # Profiled rotation
            show_attr(element, 'profiled_rotation')
            # Show rotation position ratio (0..1)
            if 'rotation_position_ratio' in self.spinners:
                control, label, btn, spin_row = self.spinners['rotation_position_ratio']
                try:
                    control.blockSignals(True)
                    control.setValue(float(getattr(element, 't_ratio', 0.0)))
                finally:
                    control.blockSignals(False)
                label.setVisible(True)
                spin_row.setVisible(True)
                
        return optional_display_items
        
    def update_values_only(self, element: Any):
        """Update only the values of visible controls without changing visibility."""
        # Helper to set a control value safely
        def set_control_value(name: str, value):
            if name not in self.spinners:
                return
            control, _, _, _ = self.spinners[name]
            if not control.isVisible():
                return
            try:
                control.blockSignals(True)
                if isinstance(control, QCheckBox):
                    control.setChecked(bool(value))
                else:
                    control.setValue(float(value))
            finally:
                control.blockSignals(False)

        # Update position
        if isinstance(element, Waypoint):
            set_control_value('x_meters', element.translation_target.x_meters)
            set_control_value('y_meters', element.translation_target.y_meters)
            # rotation degrees
            if element.rotation_target.rotation_radians is not None:
                set_control_value('rotation_degrees', math.degrees(element.rotation_target.rotation_radians))
            # profiled rotation
            set_control_value('profiled_rotation', getattr(element.rotation_target, 'profiled_rotation', True))
            # core handoff radius
            self._update_handoff_radius_value(element.translation_target)
        elif isinstance(element, TranslationTarget):
            set_control_value('x_meters', element.x_meters)
            set_control_value('y_meters', element.y_meters)
            # core handoff radius
            self._update_handoff_radius_value(element)
        elif isinstance(element, RotationTarget):
            if element.rotation_radians is not None:
                set_control_value('rotation_degrees', math.degrees(element.rotation_radians))
            # profiled rotation
            set_control_value('profiled_rotation', getattr(element, 'profiled_rotation', True))
            set_control_value('rotation_position_ratio', float(getattr(element, 't_ratio', 0.0)))
            
        # For waypoints, also reflect rotation ratio from the embedded rotation_target
        if isinstance(element, Waypoint):
            set_control_value('rotation_position_ratio', float(getattr(element.rotation_target, 't_ratio', 0.0)))
            
    def get_property_value(self, key: str, element: Any) -> Optional[Any]:
        """Get the current value of a property from an element."""
        # Check if it's a degrees-based property
        if key in DEGREES_TO_RADIANS_ATTR_MAP:
            model_attr = DEGREES_TO_RADIANS_ATTR_MAP[key]
            if isinstance(element, Waypoint):
                if hasattr(element.rotation_target, model_attr):
                    rad_value = getattr(element.rotation_target, model_attr)
                    return math.degrees(rad_value) if rad_value is not None else None
            elif hasattr(element, model_attr):
                rad_value = getattr(element, model_attr)
                return math.degrees(rad_value) if rad_value is not None else None
        else:
            # Direct attribute
            if isinstance(element, Waypoint):
                if hasattr(element.translation_target, key):
                    return getattr(element.translation_target, key)
                elif hasattr(element.rotation_target, key):
                    return getattr(element.rotation_target, key)
            elif hasattr(element, key):
                return getattr(element, key)
        return None
        
    def set_property_value(self, key: str, value: Any, element: Any):
        """Set a property value on an element."""
        # Handle rotation position ratio updates
        if key == 'rotation_position_ratio':
            clamped_ratio = clamp_from_metadata(key, float(value))
            if isinstance(element, Waypoint):
                try:
                    element.rotation_target.t_ratio = float(clamped_ratio)
                except Exception:
                    pass
            elif isinstance(element, RotationTarget):
                element.t_ratio = float(clamped_ratio)
            return
            
        if key in DEGREES_TO_RADIANS_ATTR_MAP:
            # Degrees-mapped keys
            mapped = DEGREES_TO_RADIANS_ATTR_MAP[key]
            if key == 'rotation_degrees':
                clamped_deg = clamp_from_metadata(key, float(value))
                rad_value = math.radians(clamped_deg)
                if isinstance(element, Waypoint):
                    if hasattr(element.rotation_target, mapped):
                        setattr(element.rotation_target, mapped, rad_value)
                elif hasattr(element, mapped):
                    setattr(element, mapped, rad_value)
        else:
            # Core element attributes
            if key == 'profiled_rotation':
                # Handle profiled_rotation specifically for rotation targets
                if isinstance(element, Waypoint):
                    if hasattr(element.rotation_target, key):
                        setattr(element.rotation_target, key, bool(value))
                elif isinstance(element, RotationTarget):
                    if hasattr(element, key):
                        setattr(element, key, bool(value))
            elif isinstance(element, Waypoint):
                if hasattr(element.translation_target, key):
                    clamped = clamp_from_metadata(key, float(value))
                    setattr(element.translation_target, key, clamped)
            elif hasattr(element, key):
                clamped = clamp_from_metadata(key, float(value))
                setattr(element, key, clamped)
                
    def _show_handoff_radius(self, element):
        """Show handoff radius control with proper default value."""
        if 'intermediate_handoff_radius_meters' not in self.spinners:
            return
            
        control, label, btn, spin_row = self.spinners['intermediate_handoff_radius_meters']
        val = getattr(element, 'intermediate_handoff_radius_meters', None)
        
        # Use default value from config if val is None
        if val is None:
            try:
                default_val = self.project_manager.get_default_optional_value('intermediate_handoff_radius_meters') if self.project_manager else None
                val = default_val if default_val is not None else 0.0
            except Exception:
                val = 0.0
                
        try:
            control.blockSignals(True)
            control.setValue(float(val))
        finally:
            control.blockSignals(False)
        label.setVisible(True)
        spin_row.setVisible(True)
        
    def _update_handoff_radius_value(self, element):
        """Update only the handoff radius value."""
        if 'intermediate_handoff_radius_meters' not in self.spinners:
            return
            
        control, _, _, _ = self.spinners['intermediate_handoff_radius_meters']
        if not control.isVisible():
            return
            
        if hasattr(element, 'intermediate_handoff_radius_meters'):
            val = element.intermediate_handoff_radius_meters
            if val is not None:
                try:
                    control.blockSignals(True)
                    control.setValue(float(val))
                finally:
                    control.blockSignals(False)
            else:
                # Use default value from config if val is None
                try:
                    default_val = self.project_manager.get_default_optional_value('intermediate_handoff_radius_meters') if self.project_manager else None
                    display_val = default_val if default_val is not None else 0.0
                    control.blockSignals(True)
                    control.setValue(float(display_val))
                finally:
                    control.blockSignals(False)
                    
    def _on_value_changed(self, key: str, value: Any):
        """Handle property value changes."""
        self.propertyChanged.emit(key, value)
        
    def _on_property_removed(self, key: str):
        """Handle property removal."""
        self.propertyRemoved.emit(key)
        
    def add_property_from_menu(self, key: str, element: Any) -> float:
        """Add a property from the optional menu."""
        # Determine default value from config if available
        cfg_default = None
        try:
            if self.project_manager is not None:
                cfg_default = self.project_manager.get_default_optional_value(key)
        except Exception:
            cfg_default = None
            
        base_val = float(cfg_default) if cfg_default is not None else 0.0
        
        # Set the property value
        self.set_property_value(key, base_val, element)
        
        self.propertyAdded.emit(key)
        return base_val
