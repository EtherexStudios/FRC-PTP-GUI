"""Constraint manager component for handling path constraints and range sliders."""

from typing import Dict, Optional, Tuple, Any, List
from PySide6.QtCore import QObject, Signal, QTimer, Qt, QEvent
from PySide6.QtWidgets import QWidget, QLabel, QDoubleSpinBox, QVBoxLayout, QFormLayout, QPushButton, QHBoxLayout, QSizePolicy
from PySide6.QtGui import QCursor, QMouseEvent, QIcon
from PySide6.QtCore import QSize
from models.path_model import Path, RangedConstraint
from ..widgets import RangeSlider, NoWheelDoubleSpinBox
from ..utils import SPINNER_METADATA, PATH_CONSTRAINT_KEYS, NON_RANGED_CONSTRAINT_KEYS


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
        self.path = None  # type: Optional[Path]
        self.project_manager = None  # Set externally for config access
        # Track inline range slider containers (one container per key holding all its instances)
        self._range_slider_rows = {}
        # For each key store list of sliders (one per ranged constraint instance)
        self._range_sliders = {}
        # For each key store list of spin boxes (first one is the original from property editor)
        self._range_spinboxes = {}
        self._active_preview_key = None
        # Map of constraint key -> field container used in constraints layout
        self._constraint_field_containers = {}
        
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
        """Add a path-level constraint.

        For ranged-capable constraints, this will APPEND a new ranged instance instead of
        replacing existing ones so multiple instances of the same constraint key may exist.
        """
        if self.path is None or not hasattr(self.path, 'constraints'):
            return False
            
        if value is None:
            value = self.get_default_value(key)
        # For non-ranged keys, store directly on flat constraints
        if key in NON_RANGED_CONSTRAINT_KEYS:
            try:
                setattr(self.path.constraints, key, float(value))
            except Exception:
                pass
            # Remove any stray ranged constraints of same key (defensive)
            try:
                self.path.ranged_constraints = [rc for rc in (getattr(self.path, 'ranged_constraints', []) or []) if rc.key != key]
            except Exception:
                pass
        else:
            # Append a new ranged constraint spanning the full domain
            try:
                _domain, count = self.get_domain_info_for_key(key)
                total = int(count) if int(count) > 0 else 1
                if not hasattr(self.path, 'ranged_constraints') or self.path.ranged_constraints is None:
                    self.path.ranged_constraints = []
                self.path.ranged_constraints.append(RangedConstraint(key=key, value=value, start_ordinal=1, end_ordinal=total))
            except Exception:
                pass
            # Clear flat value storage for ranged keys
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
            
        if key in NON_RANGED_CONSTRAINT_KEYS:
            # Remove flat constraint only
            try:
                setattr(self.path.constraints, key, None)
            except Exception:
                pass
            self.constraintRemoved.emit(key)
            return True
        # Ranged-capable key
        try:
            ranged_list = [rc for rc in (getattr(self.path, 'ranged_constraints', []) or []) if getattr(rc, 'key', None) == key]
        except Exception:
            ranged_list = []
        if not ranged_list:
            # Nothing to remove; ensure flat cleared
            try:
                setattr(self.path.constraints, key, None)
            except Exception:
                pass
            # Also remove any lingering UI container for this key
            try:
                self._remove_container_for_key(key)
            except Exception:
                pass
            self.constraintRemoved.emit(key)
            return True
        if len(ranged_list) > 1:
            # Remove only the FIRST instance (top) and keep others
            first = ranged_list[0]
            try:
                self.path.ranged_constraints = [rc for rc in (getattr(self.path, 'ranged_constraints', []) or []) if rc is not first]
            except Exception:
                pass
            # Do NOT emit full removal; UI refresh will rebuild remaining instances
            return True
        # Single instance -> full removal
        try:
            self.path.ranged_constraints = [rc for rc in (getattr(self.path, 'ranged_constraints', []) or []) if getattr(rc, 'key', None) != key]
        except Exception:
            pass
        try:
            setattr(self.path.constraints, key, None)
        except Exception:
            pass
        # Remove visual container if present
        try:
            self._remove_container_for_key(key)
        except Exception:
            pass
        self.constraintRemoved.emit(key)
        return True

    def _remove_container_for_key(self, key: str):
        """Hide the visual container and clear references for a ranged constraint key without disturbing others."""
        container = None
        try:
            container = self._constraint_field_containers.get(key, None)
        except Exception:
            container = None
        try:
            self._range_slider_rows.pop(key, None)
        except Exception:
            pass
        try:
            self._range_sliders.pop(key, None)
        except Exception:
            pass
        try:
            self._range_spinboxes.pop(key, None)
        except Exception:
            pass
        if container is not None:
            try:
                container.setVisible(False)
            except Exception:
                pass
        
    def update_constraint_value(self, key: str, value: float):
        """Update the value of a constraint."""
        if self.path is None or not hasattr(self.path, 'constraints'):
            return
        if key in NON_RANGED_CONSTRAINT_KEYS:
            # Direct flat update
            try:
                setattr(self.path.constraints, key, float(value))
            except Exception:
                setattr(self.path.constraints, key, value)
        else:
            # Update ranged constraints for this key ONLY if a single instance exists.
            # (When multiple instances exist they have dedicated spin boxes.)
            try:
                matching = [rc for rc in (getattr(self.path, 'ranged_constraints', []) or []) if getattr(rc, 'key', None) == key]
                if len(matching) == 1:
                    rc = matching[0]
                    try:
                        rc.value = float(value)
                    except Exception:
                        rc.value = value
                elif len(matching) > 1:
                    # Update only the FIRST instance to mirror legacy behavior (others keep own values)
                    rc0 = matching[0]
                    try:
                        rc0.value = float(value)
                    except Exception:
                        rc0.value = value
                # Always clear flat storage
                try:
                    setattr(self.path.constraints, key, None)
                except Exception:
                    pass
            except Exception:
                pass
            
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
        slider_max = total + 1  # one extra notch beyond the last anchor
        
        # Build / rebuild UI for ALL ranged instances of this key.
        # Gather current ranged constraints for this key
        ranged_list = [rc for rc in (getattr(self.path, 'ranged_constraints', []) or []) if rc.key == key]
        if not ranged_list:
            # Nothing to build yet (should not happen if caller added constraint earlier)
            return None

        # Ensure container exists and wraps the original spin_row
        field_container = self._constraint_field_containers.get(key)
        if field_container is None:
            field_container = QWidget()
            vbox = QVBoxLayout(field_container)
            # Add generous insets to avoid tight edges against the background box
            vbox.setContentsMargins(8, 11, 8, 10)
            vbox.setSpacing(4)
            try:
                field_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            except Exception:
                pass
            # Move label to the top of the field container for vertical layout
            # and place the original spin row under it.
            # Replace the label cell in the form with a tiny placeholder to keep row height consistent.
            # Propagate properties used for styling
            try:
                group_name = spin_row.property('constraintGroup')
                if group_name is not None:
                    field_container.setProperty('constraintGroup', group_name)
                # Mark container as an encompassing group box; rows will be separate
                field_container.setProperty('constraintGroupContainer', 'true')
            except Exception:
                pass
            self._constraint_field_containers[key] = field_container
            # Replace spin_row with container in form layout
            for i in range(constraints_layout.rowCount()):
                item = constraints_layout.itemAt(i, QFormLayout.LabelRole)
                if item and item.widget() == label_widget:
                    # Remove label from the form layout and reparent into our container
                    try:
                        constraints_layout.removeWidget(label_widget)
                    except Exception:
                        pass
                    # Remove the existing field widget, we will span across the row
                    try:
                        field_item = constraints_layout.itemAt(i, QFormLayout.FieldRole)
                        if field_item is not None and field_item.widget() is not None:
                            constraints_layout.removeWidget(field_item.widget())
                    except Exception:
                        pass
                    # Build vertical stack: label on top, then the spin row
                    label_widget.setParent(field_container)
                    try:
                        # Allow the label to elide instead of forcing horizontal scroll
                        label_widget.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
                    except Exception:
                        pass
                    vbox.addWidget(label_widget)
                    vbox.addWidget(spin_row)
                    # Add padding within the bordered base row (spinner+slider+minus)
                    try:
                        _base_layout = spin_row.layout()
                        if _base_layout is not None:
                            _base_layout.setContentsMargins(8, 8, 8, 8)
                            _base_layout.setSpacing(8)
                        spin_row.setMaximumHeight(44)
                    except Exception:
                        pass
                    # Span full row to align left edge with non-ranged combined rows
                    constraints_layout.setWidget(i, QFormLayout.SpanningRole, field_container)
                    try:
                        field_container.setVisible(True)
                    except Exception:
                        pass
                    break
        else:
            # Re-show previously hidden container and ensure it's in the layout
            try:
                field_container.setVisible(True)
            except Exception:
                pass
            try:
                present = False
                for i in range(constraints_layout.rowCount()):
                    for role in (QFormLayout.SpanningRole, QFormLayout.FieldRole, QFormLayout.LabelRole):
                        it = constraints_layout.itemAt(i, role)
                        if it is not None and it.widget() is field_container:
                            present = True
                            break
                    if present:
                        break
                if not present:
                    constraints_layout.addRow(field_container)
            except Exception:
                pass
        vbox: QVBoxLayout = field_container.layout()  # type: ignore

        # Clear existing dynamically added widgets (all after the first two: label and base spin_row)
        # We'll rebuild to reflect model state
        while vbox.count() > 2:
            item = vbox.itemAt(2)
            w = item.widget()
            if w is not None:
                vbox.removeWidget(w)
                w.deleteLater()
            else:
                vbox.removeItem(item)

        # Prepare lists
        sliders: List[RangeSlider] = []
        spins: List[QDoubleSpinBox] = []

        # The first spinbox is the provided control for instance index 0
        spins.append(control)

        # Helper to create slider/spinner pair for given instance index
        def _make_slider_for_instance(instance_index: int, rc_obj):
            # Determine low/high from model
            low_i_model = int(getattr(rc_obj, 'start_ordinal', 1))
            high_i_model = int(getattr(rc_obj, 'end_ordinal', total))
            # Map model (1-based inclusive) -> slider handles (left=start, right=end+1)
            low_i = max(1, min(low_i_model, total))
            high_i = max(2, min(high_i_model + 1, slider_max))
            sld = RangeSlider(1, slider_max)
            sld.setValues(low_i, high_i)
            sld.setFocusPolicy(Qt.StrongFocus)

            def _preview():
                l, h = sld.values()
                # Slider positions are conceptually 0-based; model ordinals are 1-based
                # start = left_position (0-based) -> +1 => l
                # end = right_position - 1 (0-based) -> +1 => (h - 1)
                start1 = max(1, min(int(l), int(total)))
                end1 = max(1, min(int(h - 1), int(total)))
                self._active_preview_key = key
                self.constraintRangePreviewRequested.emit(key, start1, end1)

            def _commit():
                l, h = sld.values()
                # Map slider handles (1..total+1) -> model ordinals (1..total)
                start1 = max(1, min(int(l), int(total)))
                end1 = max(1, min(int(h - 1), int(total)))
                try:
                    rc_obj.start_ordinal = start1
                    rc_obj.end_ordinal = end1
                except Exception:
                    pass
                self.constraintRangeChanged.emit(key, start1, end1)
                self._active_preview_key = key
                self.constraintRangePreviewRequested.emit(key, start1, end1)

            sld.rangeChanged.connect(lambda _l, _h: _preview())
            sld.interactionFinished.connect(lambda _l, _h: (setattr(self, '_active_preview_key', key), _commit()))
            return sld

        # Helper: ensure the base spin_row has no stale sliders before rebuilding
        def _remove_existing_sliders_from_row(row_widget: QWidget):
            try:
                row_layout = row_widget.layout()
                if row_layout is None:
                    return
                # Iterate backwards when removing
                for idx_rm in range(row_layout.count() - 1, -1, -1):
                    it = row_layout.itemAt(idx_rm)
                    if it is None:
                        continue
                    w = it.widget()
                    if w is not None and isinstance(w, RangeSlider):
                        try:
                            row_layout.removeWidget(w)
                        except Exception:
                            pass
                        w.deleteLater()
            except Exception:
                pass

        _remove_existing_sliders_from_row(spin_row)

        # Build UI for each instance
        for idx, rc_obj in enumerate(ranged_list):
            # Determine spinbox to use
            if idx == 0:
                spinbox = control
                # Initialize value
                try:
                    spinbox.blockSignals(True)
                    spinbox.setValue(float(getattr(rc_obj, 'value', control.value())))
                finally:
                    spinbox.blockSignals(False)
                # Mark the base row widget to receive the rounded row styling
                try:
                    group_name = spin_row.property('constraintGroup') or spin_row.property('constraintGroup')
                    if group_name is None:
                        # Inherit from container's original row
                        group_name = getattr(spin_row, 'property', lambda *_: None)('constraintGroup')
                    if group_name is not None:
                        spin_row.setProperty('constraintGroup', group_name)
                    spin_row.setProperty('constraintRow', 'true')
                    # Ensure row has sufficient height to show border
                    try:
                        spin_row.setMinimumHeight(32)
                        spin_row.setMaximumHeight(44)
                    except Exception:
                        pass
                    # Repolish to apply dynamic property style
                    try:
                        st = spin_row.style()
                        st.unpolish(spin_row)
                        st.polish(spin_row)
                        spin_row.update()
                    except Exception:
                        pass
                except Exception:
                    pass
            else:
                # Create a new spin row with spinbox only (no remove button) per spec
                spin_row_extra = QWidget()
                spin_row_layout = QHBoxLayout(spin_row_extra)
                # Add inner padding around controls and slider (match base row bottom padding)
                spin_row_layout.setContentsMargins(8, 8, 8, 8)
                spin_row_layout.setSpacing(8)
                try:
                    spin_row_extra.setMinimumHeight(32)
                    spin_row_extra.setMaximumHeight(44)
                    spin_row_extra.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                except Exception:
                    pass
                spinbox = NoWheelDoubleSpinBox()
                meta = SPINNER_METADATA.get(key, {})
                spinbox.setSingleStep(meta.get('step', 0.1))
                rmin, rmax = meta.get('range', (0.0, 9999.0))
                spinbox.setRange(rmin, rmax)
                try:
                    spinbox.setDecimals(3)
                    spinbox.setKeyboardTracking(False)
                except Exception:
                    pass
                try:
                    spinbox.setValue(float(getattr(rc_obj, 'value', 0.0)))
                except Exception:
                    pass
                # Enforce uniform width matching the base control if possible
                try:
                    spinbox.setMinimumWidth(90)
                    spinbox.setMaximumWidth(160)
                    spinbox.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
                except Exception:
                    pass
                # Remove instance button
                remove_btn = QPushButton()
                try:
                    remove_btn.setIcon(QIcon("assets/remove_icon.png"))
                    remove_btn.setFixedSize(16, 16)
                    remove_btn.setIconSize(QSize(14, 14))
                    remove_btn.setStyleSheet("QPushButton { border: none; } QPushButton:hover { background: #555; border-radius: 3px; }")
                except Exception:
                    pass

                def _make_remove_handler(target_rc):
                    def _remove():
                        try:
                            self.path.ranged_constraints = [rc for rc in (getattr(self.path, 'ranged_constraints', []) or []) if rc is not target_rc]
                        except Exception:
                            pass
                        # If no instances left for key, emit full removal and return
                        remaining = [rc for rc in (getattr(self.path, 'ranged_constraints', []) or []) if getattr(rc, 'key', None) == key]
                        if not remaining:
                            # Fully remove constraint entry and its UI container
                            try:
                                self._remove_container_for_key(key)
                            except Exception:
                                pass
                            self.constraintRemoved.emit(key)
                            return
                        # Rebuild UI for remaining instances
                        try:
                            self.create_range_slider_for_key(key, control, spin_row, label_widget, constraints_layout)
                        except Exception:
                            pass
                        # Refresh preview to first instance
                        try:
                            self.set_active_preview_key(key)
                        except Exception:
                            pass
                    return _remove

                remove_btn.clicked.connect(_make_remove_handler(rc_obj))

                # Set styling properties to align with the group for consistent background
                try:
                    group_name = spin_row.property('constraintGroup')
                    if group_name is not None:
                        spin_row_extra.setProperty('constraintGroup', group_name)
                    spin_row_extra.setProperty('constraintRow', 'true')
                    # Repolish to apply dynamic property style
                    try:
                        st2 = spin_row_extra.style()
                        st2.unpolish(spin_row_extra)
                        st2.polish(spin_row_extra)
                        spin_row_extra.update()
                    except Exception:
                        pass
                except Exception:
                    pass

                # Initially add only the spinbox; slider and remove button are positioned below
                spin_row_layout.addWidget(spinbox)
                # Slider and remove_btn will be positioned after slider creation
                vbox.addWidget(spin_row_extra)
            spins.append(spinbox)

            # Connect value change per instance
            def _make_value_handler(target_rc):
                return lambda v: self._update_single_ranged_constraint_value(key, target_rc, float(v))
            spinbox.valueChanged.connect(_make_value_handler(rc_obj))

            # Create and add slider on the same row as the spinbox
            sld = _make_slider_for_instance(idx, rc_obj)
            try:
                row_widget = (spin_row if idx == 0 else spin_row_extra)
                row_layout = row_widget.layout()
                if row_layout is not None:
                    # For the base row, move the remove button to the far right after the slider
                    remove_btn_widget = None
                    current_remove_btn = None
                    if idx > 0:
                        current_remove_btn = remove_btn
                    # Extract any existing QPushButton (remove button) and spacers for reordering
                    for j in range(row_layout.count() - 1, -1, -1):
                        it = row_layout.itemAt(j)
                        if it is None:
                            continue
                        w = it.widget()
                        if w is not None and isinstance(w, QPushButton):
                            remove_btn_widget = w
                            try:
                                row_layout.removeWidget(w)
                            except Exception:
                                pass
                        elif it.spacerItem() is not None:
                            try:
                                row_layout.removeItem(it)
                            except Exception:
                                pass
                    # Ensure spinbox has a fixed width for uniformity
                    try:
                        if isinstance(spins[-1], QDoubleSpinBox):
                            spins[-1].setMinimumWidth(90)
                            spins[-1].setMaximumWidth(160)
                            spins[-1].setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
                    except Exception:
                        pass

                    # Add slider with expanding policy
                    try:
                        sld.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                    except Exception:
                        pass
                    row_layout.addWidget(sld)
                    # Stretch to push the remove button to the far right
                    row_layout.addStretch()
                    # Add or re-add the remove button at the end
                    if remove_btn_widget is not None:
                        row_layout.addWidget(remove_btn_widget)
                    elif current_remove_btn is not None:
                        row_layout.addWidget(current_remove_btn)
            except Exception:
                # Fallback: if layout missing, add as separate row
                vbox.addWidget(sld)
            sliders.append(sld)

        try:
            field_container.updateGeometry()
        except Exception:
            pass

            # Spinner focus preview linking
            orig_focus_in = spinbox.focusInEvent
            def _focus_in(ev, _sld=sld):
                l, h = _sld.values()
                self._active_preview_key = key
                self.constraintRangePreviewRequested.emit(key, int(l), int(h))
                orig_focus_in(ev)
            spinbox.focusInEvent = _focus_in

        # Make label clickable to show preview of first instance
        label_widget.setStyleSheet(label_widget.styleSheet() + " QLabel:hover { text-decoration: underline; }")
        label_widget.setCursor(QCursor(Qt.PointingHandCursor))

        class LabelClickFilter(QObject):
            def __init__(self, callback):
                super().__init__()
                self.callback = callback
            def eventFilter(self, obj, event):
                if event.type() == QEvent.MouseButtonPress:
                    if isinstance(event, QMouseEvent) and event.button() == Qt.LeftButton:
                        self.callback()
                        return True
                return False

        def _show_first_preview():
            if sliders:
                l, h = sliders[0].values()
                self._active_preview_key = key
                self.constraintRangePreviewRequested.emit(key, int(l), int(h))

        label_filter = LabelClickFilter(_show_first_preview)
        label_widget.installEventFilter(label_filter)
        if not hasattr(self, '_label_filters'):
            self._label_filters = {}
        self._label_filters[key] = label_filter

        # Store references
        self._range_sliders[key] = sliders
        self._range_spinboxes[key] = spins
        self._range_slider_rows[key] = field_container

        return sliders[0] if sliders else None

    def _update_single_ranged_constraint_value(self, key: str, rc_obj, value: float):
        """Update the value for one ranged constraint instance (internal)."""
        try:
            rc_obj.value = float(value)
        except Exception:
            try:
                rc_obj.value = value
            except Exception:
                pass
        # Emit generic value changed signal
        self.constraintValueChanged.emit(key, float(value))
        
    def clear_range_sliders(self):
        """Clear all range sliders."""
        try:
            # Remove only the slider widgets; keep the constraint rows intact
            for key, slider_list in list(self._range_sliders.items()):
                for slider in slider_list:
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
            self._range_spinboxes.clear()
        except Exception:
            pass
            
    def set_active_preview_key(self, key: str):
        """Set the active constraint preview key and emit preview signal."""
        try:
            if key in self._range_sliders and self._range_sliders[key]:
                s = self._range_sliders[key][0]
                l, h = s.values()
                self._active_preview_key = key
                self.constraintRangePreviewRequested.emit(key, int(l), int(h))
        except Exception:
            pass
            
    def refresh_active_preview(self):
        """Refresh the preview for the currently active constraint key."""
        try:
            if self._active_preview_key is not None and self._active_preview_key in self._range_sliders and self._range_sliders[self._active_preview_key]:
                s = self._range_sliders[self._active_preview_key][0]
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
            for _key, slider_list in self._range_sliders.items():
                for slider in slider_list:
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
