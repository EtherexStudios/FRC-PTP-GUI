"""Constraint manager component for handling path constraints and range sliders."""

from typing import Dict, Optional, Tuple, Any
from PySide6.QtCore import QObject, Signal, QTimer, Qt, QEvent
from PySide6.QtWidgets import QWidget, QLabel, QDoubleSpinBox, QVBoxLayout, QFormLayout, QPushButton
from PySide6.QtGui import QCursor, QMouseEvent
from models.path_model import Path, RangedConstraint
from ..widgets import RangeSlider
from ..utils import SPINNER_METADATA, PATH_CONSTRAINT_KEYS


class ConstraintManager(QObject):
    """Manages path constraints and their UI representations including range sliders."""
    
    # Signals
    constraintAdded = Signal(str, float)  # key, value
    constraintRemoved = Signal(str)  # key
    constraintValueChanged = Signal(str, float)  # key, value
    constraintRangeChanged = Signal(str, int, int)  # key, start, end
    
    # Preview overlay signals
    constraintRangePreviewRequested = Signal(str, int, int)  # key, start_ordinal, end_ordinal
    constraintRangePreviewCleared = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.path: Optional[Path] = None
        self.project_manager = None  # Set externally for config access
        
        # Track inline range slider rows to avoid duplicates
        self._range_slider_rows: Dict[str, QWidget] = {}
        self._range_sliders: Dict[str, RangeSlider] = {}
        self._active_preview_key: Optional[str] = None
        
        # Map of constraint key -> field container used in constraints layout
        self._constraint_field_containers: Dict[str, QWidget] = {}
        
    def set_path(self, path: Path):
        """Set the path to manage constraints for."""
        self.path = path
        
    def get_default_value(self, key: str) -> float:
        """Get default value for a constraint from config or metadata."""
        cfg_default = None
        try:
            if self.project_manager is not None:
                cfg_default = self.project_manager.get_default_optional_value(key)
        except Exception:
            cfg_default = None
            
        if cfg_default is not None:
            return float(cfg_default)
            
        # Fall back to metadata default
        meta = SPINNER_METADATA.get(key, {})
        range_min, _ = meta.get('range', (0, 99999))
        return float(range_min)
        
    def add_constraint(self, key: str, value: Optional[float] = None) -> bool:
        """Add a path-level constraint."""
        if self.path is None or not hasattr(self.path, 'constraints'):
            return False
            
        if value is None:
            value = self.get_default_value(key)
            
        # Create or replace a ranged constraint covering the full domain immediately
        try:
            # Determine domain size
            domain, count = self.get_domain_info_for_key(key)
            total = int(count) if int(count) > 0 else 1
            
            # Remove existing ranges for this key
            self.path.ranged_constraints = [rc for rc in (getattr(self.path, 'ranged_constraints', []) or []) if rc.key != key]
            
            # Append a single full-span range with the base value
            self.path.ranged_constraints.append(RangedConstraint(key=key, value=value, start_ordinal=1, end_ordinal=total))
        except Exception:
            pass
            
        # Ensure flat constraint is not set (avoid duplication in JSON/UI semantics)
        try:
            setattr(self.path.constraints, key, None)
        except Exception:
            pass
            
        self.constraintAdded.emit(key, value)
        return True
        
    def remove_constraint(self, key: str) -> bool:
        """Remove a path-level constraint."""
        if self.path is None or not hasattr(self.path, 'constraints'):
            return False
            
        # Remove flat constraint
        try:
            setattr(self.path.constraints, key, None)
        except Exception:
            pass
            
        # Remove any ranged constraints for this key
        try:
            self.path.ranged_constraints = [rc for rc in (getattr(self.path, 'ranged_constraints', []) or []) if rc.key != key]
        except Exception:
            pass
            
        self.constraintRemoved.emit(key)
        return True
        
    def update_constraint_value(self, key: str, value: float):
        """Update the value of a constraint."""
        if self.path is None or not hasattr(self.path, 'constraints'):
            return
            
        # If there are ranged constraints for this key, update them
        try:
            has_range = any(getattr(rc, 'key', None) == key for rc in (getattr(self.path, 'ranged_constraints', []) or []))
        except Exception:
            has_range = False
            
        if has_range:
            try:
                new_list = []
                for rc in (getattr(self.path, 'ranged_constraints', []) or []):
                    if getattr(rc, 'key', None) == key:
                        try:
                            rc.value = float(value)
                        except Exception:
                            rc.value = value
                    new_list.append(rc)
                self.path.ranged_constraints = new_list
            except Exception:
                pass
            # Ensure flat constraint is cleared to keep JSON clean
            try:
                setattr(self.path.constraints, key, None)
            except Exception:
                pass
        else:
            setattr(self.path.constraints, key, value)
            
        self.constraintValueChanged.emit(key, value)
        
    def get_domain_info_for_key(self, key: str) -> Tuple[str, int]:
        """Return (domain_type, count) for the given key.
        domain_type in {"translation", "rotation"}.
        """
        if self.path is None:
            return "translation", 0
            
        if key in ("max_velocity_meters_per_sec", "max_acceleration_meters_per_sec2"):
            # Domain: anchors
            count = sum(1 for e in self.path.path_elements if hasattr(e, 'x_meters') or hasattr(e, 'translation_target'))
            return "translation", int(count)
        else:
            # Domain: rotation events
            count = sum(1 for e in self.path.path_elements if hasattr(e, 'rotation_radians') or hasattr(e, 'rotation_target'))
            return "rotation", int(count)
            
    def create_range_slider_for_key(
        self, 
        key: str, 
        control: QDoubleSpinBox, 
        spin_row: QWidget, 
        label_widget: QLabel,
        constraints_layout: QFormLayout
    ) -> RangeSlider:
        """Create or update a range slider for a constraint key."""
        domain, count = self.get_domain_info_for_key(key)
        total = max(1, count)
        
        # Determine current selection summary for initial setting
        lows = []
        highs = []
        for rc in getattr(self.path, 'ranged_constraints', []) or []:
            if rc.key == key:
                lows.append(int(rc.start_ordinal))
                highs.append(int(rc.end_ordinal))
        low = min(lows) if lows else 1
        high = max(highs) if highs else total

        # Check if we already have a slider for this key
        if key in self._range_sliders and key in self._range_slider_rows:
            slider = self._range_sliders[key]
            container = self._range_slider_rows[key]
            
            # Update range and values
            try:
                slider.blockSignals(True)
                slider.setRange(1, total)
                slider.setValues(low, high)
            finally:
                slider.blockSignals(False)
                
            return slider

        # Create a new slider
        slider = RangeSlider(1, total)
        slider.setValues(low, high)
        slider.setFocusPolicy(Qt.StrongFocus)
        try:
            slider.setEnabled(True)
        except Exception:
            pass

        def _on_preview():
            l, h = slider.values()
            self._active_preview_key = key
            self.constraintRangePreviewRequested.emit(key, int(l), int(h))

        def _on_commit():
            l, h = slider.values()
            # Replace existing ranges for this key with a single range
            try:
                current_val = float(getattr(self.path.constraints, key) or control.value())
            except Exception:
                current_val = float(control.value())
                
            self.path.ranged_constraints = [rc for rc in getattr(self.path, 'ranged_constraints', []) if rc.key != key]
            self.path.ranged_constraints.append(RangedConstraint(key=key, value=current_val, start_ordinal=int(l), end_ordinal=int(h)))
            
            self.constraintRangeChanged.emit(key, int(l), int(h))
            
            # Keep/restore preview
            self._active_preview_key = key
            self.constraintRangePreviewRequested.emit(key, int(l), int(h))

        # Connect slider signals
        slider.rangeChanged.connect(lambda _l, _h: _on_preview())
        slider.interactionFinished.connect(lambda _l, _h: (setattr(self, '_active_preview_key', key), _on_commit()))
        
        # Add preview activation for spinner interaction
        def _show_preview_for_control():
            """Show preview when interacting with the spinner"""
            l, h = slider.values()
            self._active_preview_key = key
            self.constraintRangePreviewRequested.emit(key, int(l), int(h))
        
        # Connect spinner focus and value changes
        control.valueChanged.connect(lambda _: _show_preview_for_control())
        
        # Override spinner focus event to show preview
        original_focus_in = control.focusInEvent
        def _spinner_focus_in(event):
            _show_preview_for_control()
            original_focus_in(event)
        control.focusInEvent = _spinner_focus_in
        
        # Make label clickable to show preview
        label_widget.setStyleSheet(label_widget.styleSheet() + " QLabel:hover { text-decoration: underline; }")
        label_widget.setCursor(QCursor(Qt.PointingHandCursor))
        
        # Create event filter for label clicks
        class LabelClickFilter(QObject):
            def __init__(self, callback):
                super().__init__()
                self.callback = callback
                
            def eventFilter(self, obj, event):
                if event.type() == QEvent.MouseButtonPress:
                    if isinstance(event, QMouseEvent) and event.button() == Qt.LeftButton:
                        print(f"DEBUG: Label clicked for {key}")  # Debug output
                        self.callback()
                        return True  # Event handled
                return False  # Let other events pass through
        
        # Install the event filter
        label_filter = LabelClickFilter(_show_preview_for_control)
        label_widget.installEventFilter(label_filter)
        
        # Store the filter to prevent garbage collection
        if not hasattr(self, '_label_filters'):
            self._label_filters = {}
        self._label_filters[key] = label_filter
        
        # Create container for slider
        field_container = self._constraint_field_containers.get(key)
        if field_container is None:
            field_container = QWidget()
            vbox = QVBoxLayout(field_container)
            vbox.setContentsMargins(0, 0, 0, 0)
            vbox.setSpacing(3)
            vbox.addWidget(spin_row)
            self._constraint_field_containers[key] = field_container
            
            # Replace the spin_row in the form layout with the container
            # Find the row index for this label
            for i in range(constraints_layout.rowCount()):
                item = constraints_layout.itemAt(i, QFormLayout.LabelRole)
                if item and item.widget() == label_widget:
                    # Replace the field widget with our container
                    constraints_layout.setWidget(i, QFormLayout.FieldRole, field_container)
                    break
        else:
            vbox = field_container.layout()
            
        # Add slider to container
        vbox.addWidget(slider)
        
        # Store references
        self._range_sliders[key] = slider
        self._range_slider_rows[key] = field_container
        
        return slider
        
    def clear_range_sliders(self):
        """Clear all range sliders."""
        try:
            # Remove only the slider widgets; keep the constraint rows intact
            for key, slider in list(self._range_sliders.items()):
                try:
                    parent = slider.parentWidget()
                    if parent is not None and parent.layout() is not None:
                        try:
                            parent.layout().removeWidget(slider)
                        except Exception:
                            pass
                    slider.deleteLater()
                except Exception:
                    pass
            self._range_slider_rows.clear()
            self._range_sliders.clear()
        except Exception:
            pass
            
    def set_active_preview_key(self, key: str):
        """Set the active constraint preview key and emit preview signal."""
        try:
            if key in self._range_sliders:
                s = self._range_sliders[key]
                l, h = s.values()
                self._active_preview_key = key
                self.constraintRangePreviewRequested.emit(key, int(l), int(h))
        except Exception:
            pass
            
    def refresh_active_preview(self):
        """Refresh the preview for the currently active constraint key."""
        try:
            if self._active_preview_key is not None and self._active_preview_key in self._range_sliders:
                s = self._range_sliders[self._active_preview_key]
                l, h = s.values()
                self.constraintRangePreviewRequested.emit(self._active_preview_key, int(l), int(h))
        except Exception:
            pass
            
    def clear_active_preview(self):
        """Clear the active preview."""
        try:
            self._active_preview_key = None
            self.constraintRangePreviewCleared.emit()
        except Exception:
            pass
            
    def is_widget_range_related(self, widget: QWidget) -> bool:
        """Return True if the clicked widget is inside a constraint label/spinner/slider area."""
        try:
            if widget is None:
                return False
                
            # Check sliders
            for _key, slider in self._range_sliders.items():
                try:
                    if slider is widget:
                        return True
                    if hasattr(slider, 'isAncestorOf') and slider.isAncestorOf(widget):
                        return True
                except Exception:
                    pass
                    
            # Check slider containers
            for _key, row in self._range_slider_rows.items():
                if row is None:
                    continue
                try:
                    if row is widget:
                        return True
                    if hasattr(row, 'isAncestorOf') and row.isAncestorOf(widget):
                        return True
                except Exception:
                    pass
                    
        except Exception:
            return False
            
        return False
        
    def get_constraint_value(self, key: str) -> Optional[float]:
        """Get the current value of a constraint."""
        if self.path is None or not hasattr(self.path, 'constraints'):
            return None
            
        # Check ranged constraints first
        try:
            for rc in getattr(self.path, 'ranged_constraints', []) or []:
                if getattr(rc, 'key', None) == key:
                    return float(getattr(rc, 'value', None))
        except Exception:
            pass
            
        # Check flat constraint
        try:
            val = getattr(self.path.constraints, key, None)
            if val is not None:
                return float(val)
        except Exception:
            pass
            
        return None
        
    def has_constraint(self, key: str) -> bool:
        """Check if a constraint is present."""
        if self.path is None:
            return False
            
        # Check ranged constraints
        try:
            if any(getattr(rc, 'key', None) == key for rc in (getattr(self.path, 'ranged_constraints', []) or [])):
                return True
        except Exception:
            pass
            
        # Check flat constraint
        try:
            if hasattr(self.path, 'constraints') and getattr(self.path.constraints, key, None) is not None:
                return True
        except Exception:
            pass
            
        return False
