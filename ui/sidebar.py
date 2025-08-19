from PySide6.QtWidgets import QWidget, QFormLayout, QLabel, QComboBox, QDoubleSpinBox, QMenu, QPushButton, QVBoxLayout, QHBoxLayout, QGroupBox, QSizePolicy, QSpacerItem, QMessageBox, QCheckBox
from PySide6.QtWidgets import QListWidget, QListWidgetItem 
from models.path_model import Path, TranslationTarget, RotationTarget, Waypoint, RangedConstraint
from PySide6.QtCore import Qt
from PySide6.QtCore import Signal, QPoint, QSize, QTimer, QRect, QEvent
from enum import Enum
from typing import Optional, Tuple
import math
from PySide6.QtGui import QIcon, QGuiApplication, QPainter, QColor, QPen
from ui.canvas_constants import FIELD_LENGTH_METERS, FIELD_WIDTH_METERS, ELEMENT_CIRCLE_RADIUS_M, ELEMENT_RECT_WIDTH_M, ELEMENT_RECT_HEIGHT_M
from typing import Any

from .sidebar_widgets import ElementType, CustomList, PopupCombobox, RangeSlider
class Sidebar(QWidget):
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
    spinner_metadata = {
        # Put rotation first so it appears at the top of Core
        'rotation_degrees': {'label': 'Rotation (deg)', 'step': 1.0, 'range': (-180.0, 180.0), 'removable': False, 'section': 'core'},
        'x_meters': {'label': 'X (m)', 'step': 0.05, 'range': (0.0, float(FIELD_LENGTH_METERS)), 'removable': False, 'section': 'core'},
        'y_meters': {'label': 'Y (m)', 'step': 0.05, 'range': (0.0, float(FIELD_WIDTH_METERS)), 'removable': False, 'section': 'core'},
        # Handoff radius is a core control for TranslationTarget and Waypoint
        'intermediate_handoff_radius_meters': {'label': 'Handoff Radius (m)', 'step': 0.05, 'range': (0, 99999), 'removable': False, 'section': 'core'}, 
        # Ratio along the segment between previous and next anchors for rotation elements (0..1)
        'rotation_position_ratio': {'label': 'Rotation Pos (0–1)', 'step': 0.01, 'range': (0.0, 1.0), 'removable': False, 'section': 'core'},
        # Boolean checkbox for profiled rotation
        'profiled_rotation': {'label': 'Profiled Rotation', 'type': 'checkbox', 'removable': False, 'section': 'core'},
        # Constraints (optional)
        'final_velocity_meters_per_sec': {'label': 'Final Velocity (m/s)', 'step': 0.1, 'range': (0, 99999), 'removable': True, 'section': 'constraints'},
        'max_velocity_meters_per_sec': {'label': 'Max Velocity (m/s)', 'step': 0.1, 'range': (0, 99999), 'removable': True, 'section': 'constraints'},
        'max_acceleration_meters_per_sec2': {'label': 'Max Acceleration (m/s²)', 'step': 0.1, 'range': (0, 99999), 'removable': True, 'section': 'constraints'},
        'max_velocity_deg_per_sec': {'label': 'Max Rot Velocity<br/>(deg/s)', 'step': 1.0, 'range': (0, 99999), 'removable': True, 'section': 'constraints'},
        'max_acceleration_deg_per_sec2': {'label': 'Max Rot Acceleration<br/>(deg/s²)', 'step': 1.0, 'range': (0, 99999), 'removable': True, 'section': 'constraints'}
    }        

    # Map UI spinner keys to model attribute names (for rotation fields in degrees)
    degrees_to_radians_attr_map = {
        'rotation_degrees': 'rotation_radians'
    }

    @classmethod
    def _meta(cls, key: str) -> dict:
        return cls.spinner_metadata.get(key, {})

    @classmethod
    def _label(cls, key: str) -> str:
        meta = cls._meta(key)
        return meta.get('label', key)

    @classmethod
    def _clamp_from_metadata(cls, key: str, value: float) -> float:
        meta = cls._meta(key)
        value_min, value_max = meta.get('range', (None, None))
        if value_min is None or value_max is None:
            return value
        if value < value_min:
            return value_min
        if value > value_max:
            return value_max
        return value
    
    def _create_translation_target(self, x_meters: float, y_meters: float, intermediate_handoff_radius_meters: Optional[float] = None) -> TranslationTarget:
        """Create a TranslationTarget with proper default handoff radius from config."""
        if intermediate_handoff_radius_meters is None:
            try:
                default_val = self.project_manager.get_default_optional_value('intermediate_handoff_radius_meters') if self.project_manager else None
                intermediate_handoff_radius_meters = default_val
            except Exception:
                intermediate_handoff_radius_meters = None
        
        return TranslationTarget(
            x_meters=x_meters,
            y_meters=y_meters,
            intermediate_handoff_radius_meters=intermediate_handoff_radius_meters
        )

    def _create_waypoint(
        self,
        x_meters: float,
        y_meters: float,
        *,
        intermediate_handoff_radius_meters: Optional[float] = None,
        rotation_radians: float = 0.0,
        t_ratio: float = 0.0,
        profiled_rotation: bool = True,
    ) -> Waypoint:
        """Create a Waypoint ensuring the translation target's handoff radius
        defaults from config when not provided.
        """
        tt = self._create_translation_target(
            x_meters=x_meters,
            y_meters=y_meters,
            intermediate_handoff_radius_meters=intermediate_handoff_radius_meters,
        )
        rt = RotationTarget(
            rotation_radians=rotation_radians,
            t_ratio=t_ratio,
            profiled_rotation=profiled_rotation,
        )
        return Waypoint(translation_target=tt, rotation_target=rt)

    def _get_robot_dimensions(self) -> Tuple[float, float]:
        """Return (length_m, width_m) for rectangle-based elements.
        Prefer project config if available, otherwise fall back to canvas defaults.
        """
        length_m = float(ELEMENT_RECT_WIDTH_M)
        width_m = float(ELEMENT_RECT_HEIGHT_M)
        try:
            if getattr(self, 'project_manager', None) is not None and getattr(self.project_manager, 'config', None):
                cfg = self.project_manager.config
                length_m = float(cfg.get('robot_length_meters', length_m))
                width_m = float(cfg.get('robot_width_meters', width_m))
        except Exception:
            pass
        return length_m, width_m

    def _element_bounding_radius_for_type(self, elem_type: ElementType) -> float:
        """Approximate half-diagonal radius for overlap checks based on element type."""
        if elem_type == ElementType.TRANSLATION:
            return float(ELEMENT_CIRCLE_RADIUS_M)
        # Waypoint and Rotation use rectangle dimensions
        length_m, width_m = self._get_robot_dimensions()
        return float(math.hypot(length_m / 2.0, width_m / 2.0))

    def _element_bounding_radius_for_instance(self, element: Any) -> float:
        if isinstance(element, TranslationTarget):
            return float(ELEMENT_CIRCLE_RADIUS_M)
        if isinstance(element, Waypoint) or isinstance(element, RotationTarget):
            length_m, width_m = self._get_robot_dimensions()
            return float(math.hypot(length_m / 2.0, width_m / 2.0))
        return 0.3

    def _element_position_for_index(self, idx: int) -> Tuple[float, float]:
        """Return model-space center position for element at idx."""
        if self.path is None or idx < 0 or idx >= len(self.path.path_elements):
            return 0.0, 0.0
        e = self.path.path_elements[idx]
        if isinstance(e, TranslationTarget):
            return float(e.x_meters), float(e.y_meters)
        if isinstance(e, Waypoint):
            return float(e.translation_target.x_meters), float(e.translation_target.y_meters)
        if isinstance(e, RotationTarget):
            prev_pos, next_pos = self._neighbor_positions_model(idx)
            if prev_pos is None or next_pos is None:
                return 0.0, 0.0
            ax, ay = prev_pos
            bx, by = next_pos
            try:
                t = float(getattr(e, 't_ratio', 0.0))
            except Exception:
                t = 0.0
            if t < 0.0:
                t = 0.0
            elif t > 1.0:
                t = 1.0
            return ax + t * (bx - ax), ay + t * (by - ay)
        return 0.0, 0.0

    def _propose_non_overlapping_position(self, base_x: float, base_y: float, new_type: ElementType) -> Tuple[float, float]:
        """Find a nearby position to base_x/base_y that avoids significant overlap with existing elements."""
        if self.path is None or not getattr(self.path, 'path_elements', None):
            # Clamp to field bounds and return
            return (
                Sidebar._clamp_from_metadata('x_meters', float(base_x)),
                Sidebar._clamp_from_metadata('y_meters', float(base_y)),
            )

        # Build list of existing positions and their radii
        existing: list[Tuple[float, float, float]] = []
        try:
            for i, el in enumerate(self.path.path_elements):
                px, py = self._element_position_for_index(i)
                r = self._element_bounding_radius_for_instance(el)
                existing.append((float(px), float(py), float(r)))
        except Exception:
            pass

        new_r = self._element_bounding_radius_for_type(new_type)
        margin = 0.10  # small visual gap

        def _is_clear(x: float, y: float) -> bool:
            for (ox, oy, orad) in existing:
                dx = x - ox
                dy = y - oy
                if dx * dx + dy * dy < (new_r + orad + margin) ** 2:
                    return False
            return True

        # First try base
        bx = Sidebar._clamp_from_metadata('x_meters', float(base_x))
        by = Sidebar._clamp_from_metadata('y_meters', float(base_y))
        if _is_clear(bx, by):
            return bx, by

        # Try offsets in expanding rings around base
        length_m, width_m = self._get_robot_dimensions()
        step = max(new_r * 2.0, max(length_m, width_m) * 0.6, float(ELEMENT_CIRCLE_RADIUS_M) * 2.0) + margin
        directions = [
            (1, 0), (-1, 0), (0, 1), (0, -1),
            (1, 1), (1, -1), (-1, 1), (-1, -1),
            (2, 0), (-2, 0), (0, 2), (0, -2),
        ]
        for ring in range(1, 4):
            dist = step * ring
            for dx_unit, dy_unit in directions:
                x = Sidebar._clamp_from_metadata('x_meters', bx + dx_unit * dist)
                y = Sidebar._clamp_from_metadata('y_meters', by + dy_unit * dist)
                if _is_clear(x, y):
                    return x, y

        # Fallback: return base clamped
        return bx, by

    # Preview overlay signals for ranged constraints
    constraintRangePreviewRequested = Signal(str, int, int)  # key, start_ordinal, end_ordinal
    constraintRangePreviewCleared = Signal()

    # RangeSlider moved to sidebar_widgets

    def __init__(self, path=Path()):

        super().__init__()
        main_layout = QVBoxLayout(self)
        self.setMinimumWidth(300) # Set a minimum width for the sidebar
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        # Top section for the list label and add button in horizontal layout
        top_section = QWidget()
        top_layout = QHBoxLayout(top_section)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(20)
        
        # label = QLabel("Path Elements")
        # top_layout.addWidget(label)

        # Refactored Path Elements label to match constraints title bar style
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
        # Match constraints title bar margins/spacing precisely
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
        # Push label to the left and keep the add button at the right inside the bar
        path_elements_bar_layout.addStretch()
        
        # Removed stretch here to avoid pushing the path elements bar to the right
        
        self.add_element_pop = PopupCombobox()
        self.add_element_pop.setText("Add element")
        self.add_element_pop.setToolTip("Add a path element at the current selection")
        self.add_element_pop.button.setIconSize(QSize(16, 16))
        self.add_element_pop.button.setMinimumHeight(22)
        self.add_element_pop.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        # prevent the button text from clipping within the bar
        self.add_element_pop.setText("Add element")

        path_elements_bar_layout.addWidget(self.add_element_pop)

        # Make the bar expand to full width of the top section
        top_layout.addWidget(self.path_elements_bar, 1)

        main_layout.addWidget(top_section)

        self.path = path
        # Optional: set externally to access config defaults
        self.project_manager = None
        # Re-entrancy/visibility guards
        self._suspended: bool = False
        self._ready: bool = False
        # Track last selected index for restoration when paths are reloaded
        self._last_selected_index: int = 0
        
        self.points_list = CustomList()
        main_layout.addWidget(self.points_list)
        # No global shortcuts here to avoid interfering with text editing fields.
        # The list (`points_list`) captures Delete/Backspace via its own keyPressEvent.

        main_layout.addSpacing(10) # Add space between list and groupbox

        # Create a container for the title bar to style it
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
        title_bar_layout.setContentsMargins(10, 0, 10, 0) # Remove vertical margins
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
        
        # Note: the constraints add button is moved to a separate "Path constraints" title bar
        
        main_layout.addWidget(self.title_bar)
        
        # Form section for editable properties
        self.form_container = QGroupBox()
        self.form_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.form_container.setStyleSheet("""
            QGroupBox { background-color: #242424; border: 1px solid #3f3f3f; border-radius: 6px; }
            QLabel { color: #f0f0f0; }
        """)
        
        # Main layout for the group box
        group_box_spinner_layout = QVBoxLayout(self.form_container)
        group_box_spinner_layout.setContentsMargins(6, 6, 6, 6)
        group_box_spinner_layout.setSpacing(8)

        # Properties form (no collapsibles): keep type selector and core spinners together
        self.core_page = QWidget()
        self.core_page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.core_layout = QFormLayout(self.core_page)
        self.core_layout.setLabelAlignment(Qt.AlignRight)
        self.core_layout.setVerticalSpacing(8)
        self.core_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        # Separate constraints group below with its own title bar (created later) and form layout
        self.constraints_form_container = QGroupBox()
        self.constraints_form_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.constraints_form_container.setStyleSheet(
            """
            QGroupBox { background-color: #242424; border: 1px solid #3f3f3f; border-radius: 6px; }
            QLabel { color: #f0f0f0; }
            """
        )
        self.constraints_layout = QFormLayout(self.constraints_form_container)
        self.constraints_layout.setLabelAlignment(Qt.AlignRight)
        self.constraints_layout.setVerticalSpacing(8)
        self.constraints_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        

        # Store label references for each spinner
        self.spinners = {}
        # Map of constraint key -> field container used in constraints layout
        self._constraint_field_containers: dict[str, QWidget] = {}
     
        # Optional elements combobox
        self.optional_container = QWidget()
        self.optional_box_layout = QHBoxLayout(self.optional_container)
        self.optional_box_layout.setContentsMargins(0, 0, 0, 0) # Removes extra padding

        self.type_combo = QComboBox()
        self.type_combo.addItems([e.value for e in ElementType])
        self.type_label = QLabel("Type:")

        self.optional_box_layout.addWidget(self.type_combo)

        # Put the type selector and optional property button above the toolbox
        header_row = QWidget()
        header_row_layout = QHBoxLayout(header_row)
        header_row_layout.setContentsMargins(0, 0, 0, 0)
        header_row_layout.setSpacing(6)
        header_row_layout.addWidget(self.type_label)
        header_row_layout.addWidget(self.optional_container, 1)
        group_box_spinner_layout.addWidget(header_row)
        # Place the core form (type + core spinners) directly in this group
        group_box_spinner_layout.addWidget(self.core_page)
        
        for name, data in self.spinner_metadata.items():
            # Create either a checkbox or a spinbox based on the type
            control_type = data.get('type', 'spinner')
            if control_type == 'checkbox':
                control = QCheckBox()
                control.setChecked(True if name == 'profiled_rotation' else False)
                control.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                # Connect checkbox to change handler
                control.toggled.connect(lambda v, n=name: self.on_attribute_change(n, v))
            else:
                control = QDoubleSpinBox()
                control.setSingleStep(data['step'])
                control.setRange(*data['range'])
                control.setValue(0)
                # Ensure better typing/paste UX and precision
                try:
                    control.setDecimals(3)  # show three decimal places
                except Exception:
                    pass
                try:
                    # Do not emit valueChanged on each keystroke; only when committed
                    control.setKeyboardTracking(False)
                except Exception:
                    pass
                control.setMinimumWidth(96) # Wider for readability
                control.setMaximumWidth(200) # Allow expansion when sidebar is wider
                control.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                # Connect spinbox to change handler
                control.valueChanged.connect(lambda v, n=name: self.on_attribute_change(n, v))
            
            label = QLabel(data['label'])
            # Check if label contains HTML and adjust wrapping accordingly
            if '<br/>' in data['label']:
                label.setWordWrap(False)  # Disable word wrap for HTML labels
                label.setTextFormat(Qt.RichText)  # Enable HTML rendering
            else:
                label.setWordWrap(True)
            label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            # Use plain text for tooltip (remove HTML tags)
            tooltip_text = data['label'].replace('<br/>', ' ')
            label.setToolTip(tooltip_text)
            label.setMinimumWidth(120) # Ensure labels have reasonable minimum width

            # Add button next to control
            spin_row = QWidget()
            spin_row_layout = QHBoxLayout(spin_row)
            spin_row_layout.setContentsMargins(0, 0, 0, 0)
            spin_row_layout.setSpacing(5) # Controls space between control and btn
            spin_row.setMinimumHeight(24)
            spin_row.setMaximumHeight(24)

            btn = QPushButton()
            btn.setIconSize(QSize(14, 14))
            btn.setFixedSize(16, 16)
            btn.setStyleSheet("QPushButton { border: none; } QPushButton:hover { background: #555; border-radius: 3px; }")

            if data.get('removable', True):
                btn.setIcon(QIcon("assets/remove_icon.png"))
                # Connect button to remove attribute
                # Remove path-level constraints via this handler too
                btn.clicked.connect(lambda checked=False, n=name: self.on_attribute_removed(n))
            else:
                btn.setIcon(QIcon()) # Blank icon
                btn.setEnabled(False) # Make non-removable buttons non-interactive

            spin_row_layout.addStretch() # Push widgets to the right
            spin_row_layout.addWidget(control)
            spin_row_layout.addWidget(btn)
            # Make the spin row expand to fill available width
            spin_row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

            # Add to the appropriate section based on metadata
            section = data.get('section', 'core')
            if section == 'core':
                self.core_layout.addRow(label, spin_row)
            elif section == 'constraints':
                # Wrap the spinner row in a stable container so later we can add a slider without replacing the row
                field_container = QWidget()
                vbl = QVBoxLayout(field_container)
                vbl.setContentsMargins(0, 0, 0, 0)
                vbl.setSpacing(3)
                vbl.addWidget(spin_row)
                try:
                    label.setFocusPolicy(Qt.StrongFocus)
                    label.installEventFilter(self)
                except Exception:
                    pass
                self.constraints_layout.addRow(label, field_container)
                self._constraint_field_containers[name] = field_container
            else:
                self.core_layout.addRow(label, spin_row)
            self.spinners[name] = (control, label, btn, spin_row)

        # Stretch to consume remaining vertical space
        group_box_spinner_layout.addStretch(1)
        # Subtle padding around the form
        self.form_container.setContentsMargins(6, 6, 6, 6)

        main_layout.addWidget(self.form_container)

        # Constraints title bar and add button (moved here)
        self.constraints_title_bar = QWidget()
        self.constraints_title_bar.setObjectName("constraintsTitleBar")
        self.constraints_title_bar.setStyleSheet(
            """
            QWidget#constraintsTitleBar {
                background-color: #2f2f2f;
                border: 1px solid #4a4a4a;
                border-radius: 6px;
            }
            """
        )
        constraints_title_layout = QHBoxLayout(self.constraints_title_bar)
        constraints_title_layout.setContentsMargins(8, 0, 8, 0)  # Reduced margins
        constraints_title_layout.setSpacing(8)  # Reduced spacing to prevent clipping
        constraints_label = QLabel("Path Constraints")
        constraints_label.setStyleSheet(
            """
            font-size: 14px;
            font-weight: bold;
            color: #eeeeee;
            background: transparent;
            border: none;
            padding: 6px 0;
            """
        )
        # Allow label to shrink if needed
        constraints_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        constraints_title_layout.addWidget(constraints_label)
        constraints_title_layout.addStretch()
        self.optional_pop = PopupCombobox()
        # Match the element add button sizing
        self.optional_pop.setText("Add constraint")
        self.optional_pop.setToolTip("Add an optional constraint")
        self.optional_pop.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        # Use consistent sizing with element add button
        self.optional_pop.button.setIconSize(QSize(16, 16))  # Match add_element_pop
        self.optional_pop.button.setMinimumHeight(22)  # Match add_element_pop
        constraints_title_layout.addWidget(self.optional_pop)
        # Populate available constraint keys immediately
        self.optional_display_to_key = {}

        main_layout.addWidget(self.constraints_title_bar)
        main_layout.addWidget(self.constraints_form_container)
        main_layout.addStretch() # Pushes all content to the top
        
        # Defer selection handling to the next event loop to avoid re-entrancy
        try:
            self.points_list.itemSelectionChanged.connect(self.on_item_selected)
        except Exception:
            pass
        self.points_list.reordered.connect(self.on_points_list_reordered)
        self.points_list.deleteRequested.connect(lambda: self._delete_via_shortcut())
        # Additional guard: prevent dragging rotation to start or end by enforcing after drop

        self.type_combo.currentTextChanged.connect(self.on_type_change)

        self.optional_pop.item_selected.connect(self.on_constraint_added)
        
        # Add element dropdown wiring
        self.add_element_pop.item_selected.connect(self.on_add_element_selected)
        
        self.rebuild_points_list()

        # Track inline range slider rows to avoid duplicates
        self._range_slider_rows: dict[str, QWidget] = {}
        self._range_sliders: dict[str, RangeSlider] = {}
        self._active_preview_key: Optional[str] = None
        # Allow sidebar-wide click to clear preview when clicking elsewhere
        self.installEventFilter(self)

    # Utilities for inline range sliders
    def _clear_range_sliders(self):
        try:
            # Remove only the slider widgets; keep the constraint rows intact
            for key, slider in list(self._range_sliders.items()):
                try:
                    parent = slider.parentWidget()
                    if parent is not None and isinstance(parent.layout(), QHBoxLayout) or isinstance(parent.layout(), QVBoxLayout):
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

    def _ensure_range_slider_for_key(self, name: str, control: QDoubleSpinBox, spin_row: QWidget, label_widget: QLabel):
        domain, count = self._domain_info_for_key(name)
        total = max(1, count)
        # Determine current selection summary for initial setting
        lows = []
        highs = []
        for rc in getattr(self.path, 'ranged_constraints', []) or []:
            if rc.key == name:
                lows.append(int(rc.start_ordinal))
                highs.append(int(rc.end_ordinal))
        low = min(lows) if lows else 1
        high = max(highs) if highs else total

        # Locate the constraints row for this label and get its current field widget
        row_index = -1
        current_field_widget = None
        try:
            for i in range(self.constraints_layout.rowCount()):
                lab_item = self.constraints_layout.itemAt(i, QFormLayout.LabelRole)
                if lab_item is not None and lab_item.widget() is label_widget:
                    row_index = i
                    break
            if row_index >= 0:
                current_item = self.constraints_layout.itemAt(row_index, QFormLayout.FieldRole)
                current_field_widget = current_item.widget() if current_item is not None else None
        except Exception:
            current_field_widget = None

        if name in self._range_sliders and name in self._range_slider_rows:
            slider = self._range_sliders[name]
            container = self._range_slider_rows[name]
            # If container is not currently the field widget, re-embed below
            if current_field_widget is not container:
                pass  # fall through to re-embed
            else:
                # Update range and values; avoid re-connecting signals
                try:
                    slider.blockSignals(True)
                    slider.setRange(1, total)
                    slider.setValues(low, high)
                finally:
                    slider.blockSignals(False)
                # Ensure order: spin_row then slider
                try:
                    vbox = container.layout()
                    if vbox is not None:
                        # Ensure widgets are present and ordered
                        # Remove then insert to fix order
                        vbox.removeWidget(spin_row)
                        vbox.insertWidget(0, spin_row)
                        vbox.removeWidget(slider)
                        vbox.insertWidget(1, slider)
                except Exception:
                    pass
                return

        # Create a new slider row
        slider = RangeSlider(1, total)
        slider.setValues(low, high)
        slider.setFocusPolicy(Qt.StrongFocus)
        try:
            slider.setEnabled(True)
        except Exception:
            pass

        def _on_preview():
            l, h = slider.values()
            # Force this constraint to be the active one and show its preview
            self._active_preview_key = name
            try:
                self.constraintRangePreviewRequested.emit(name, int(l), int(h))
            except Exception:
                pass

        def _on_commit():
            l, h = slider.values()
            try:
                self.aboutToChange.emit('Edit Ranged Constraint')
            except Exception:
                pass
            # Replace existing ranges for this key with a single range
            try:
                current_val = float(getattr(self.path.constraints, name) or control.value())
            except Exception:
                current_val = float(control.value())
            self.path.ranged_constraints = [rc for rc in getattr(self.path, 'ranged_constraints', []) if rc.key != name]
            self.path.ranged_constraints.append(RangedConstraint(key=name, value=current_val, start_ordinal=int(l), end_ordinal=int(h)))
            self.modelChanged.emit()
            try:
                self.userActionOccurred.emit('Edit Ranged Constraint')
            except Exception:
                pass
            # Keep/restore preview to this slider after commit so it persists
            try:
                self._active_preview_key = name
                self.constraintRangePreviewRequested.emit(name, int(l), int(h))
            except Exception:
                pass

        # Connect slider signals - only one connection per signal to avoid conflicts
        slider.rangeChanged.connect(lambda _l, _h: _on_preview())
        # On drag finish, ensure this slider remains the active preview owner
        slider.interactionFinished.connect(lambda _l, _h: (setattr(self, '_active_preview_key', name), _on_commit()))
        slider.installEventFilter(self)
        if isinstance(control, QDoubleSpinBox) and control is not None:
            control.installEventFilter(self)
            # Keep overlay visible when changing spinner value, but only if this constraint is currently active
            try:
                def _on_spinner_change(_v):
                    # Always activate and show this constraint's preview when its spinner changes
                    self._set_active_preview_key_and_emit(name)
                control.valueChanged.connect(_on_spinner_change)
            except Exception:
                pass

        # Make the label focusable for preview via keyboard/mouse and install filter
        try:
            if isinstance(label_widget, QLabel):
                label_widget.setFocusPolicy(Qt.StrongFocus)
                label_widget.installEventFilter(self)
                # Also connect mouse press on the label directly to show preview
                def _label_click_preview(_event=None, _n=name):
                    try:
                        self._active_preview_key = _n
                        s = self._range_sliders[_n]
                        l, h = s.values()
                        self.constraintRangePreviewRequested.emit(_n, int(l), int(h))
                    except Exception:
                        pass
                try:
                    label_widget.mousePressEvent = (lambda ev, fn=_label_click_preview: (fn(ev)))
                except Exception:
                    pass
        except Exception:
            pass

        # Embed the slider under the existing field using a vertical container (row_index already computed)

        # Prefer pre-built stable container if present
        field_container = self._constraint_field_containers.get(name)
        if field_container is None:
            field_container = QWidget()
            vbox = QVBoxLayout(field_container)
            vbox.setContentsMargins(0, 0, 0, 0)
            vbox.setSpacing(3)
            # Ensure spinner row is inside
            vbox.addWidget(spin_row)
            self._constraint_field_containers[name] = field_container
        else:
            vbox = field_container.layout()
        # Replace the field widget at this row with a container and add the original row + slider inside
        try:
            if row_index >= 0:
                # Replace the field with our container if not already
                current_item = self.constraints_layout.itemAt(row_index, QFormLayout.FieldRole)
                current_widget = current_item.widget() if current_item is not None else None
                if current_widget is not field_container:
                    self.constraints_layout.setWidget(row_index, QFormLayout.FieldRole, field_container)
                # Ensure order: spinner first, then slider
                try:
                    # Remove any existing slider from container to avoid stacking ghosts
                    for i in reversed(range(vbox.count())):
                        w = vbox.itemAt(i).widget()
                        if isinstance(w, RangeSlider) and w is not slider:
                            vbox.removeWidget(w)
                            try:
                                w.deleteLater()
                            except Exception:
                                pass
                    vbox.removeWidget(spin_row)
                except Exception:
                    pass
                vbox.insertWidget(0, spin_row)
                try:
                    vbox.removeWidget(slider)
                except Exception:
                    pass
                vbox.insertWidget(1, slider)
            else:
                # If we cannot find the row, append safely
                try:
                    vbox.removeWidget(spin_row)
                except Exception:
                    pass
                vbox.insertWidget(0, spin_row)
                try:
                    vbox.removeWidget(slider)
                except Exception:
                    pass
                vbox.insertWidget(1, slider)
                try:
                    self.constraints_layout.addRow(label_widget, field_container)
                except Exception:
                    pass
        except Exception:
            # Fallback append
            try:
                vbox.addWidget(spin_row)
                vbox.addWidget(slider)
                self.constraints_layout.addRow(label_widget, field_container)
            except Exception:
                pass

        self._range_sliders[name] = slider
        self._range_slider_rows[name] = field_container
        # Do not auto-show preview on creation to avoid reactivating overlay during non-constraint interactions

    def _set_active_preview_key_and_emit(self, name: str):
        try:
            if name in self._range_sliders:
                s = self._range_sliders[name]
                l, h = s.values()
                self._active_preview_key = name
                self.constraintRangePreviewRequested.emit(name, int(l), int(h))
        except Exception:
            pass
            
    def _refresh_active_preview(self):
        """Refresh the preview for the currently active constraint key."""
        try:
            if self._active_preview_key is not None and self._active_preview_key in self._range_sliders:
                s = self._range_sliders[self._active_preview_key]
                l, h = s.values()
                self.constraintRangePreviewRequested.emit(self._active_preview_key, int(l), int(h))
        except Exception:
            pass

    # ---- Public helpers for external widgets to control constraint preview ----
    def clear_active_preview(self):
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
            # Sliders: clicked widget is the slider or inside it
            for _key, slider in self._range_sliders.items():
                try:
                    if slider is widget:
                        return True
                    if hasattr(slider, 'isAncestorOf') and slider.isAncestorOf(widget):
                        return True
                except Exception:
                    pass
            # Slider containers (rows under the constraint field)
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
            # Labels and spinners for keys that have sliders
            for key in list(self._range_sliders.keys()):
                if key not in self.spinners:
                    continue
                try:
                    control, label, _btn, _row = self.spinners[key]
                except Exception:
                    continue
                for w in (control, label):
                    try:
                        if w is widget:
                            return True
                        if hasattr(w, 'isAncestorOf') and w.isAncestorOf(widget):
                            return True
                    except Exception:
                        continue
        except Exception:
            return False
        return False

    def eventFilter(self, obj, event):
        try:
            et = event.type()
            # Focus in on range-related widgets => show preview
            if et == QEvent.FocusIn:
                # Determine if this is one of our tracked sliders or spinboxes
                for key, s in self._range_sliders.items():
                    if obj is s:
                        l, h = s.values()
                        self._active_preview_key = key
                        self.constraintRangePreviewRequested.emit(key, int(l), int(h))
                        return False
                for key, (control, label, _btn, _row) in self.spinners.items():
                    if (obj is control or obj is label) and key in self._range_sliders:
                        s = self._range_sliders[key]
                        l, h = s.values()
                        self._active_preview_key = key
                        self.constraintRangePreviewRequested.emit(key, int(l), int(h))
                        return False
                        
            # Handle clicks on range-related controls to show preview immediately
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

                # Check if clicking on any range-related control and show preview immediately
                clicked_key = None
                
                # Check sliders and their containers
                for key, row in self._range_slider_rows.items():
                    if row is not None and (target_widget is row or row.isAncestorOf(target_widget)):
                        clicked_key = key
                        break
                        
                if clicked_key is None:
                    for key, s in self._range_sliders.items():
                        if target_widget is s or s.isAncestorOf(target_widget):
                            clicked_key = key
                            break
                            
                if clicked_key is None:
                    for key, (control, label, _btn, _row) in self.spinners.items():
                        if target_widget in (control, label) or (hasattr(control, 'isAncestorOf') and control.isAncestorOf(target_widget)):
                            if key in self._range_sliders:
                                clicked_key = key
                                break
                
                # If we clicked on a range-related control, show its preview immediately
                if clicked_key is not None:
                    try:
                        # Clear any existing preview first
                        if self._active_preview_key != clicked_key:
                            self.constraintRangePreviewCleared.emit()
                        
                        s = self._range_sliders[clicked_key]
                        l, h = s.values()
                        self._active_preview_key = clicked_key
                        self.constraintRangePreviewRequested.emit(clicked_key, int(l), int(h))
                    except Exception:
                        pass
                    return False
                
                # Clicked somewhere not tied to a constraint slider/spinner/label → clear overlay
                self._active_preview_key = None
                self.constraintRangePreviewCleared.emit()
                
                return False
                        
        except Exception:
            pass
        return super().eventFilter(obj, event)

    # ---------- Ranged constraints helpers ----------
    def _domain_info_for_key(self, key: str) -> tuple[str, int]:
        """Return (domain_type, count) for the given key.
        domain_type in {"translation", "rotation"}.
        """
        if self.path is None:
            return "translation", 0
        if key in ("max_velocity_meters_per_sec", "max_acceleration_meters_per_sec2"):
            # Domain: anchors
            count = sum(1 for e in self.path.path_elements if isinstance(e, (TranslationTarget, Waypoint)))
            return "translation", int(count)
        else:
            # Domain: rotation events (RotationTarget + Waypoint)
            count = sum(1 for e in self.path.path_elements if isinstance(e, (RotationTarget, Waypoint)))
            return "rotation", int(count)

    # NOTE: All ranged constraints are now edited inline under their value spinners using RangeSlider
    
    def _delete_via_shortcut(self):
        # Emit a deletion request so the owner can handle model + undo coherently
        try:
            self.deleteSelectedRequested.emit()
        except Exception:
            pass
    
    def hide_spinners(self):
        for name, (spin, label, btn, spin_row) in self.spinners.items():
            label.setVisible(False)
            spin_row.setVisible(False)

        self.type_combo.setVisible(False)
        self.type_label.setVisible(False)
        self.form_container.setVisible(False)
        self.title_bar.setVisible(False)
        # Hide constraints section too
        if hasattr(self, 'constraints_title_bar'):
            self.constraints_title_bar.setVisible(False)
        if hasattr(self, 'constraints_form_container'):
            self.constraints_form_container.setVisible(False)

    def set_suspended(self, suspended: bool):
        self._suspended = bool(suspended)

    def mark_ready(self):
        self._ready = True

    def get_selected_index(self):
        # Prefer current row which mirrors list order to model
        row = self.points_list.currentRow()
        if row is None or row < 0:
            return None
        if self.path is None:
            return None
        if row >= len(self.path.path_elements):
            return None
        return row
    
    def expose_element(self, element):
        if element is None:
            return
        # Reset optional dropdown
        self.optional_pop.clear()
        self.optional_display_to_key = {}
        optional_display_items = []
        # Clear any previously injected inline range sliders to prevent duplicates
        self._clear_range_sliders()
        # Helper: sanitize labels for menu display (strip HTML line breaks)
        def _menu_label_for_key(key: str) -> str:
            return Sidebar._label(key).replace('<br/>', ' ')
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
            model_attr = Sidebar.degrees_to_radians_attr_map.get(deg_name)
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
        # First hide all rows; we'll only show those that are present/selected
        for name, (control, label, btn, spin_row) in self.spinners.items():
            label.setVisible(False)
            spin_row.setVisible(False)
        # Core: position always from translation_target if Waypoint, else from element
        if isinstance(element, Waypoint):
            # Position from translation_target
            show_attr(element.translation_target, 'x_meters')
            show_attr(element.translation_target, 'y_meters')
            # Rotation degrees from rotation_target
            show_deg_attr(element.rotation_target, 'rotation_degrees')
            # Profiled rotation from rotation_target
            show_attr(element.rotation_target, 'profiled_rotation')
            # Core handoff radius (force-visible for Waypoints)
            if 'intermediate_handoff_radius_meters' in self.spinners:
                control, label, btn, spin_row = self.spinners['intermediate_handoff_radius_meters']
                val = getattr(element.translation_target, 'intermediate_handoff_radius_meters', None)
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
        elif isinstance(element, TranslationTarget):
            show_attr(element, 'x_meters')
            show_attr(element, 'y_meters')
            # Core handoff radius for TranslationTarget
            if 'intermediate_handoff_radius_meters' in self.spinners:
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

        # Path-level constraints panel
        # Build options list and show present constraints
        self.optional_pop.clear()
        self.optional_display_to_key = {}
        optional_display_items = []
        has_constraints = False
        if self.path is not None and hasattr(self.path, 'constraints') and self.path.constraints is not None:
            c = self.path.constraints
            # Translation constraints
            for name in ['final_velocity_meters_per_sec', 'max_velocity_meters_per_sec', 'max_acceleration_meters_per_sec2']:
                if hasattr(c, name):
                    val = getattr(c, name)
                    # Detect if this key has any ranged constraint entries
                    has_range = any(getattr(rc, 'key', None) == name for rc in (getattr(self.path, 'ranged_constraints', []) or []))
                    range_val = None
                    if has_range:
                        try:
                            for rc in (getattr(self.path, 'ranged_constraints', []) or []):
                                if getattr(rc, 'key', None) == name:
                                    range_val = float(getattr(rc, 'value', None))
                                    break
                        except Exception:
                            range_val = None
                    if (val is not None or has_range) and name in self.spinners:
                        control, label, btn, spin_row = self.spinners[name]
                        try:
                            control.blockSignals(True)
                            if isinstance(control, QCheckBox):
                                control.setChecked(bool(val))
                            else:
                                shown_value = float(val) if val is not None else (float(range_val) if range_val is not None else 0.0)
                                control.setValue(shown_value)
                        finally:
                            control.blockSignals(False)
                        label.setVisible(True)
                        spin_row.setVisible(True)
                        has_constraints = True
                        if name in ('max_velocity_meters_per_sec', 'max_acceleration_meters_per_sec2'):
                            self._ensure_range_slider_for_key(name, control if not isinstance(control, QCheckBox) else None, spin_row, label)
                    else:
                        display = _menu_label_for_key(name)
                        optional_display_items.append(display)
                        self.optional_display_to_key[display] = name
            # Rotation constraints (deg domain)
            for name in ['max_velocity_deg_per_sec', 'max_acceleration_deg_per_sec2']:
                if hasattr(c, name):
                    val = getattr(c, name)
                    has_range = any(getattr(rc, 'key', None) == name for rc in (getattr(self.path, 'ranged_constraints', []) or []))
                    range_val = None
                    if has_range:
                        try:
                            for rc in (getattr(self.path, 'ranged_constraints', []) or []):
                                if getattr(rc, 'key', None) == name:
                                    range_val = float(getattr(rc, 'value', None))
                                    break
                        except Exception:
                            range_val = None
                    if (val is not None or has_range) and name in self.spinners:
                        control, label, btn, spin_row = self.spinners[name]
                        try:
                            control.blockSignals(True)
                            if isinstance(control, QCheckBox):
                                control.setChecked(bool(val))
                            else:
                                shown_value = float(val) if val is not None else (float(range_val) if range_val is not None else 0.0)
                                control.setValue(shown_value)
                        finally:
                            control.blockSignals(False)
                        label.setVisible(True)
                        spin_row.setVisible(True)
                        has_constraints = True
                        self._ensure_range_slider_for_key(name, control if not isinstance(control, QCheckBox) else None, spin_row, label)
                    else:
                        display = _menu_label_for_key(name)
                        optional_display_items.append(display)
                        self.optional_display_to_key[display] = name
        # Populate the optional dropdown sorted
        if optional_display_items:
            optional_display_items = sorted(list(dict.fromkeys(optional_display_items)))
            self.optional_pop.add_items(optional_display_items)
        else:
            self.optional_pop.clear()

        # Ensure visible spin boxes reflect current config bounds if modified
        self._refresh_spinner_metadata_bounds()

    def update_current_values_only(self):
        idx = self.get_selected_index()
        if idx is None or self.path is None:
            return
        element = self.path.get_element(idx)
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
            if hasattr(element.translation_target, 'intermediate_handoff_radius_meters'):
                val = element.translation_target.intermediate_handoff_radius_meters
                if val is not None:
                    set_control_value('intermediate_handoff_radius_meters', float(val))
                else:
                    # Use default value from config if val is None
                    try:
                        default_val = self.project_manager.get_default_optional_value('intermediate_handoff_radius_meters') if self.project_manager else None
                        display_val = default_val if default_val is not None else 0.0
                        set_control_value('intermediate_handoff_radius_meters', float(display_val))
                    except Exception:
                        set_control_value('intermediate_handoff_radius_meters', 0.0)
        elif isinstance(element, TranslationTarget):
            set_control_value('x_meters', element.x_meters)
            set_control_value('y_meters', element.y_meters)
            # core handoff radius
            if hasattr(element, 'intermediate_handoff_radius_meters'):
                val = element.intermediate_handoff_radius_meters
                if val is not None:
                    set_control_value('intermediate_handoff_radius_meters', float(val))
                else:
                    # Use default value from config if val is None
                    try:
                        default_val = self.project_manager.get_default_optional_value('intermediate_handoff_radius_meters') if self.project_manager else None
                        display_val = default_val if default_val is not None else 0.0
                        set_control_value('intermediate_handoff_radius_meters', float(display_val))
                    except Exception:
                        set_control_value('intermediate_handoff_radius_meters', 0.0)
        elif isinstance(element, RotationTarget):
            if element.rotation_radians is not None:
                set_control_value('rotation_degrees', math.degrees(element.rotation_radians))
            # profiled rotation
            set_control_value('profiled_rotation', getattr(element, 'profiled_rotation', True))
            set_control_value('rotation_position_ratio', float(getattr(element, 't_ratio', 0.0)))
        # For waypoints, also reflect rotation ratio from the embedded rotation_target
        if isinstance(element, Waypoint):
            set_control_value('rotation_position_ratio', float(getattr(element.rotation_target, 't_ratio', 0.0)))

    def _refresh_spinner_metadata_bounds(self):
        # If needed in the future: dynamically adjust ranges from config. For now, keep static.
        # Hook to refresh UI on config change.
        for name, (control, label, btn, spin_row) in self.spinners.items():
            meta = self.spinner_metadata.get(name, {})
            rng = meta.get('range')
            if rng and isinstance(rng, tuple) and len(rng) == 2:
                try:
                    control.blockSignals(True)
                    if hasattr(control, 'setRange'):  # Only for spinboxes, not checkboxes
                        control.setRange(float(rng[0]), float(rng[1]))
                finally:
                    control.blockSignals(False)

    # Removed toolbox-related helpers after layout refactor

    def on_item_selected(self):
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
                if hasattr(self, 'clear_active_preview'):
                    self.clear_active_preview()
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
            
            # Expose element properties (guarded)
            try:
                self.expose_element(element)
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
            
            # Rebuild type combo (guarded)
            try:
                self._rebuild_type_combo_for_index(idx, current_type)
            except (RuntimeError, AttributeError):
                pass  # Non-critical, continue
            
            # Refresh add-element options (guarded)
            try:
                self._refresh_add_dropdown_items()
            except (RuntimeError, AttributeError):
                pass  # Non-critical, continue
            
            # Show controls (guarded)
            try:
                for widget in (self.type_label, self.type_combo, self.form_container, self.title_bar, self.constraints_title_bar, self.constraints_form_container):
                    if widget is not None:
                        widget.setVisible(True)
            except (RuntimeError, AttributeError):
                pass  # Non-critical, continue
            
            # Note: elementSelected signal intentionally not emitted here to avoid
            # re-entrant selection loops during fullscreen/resize transitions
            
        except Exception as e:
            # Fail safe: keep UI alive
            print(f"Sidebar selection error: {e}")
            self.hide_spinners()
    
    def on_attribute_removed(self, key):
        idx = self.get_selected_index()
        if idx is None or self.path is None:
            return
        
        element = self.path.get_element(idx)
        # Build description
        label_text = Sidebar._label(key).replace('<br/>', ' ')
        desc = f"Remove {label_text}" if key in ['final_velocity_meters_per_sec', 'max_velocity_meters_per_sec', 'max_acceleration_meters_per_sec2', 'max_velocity_deg_per_sec', 'max_acceleration_deg_per_sec2'] else f"Remove {label_text}"
        try:
            self.aboutToChange.emit(desc)
        except Exception:
            pass
        # Map degree-based keys for element rotation angle only
        if key == 'rotation_degrees':
            mapped = Sidebar.degrees_to_radians_attr_map[key]
            if isinstance(element, Waypoint):
                if hasattr(element.rotation_target, mapped):
                    setattr(element.rotation_target, mapped, None)
            elif hasattr(element, mapped):
                setattr(element, mapped, None)
        elif key in ['final_velocity_meters_per_sec', 'max_velocity_meters_per_sec', 'max_acceleration_meters_per_sec2', 'max_velocity_deg_per_sec', 'max_acceleration_deg_per_sec2']:
            # Removing a path-level constraint
            if hasattr(self.path, 'constraints'):
                setattr(self.path.constraints, key, None)
            # Also remove any ranged constraints for this key
            try:
                self.path.ranged_constraints = [rc for rc in (getattr(self.path, 'ranged_constraints', []) or []) if rc.key != key]
            except Exception:
                pass
        else:
            if isinstance(element, Waypoint):
                if hasattr(element.translation_target, key):
                    setattr(element.translation_target, key, None)
            elif hasattr(element, key):
                setattr(element, key, None)
        
        self.on_item_selected()
        self.modelChanged.emit()
        try:
            self.userActionOccurred.emit(desc)
        except Exception:
            pass

    def on_attribute_added(self, key):
        idx = self.get_selected_index()
        if idx is None or self.path is None:
            return
        element = self.path.get_element(idx)
        # Translate display name back to actual key if needed
        if hasattr(self, 'optional_display_to_key') and self.optional_display_to_key:
            real_key = self.optional_display_to_key.get(key, key)
        else:
            real_key = key

        # Determine default value from config if available
        cfg_default = None
        try:
            if getattr(self, 'project_manager', None) is not None:
                cfg_default = self.project_manager.get_default_optional_value(real_key)
        except Exception:
            cfg_default = None

        # Build description
        label_text = Sidebar._label(real_key).replace('<br/>', ' ')
        desc = f"Add {label_text}"
        try:
            self.aboutToChange.emit(desc)
        except Exception:
            pass

        # Path-level constraints or element attributes
        if real_key in ['final_velocity_meters_per_sec', 'max_velocity_meters_per_sec', 'max_acceleration_meters_per_sec2', 'max_velocity_deg_per_sec', 'max_acceleration_deg_per_sec2']:
            base_val = float(cfg_default) if cfg_default is not None else 0.0
            if hasattr(self.path, 'constraints'):
                setattr(self.path.constraints, real_key, base_val)
        elif real_key in Sidebar.degrees_to_radians_attr_map and real_key == 'rotation_degrees':
            mapped = Sidebar.degrees_to_radians_attr_map[real_key]
            deg_val = float(cfg_default) if cfg_default is not None else 0.0
            rad_val = math.radians(deg_val)
            if isinstance(element, Waypoint):
                if hasattr(element.rotation_target, mapped):
                    setattr(element.rotation_target, mapped, rad_val)
            elif hasattr(element, mapped):
                setattr(element, mapped, rad_val)
        else:
            base_val = float(cfg_default) if cfg_default is not None else 0.0
            if isinstance(element, Waypoint):
                if hasattr(element.translation_target, real_key):
                    setattr(element.translation_target, real_key, base_val)
            elif hasattr(element, real_key):
                setattr(element, real_key, base_val)
        # Defer UI refresh to allow QMenu to close cleanly, then rebuild dropdown
        def _refresh_and_focus_constraints(e=element):
            try:
                self.expose_element(e)
            except Exception:
                pass
        QTimer.singleShot(0, _refresh_and_focus_constraints)
        self.modelChanged.emit()
        try:
            self.userActionOccurred.emit(desc)
        except Exception:
            pass


    def on_type_change(self, value):
        idx = self.get_selected_index()
        if idx is not None and self.path is not None:
            prev = self.path.get_element(idx)
            # Only change if type is different
            prev_type = (
                ElementType.TRANSLATION if isinstance(prev, TranslationTarget)
                else ElementType.ROTATION if isinstance(prev, RotationTarget)
                else ElementType.WAYPOINT if isinstance(prev, Waypoint)
                else None
            )
            new_type = ElementType(value)
            # Prevent creating rotation at ends unless the current element already is rotation
            if new_type == ElementType.ROTATION and prev_type != ElementType.ROTATION:
                if idx == 0 or idx == len(self.path.path_elements) - 1:
                    # Disallowed; restore UI selection
                    self._rebuild_type_combo_for_index(idx, prev_type)
                    return
            if prev_type == new_type:
                return

            # Announce about-to-change for undo snapshot
            try:
                self.aboutToChange.emit(f"Change element type to {new_type.value}")
            except Exception:
                pass

            # Gather all attributes from TranslationTarget and RotationTarget
            translation_attrs = [
                'x_meters',
                'y_meters',
                'intermediate_handoff_radius_meters'
            ]
            rotation_attrs = [
                'rotation_radians',
                't_ratio',
            ]

            translation_values = {attr: getattr(prev, attr, None) for attr in translation_attrs}
            rotation_values = {attr: getattr(prev, attr, None) for attr in rotation_attrs}

            if prev_type == ElementType.WAYPOINT:
                new_elem = (
                    prev.translation_target if new_type == ElementType.TRANSLATION
                    else prev.rotation_target
                )
            elif new_type == ElementType.ROTATION:
                new_elem = RotationTarget(
                    rotation_radians=rotation_values['rotation_radians'] if rotation_values['rotation_radians'] else 0.0,
                    t_ratio=rotation_values['t_ratio'] if rotation_values['t_ratio'] is not None else 0.5,
                    profiled_rotation=True,
                )
            elif new_type == ElementType.TRANSLATION:
                # If converting from a RotationTarget, place the new translation at the
                # rotation's implied position (by t_ratio along neighbors)
                if prev_type == ElementType.ROTATION:
                    # Compute implied position from neighbors
                    prev_pos, next_pos = self._neighbor_positions_model(idx)
                    if prev_pos is not None and next_pos is not None:
                        ax, ay = prev_pos
                        bx, by = next_pos
                        try:
                            t = float(getattr(prev, 't_ratio', 0.0))
                        except Exception:
                            t = 0.0
                        x_new = ax + t * (bx - ax)
                        y_new = ay + t * (by - ay)
                    else:
                        x_new = float(translation_values['x_meters'] or 0.0)
                        y_new = float(translation_values['y_meters'] or 0.0)
                else:
                    x_new = float(translation_values['x_meters'] or 0.0)
                    y_new = float(translation_values['y_meters'] or 0.0)
                new_elem = self._create_translation_target(
                    x_new,
                    y_new,
                    translation_values['intermediate_handoff_radius_meters']
                )
            elif new_type == ElementType.WAYPOINT:
                if prev_type == ElementType.TRANSLATION:
                    # Recreate translation target to ensure handoff radius default is applied
                    tt = self._create_translation_target(
                        float(getattr(prev, 'x_meters', 0.0)),
                        float(getattr(prev, 'y_meters', 0.0)),
                        getattr(prev, 'intermediate_handoff_radius_meters', None),
                    )
                    new_elem = Waypoint(translation_target=tt)
                    # keep rotation ratio default at 0.0
                else:
                    # prev is RotationTarget; create a waypoint at the rotation's implied position
                    # translation at implied pos, rotation retains its angle and t_ratio
                    prev_pos, next_pos = self._neighbor_positions_model(idx)
                    if prev_pos is not None and next_pos is not None:
                        ax, ay = prev_pos
                        bx, by = next_pos
                        try:
                            t = float(getattr(prev, 't_ratio', 0.0))
                        except Exception:
                            t = 0.0
                        x_new = ax + t * (bx - ax)
                        y_new = ay + t * (by - ay)
                    else:
                        x_new, y_new = 0.0, 0.0
                    tt = self._create_translation_target(x_meters=x_new, y_meters=y_new)
                    new_elem = Waypoint(rotation_target=prev, translation_target=tt)

            # If we have just created or switched to a rotation element, snap its x/y to closest point on line between neighbors
            if new_type == ElementType.ROTATION:
                # Update the model first so neighbor calculations work
                self.path.path_elements[idx] = new_elem
                # Ensure rotations order by t_ratio
                self._check_and_swap_rotation_targets()
            else:
                # For non-rotation elements, just update the model
                self.path.path_elements[idx] = new_elem

            self.rebuild_points_list()
            self.select_index(idx)
            self.modelStructureChanged.emit()
            try:
                self.userActionOccurred.emit(f"Change element type to {new_type.value}")
            except Exception:
                pass

    def _rebuild_type_combo_for_index(self, idx: int, current_type: ElementType):
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

    def _neighbor_positions_model(self, idx: int) -> Tuple[Optional[Tuple[float, float]], Optional[Tuple[float, float]]]:
        if self.path is None:
            return None, None
        # prev
        prev_pos = None
        for i in range(idx - 1, -1, -1):
            e = self.path.path_elements[i]
            if isinstance(e, TranslationTarget):
                prev_pos = (float(e.x_meters), float(e.y_meters))
                break
            if isinstance(e, Waypoint):
                prev_pos = (float(e.translation_target.x_meters), float(e.translation_target.y_meters))
                break
        # next
        next_pos = None
        for i in range(idx + 1, len(self.path.path_elements)):
            e = self.path.path_elements[i]
            if isinstance(e, TranslationTarget):
                next_pos = (float(e.x_meters), float(e.y_meters))
                break
            if isinstance(e, Waypoint):
                next_pos = (float(e.translation_target.x_meters), float(e.translation_target.y_meters))
                break
        return prev_pos, next_pos

    def _project_point_between_neighbors(self, idx: int, x_m: float, y_m: float) -> Tuple[float, float]:
        prev_pos, next_pos = self._neighbor_positions_model(idx)
        if prev_pos is None or next_pos is None:
            return x_m, y_m
        ax, ay = prev_pos
        bx, by = next_pos
        dx = bx - ax
        dy = by - ay
        denom = dx * dx + dy * dy
        if denom <= 0.0:
            return x_m, y_m
        t = ((x_m - ax) * dx + (y_m - ay) * dy) / denom
        if t < 0.0:
            t = 0.0
        elif t > 1.0:
            t = 1.0
        proj_x = ax + t * dx
        proj_y = ay + t * dy
        proj_x = Sidebar._clamp_from_metadata('x_meters', proj_x)
        proj_y = Sidebar._clamp_from_metadata('y_meters', proj_y)
        return proj_x, proj_y

    def _midpoint_between_neighbors(self, idx: int) -> Optional[Tuple[float, float]]:
        prev_pos, next_pos = self._neighbor_positions_model(idx)
        if prev_pos is None or next_pos is None:
            return None
        ax, ay = prev_pos
        bx, by = next_pos
        return (ax + bx) / 2.0, (ay + by) / 2.0

    def _reproject_all_rotation_positions(self):
        # No model updates required. Canvas derives rotation positions from t_ratio.
        return

    # Removed unused getattr_deep helper for cleanliness


    def on_attribute_change(self, key, value):
        idx = self.get_selected_index()
        if idx is not None and self.path is not None:
            element = self.path.get_element(idx)
            # Build a clear description for undo/redo
            label_text = Sidebar._label(key).replace('<br/>', ' ')
            # Determine scope/entity for description
            def _entity_name(el):
                if isinstance(el, Waypoint):
                    return 'Waypoint'
                if isinstance(el, RotationTarget):
                    return 'Rotation'
                if isinstance(el, TranslationTarget):
                    return 'Translation'
                return 'Element'
            entity = _entity_name(element)
            desc: str = f"Edit {label_text}"
            # Path constraints group
            path_constraint_keys = [
                'final_velocity_meters_per_sec',
                'max_velocity_meters_per_sec',
                'max_acceleration_meters_per_sec2',
                'max_velocity_deg_per_sec',
                'max_acceleration_deg_per_sec2',
            ]
            if key in path_constraint_keys:
                desc = f"Edit Path Constraint: {label_text}"
            else:
                # Degrees-based or core element attributes
                desc = f"Edit {entity} {label_text}"
            try:
                self.aboutToChange.emit(desc)
            except Exception:
                pass
            # Handle rotation position ratio updates
            if key == 'rotation_position_ratio':
                clamped_ratio = Sidebar._clamp_from_metadata(key, float(value))
                if isinstance(element, Waypoint):
                    try:
                        element.rotation_target.t_ratio = float(clamped_ratio)
                    except Exception:
                        pass
                elif isinstance(element, RotationTarget):
                    element.t_ratio = float(clamped_ratio)
                # No re-projection needed; canvas computes from ratio
                self.modelChanged.emit()
                try:
                    self.userActionOccurred.emit(desc)
                except Exception:
                    pass
                return
            if key in Sidebar.degrees_to_radians_attr_map:
                # Degrees-mapped keys only apply to rotation_degrees on element; other deg constraints are path-level
                mapped = Sidebar.degrees_to_radians_attr_map[key]
                if key == 'rotation_degrees':
                    clamped_deg = Sidebar._clamp_from_metadata(key, float(value))
                    rad_value = math.radians(clamped_deg)
                    if isinstance(element, Waypoint):
                        if hasattr(element.rotation_target, mapped):
                            setattr(element.rotation_target, mapped, rad_value)
                    elif hasattr(element, mapped):
                        setattr(element, mapped, rad_value)
                else:
                    # Path-level rotation constraints
                    if self.path is not None and hasattr(self.path, 'constraints'):
                        clamped = Sidebar._clamp_from_metadata(key, float(value))
                        setattr(self.path.constraints, key, clamped)
            else:
                # Core element attributes or path-level constraints
                if key in path_constraint_keys:
                    if self.path is not None and hasattr(self.path, 'constraints'):
                        clamped = Sidebar._clamp_from_metadata(key, float(value))
                        # If there are ranged constraints for this key, update them and avoid setting flat constraint
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
                                            rc.value = float(clamped)
                                        except Exception:
                                            rc.value = clamped
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
                            setattr(self.path.constraints, key, clamped)
                else:
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
                            clamped = Sidebar._clamp_from_metadata(key, float(value))
                            setattr(element.translation_target, key, clamped)
                            # Reproject all rotation targets since endpoints changed
                            self._reproject_all_rotation_positions()
                    elif hasattr(element, key):
                        clamped = Sidebar._clamp_from_metadata(key, float(value))
                        setattr(element, key, clamped)
                        # If a translation target moved, reproject rotations
                        if isinstance(element, TranslationTarget) and key in ('x_meters', 'y_meters'):
                            self._reproject_all_rotation_positions()
            self.modelChanged.emit()
            try:
                self.userActionOccurred.emit(desc)
            except Exception:
                pass

    def rebuild_points_list(self):
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

                    # Use an empty QListWidgetItem and render all visuals via a row widget to avoid duplicate text painting
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

    def set_path(self, path: Path):
        self.path = path
        # Pre-check: ensure rotation elements are projected between neighbors
        self._reproject_all_rotation_positions()
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
        
        # No signal here; caller coordinates initial sync
        
    def on_points_list_reordered(self):
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
        # Apply order to model
        self.path.reorder_elements(new_order)
        # Repair any invalid placements
        self._repair_rotation_at_ends()
        # Ensure rotations are projected post-reorder
        self._reproject_all_rotation_positions()
        # Rebuild UI to reflect corrected model order
        self.rebuild_points_list()
        self.modelStructureChanged.emit()
        try:
            self.userActionOccurred.emit("Reorder elements")
        except Exception:
            pass

    # External API for other widgets
    def select_index(self, index: int):
        if index is None:
            return
        if index < 0 or index >= self.points_list.count():
            return
        # Selecting from the elements list should clear any active constraint preview
        try:
            if hasattr(self, 'clear_active_preview'):
                self.clear_active_preview()
        except Exception:
            pass
        # Defer selection to avoid re-entrancy during fullscreen/layout changes
        QTimer.singleShot(0, lambda i=index: self.points_list.setCurrentRow(i))

    def refresh_current_selection(self):
        # Re-run expose for current selection using current model values
        self.on_item_selected()

    # -------------------- Add/Remove elements --------------------
    def _refresh_add_dropdown_items(self):
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
        # Insert AFTER the selected row; if nothing selected, append at end
        current_row = self.points_list.currentRow()
        if current_row < 0:
            return len(self.path.path_elements) if self.path else 0
        return current_row + 1

    def on_add_element_selected(self, type_text: str):
        if self.path is None:
            return
        new_type = ElementType(type_text)
        insert_pos = self._insert_position_from_selection()
        # Enforce rotation cannot be at start/end
        if new_type == ElementType.ROTATION:
            if insert_pos == 0:
                insert_pos = 1
            if insert_pos == len(self.path.path_elements):
                insert_pos = max(0, len(self.path.path_elements) - 1)
            if len(self.path.path_elements) == 0:
                # Cannot add rotation as the first element; switch to translation
                new_type = ElementType.TRANSLATION
        # Build the new element with sensible defaults
        def current_pos_defaults() -> Tuple[float, float]:
            idx = self.get_selected_index()
            if idx is None or idx < 0 or idx >= len(self.path.path_elements):
                # Default to center field
                return float(FIELD_LENGTH_METERS / 2.0), float(FIELD_WIDTH_METERS / 2.0)
            e = self.path.path_elements[idx]
            if isinstance(e, TranslationTarget):
                return float(e.x_meters), float(e.y_meters)
            if isinstance(e, Waypoint):
                return float(e.translation_target.x_meters), float(e.translation_target.y_meters)
            if isinstance(e, RotationTarget):
                # For rotations, compute midpoint between neighbors
                # Sidebar-only utility for default placement decisions
                prev_pos, next_pos = self._neighbor_positions_model(idx)
                if prev_pos is None or next_pos is None:
                    return float(FIELD_LENGTH_METERS / 2.0), float(FIELD_WIDTH_METERS / 2.0)
                ax, ay = prev_pos
                bx, by = next_pos
                return (ax + bx) / 2.0, (ay + by) / 2.0
            return float(FIELD_LENGTH_METERS / 2.0), float(FIELD_WIDTH_METERS / 2.0)
        x0, y0 = current_pos_defaults()
        # Propose a nearby non-overlapping position relative to current element
        try:
            x0, y0 = self._propose_non_overlapping_position(x0, y0, new_type)
        except Exception:
            pass
        # Announce about-to-change for undo snapshot
        try:
            self.aboutToChange.emit(f"Add {new_type.value}")
        except Exception:
            pass
        if new_type == ElementType.TRANSLATION:
            new_elem = self._create_translation_target(x_meters=x0, y_meters=y0)
        elif new_type == ElementType.WAYPOINT:
            # Use helper to ensure handoff radius defaulting from config
            new_elem = self._create_waypoint(
                x_meters=x0,
                y_meters=y0,
                intermediate_handoff_radius_meters=None,
                rotation_radians=0.0,
                t_ratio=0.0,
                profiled_rotation=True,
            )
        else:  # ROTATION
            # Choose a t_ratio along the segment between nearest anchors to avoid overlap
            # Determine anchor positions relative to the insertion point
            prev_pos = None
            next_pos = None
            try:
                # Scan backward from insert_pos-1 for previous anchor
                for i in range(insert_pos - 1, -1, -1):
                    el = self.path.path_elements[i]
                    if isinstance(el, TranslationTarget):
                        prev_pos = (float(el.x_meters), float(el.y_meters))
                        break
                    if isinstance(el, Waypoint):
                        prev_pos = (float(el.translation_target.x_meters), float(el.translation_target.y_meters))
                        break
                # Scan forward from insert_pos for next anchor
                for i in range(insert_pos, len(self.path.path_elements)):
                    el = self.path.path_elements[i]
                    if isinstance(el, TranslationTarget):
                        next_pos = (float(el.x_meters), float(el.y_meters))
                        break
                    if isinstance(el, Waypoint):
                        next_pos = (float(el.translation_target.x_meters), float(el.translation_target.y_meters))
                        break
            except Exception:
                prev_pos, next_pos = None, None

            # Base t from projecting the current default position onto the segment
            def _project_t(ax: float, ay: float, bx: float, by: float, x: float, y: float) -> float:
                dx = bx - ax
                dy = by - ay
                denom = dx * dx + dy * dy
                if denom <= 0.0:
                    return 0.5
                t = ((x - ax) * dx + (y - ay) * dy) / denom
                if t < 0.0:
                    t = 0.0
                elif t > 1.0:
                    t = 1.0
                return float(t)

            # Build existing elements footprint list for overlap checks
            existing = []
            try:
                for i, el in enumerate(self.path.path_elements):
                    px, py = self._element_position_for_index(i)
                    r = self._element_bounding_radius_for_instance(el)
                    existing.append((float(px), float(py), float(r)))
            except Exception:
                pass

            # Candidate t search around t_base
            def _pos_for_t(ax: float, ay: float, bx: float, by: float, t: float) -> Tuple[float, float]:
                return ax + t * (bx - ax), ay + t * (by - ay)

            def _is_clear(x: float, y: float, new_r: float) -> bool:
                for (ox, oy, orad) in existing:
                    dx = x - ox
                    dy = y - oy
                    if dx * dx + dy * dy < (new_r + orad + 0.10) ** 2:
                        return False
                return True

            # Compute new element radius for overlap checks (rotation footprint ~= waypoint rect)
            new_r = self._element_bounding_radius_for_type(ElementType.ROTATION)
            # Default to midpoint
            t_choice = 0.5
            if prev_pos is not None and next_pos is not None:
                ax, ay = prev_pos
                bx, by = next_pos
                # Compute end exclusion based on element footprints
                try:
                    # Find the actual anchor elements to get radii
                    prev_el = None
                    next_el = None
                    for i in range(insert_pos - 1, -1, -1):
                        el = self.path.path_elements[i]
                        if isinstance(el, (TranslationTarget, Waypoint)):
                            prev_el = el
                            break
                    for i in range(insert_pos, len(self.path.path_elements)):
                        el = self.path.path_elements[i]
                        if isinstance(el, (TranslationTarget, Waypoint)):
                            next_el = el
                            break
                    prev_rad = self._element_bounding_radius_for_instance(prev_el) if prev_el is not None else 0.0
                    next_rad = self._element_bounding_radius_for_instance(next_el) if next_el is not None else 0.0
                except Exception:
                    prev_rad = 0.0
                    next_rad = 0.0

                seg_len = math.hypot(bx - ax, by - ay)
                margin = 0.10
                if seg_len > 0.0:
                    t_min = min(0.45, (new_r + prev_rad + margin) / seg_len)
                    t_max = 1.0 - min(0.45, (new_r + next_rad + margin) / seg_len)
                    if t_min > t_max:
                        # Degenerate case: fall back to center band
                        t_min, t_max = 0.25, 0.75
                else:
                    t_min, t_max = 0.05, 0.95

                # Start from selection-aware base:
                t_base = 0.5
                try:
                    sel_idx = self.get_selected_index()
                    if sel_idx is not None:
                        sel_el = self.path.get_element(sel_idx)
                        if isinstance(sel_el, RotationTarget):
                            t_base = float(getattr(sel_el, 't_ratio', 0.5))
                        else:
                            t_base = _project_t(ax, ay, bx, by, x0, y0)
                    else:
                        t_base = _project_t(ax, ay, bx, by, x0, y0)
                except Exception:
                    t_base = _project_t(ax, ay, bx, by, x0, y0)

                # Constrain to allowed interior range
                t_base = max(min(t_base, t_max), t_min)
                # Try a set of offsets around t_base
                delta = 0.08
                try:
                    if seg_len > 0:
                        delta = min(0.20, max(0.04, (new_r + margin) / seg_len * 2.0))
                except Exception:
                    pass
                offsets = [0.0, delta, -delta, 2 * delta, -2 * delta, 3 * delta, -3 * delta]
                for off in offsets:
                    t_try = max(min(t_base + off, t_max), t_min)
                    cx, cy = _pos_for_t(ax, ay, bx, by, t_try)
                    if _is_clear(cx, cy, new_r):
                        t_choice = t_try
                        break
            # Create rotation with chosen ratio
            new_elem = RotationTarget(rotation_radians=0.0, t_ratio=float(t_choice), profiled_rotation=True)
        # Insert and then fix constraints/positions
        self.path.path_elements.insert(insert_pos, new_elem)
        # If we inserted a rotation, ensure its t_ratio stays as chosen above
        if isinstance(new_elem, RotationTarget):
            try:
                new_elem.t_ratio = float(getattr(new_elem, 't_ratio', 0.5))
            except Exception:
                new_elem.t_ratio = 0.5
        # After any insert, ensure rotations are not at ends; if they are, swap inward with nearest non-rotation
        self._repair_rotation_at_ends()
        # Reproject rotation positions
        self._reproject_all_rotation_positions()
        # Rebuild UI and select newly inserted element (find its new index by identity)
        identity = id(new_elem)
        self.rebuild_points_list()
        new_index = next((i for i, e in enumerate(self.path.path_elements) if id(e) == identity), insert_pos)
        self.select_index(new_index)
        self.modelStructureChanged.emit()
        try:
            self.userActionOccurred.emit(f"Add {new_type.value}")
        except Exception:
            pass

    def _on_remove_element(self, idx_to_remove: int):
        if self.path is None:
            return
        if idx_to_remove < 0 or idx_to_remove >= len(self.path.path_elements):
            return
        # Announce about-to-change for undo snapshot
        try:
            el = self.path.path_elements[idx_to_remove]
            tname = 'Waypoint' if isinstance(el, Waypoint) else 'Rotation' if isinstance(el, RotationTarget) else 'Translation'
            self.aboutToChange.emit(f"Delete {tname}")
        except Exception:
            pass
        removed = self.path.path_elements.pop(idx_to_remove)
        # After removal, ensure we do not end with rotation at start or end
        self._repair_rotation_at_ends()
        # Reproject post-change
        self._reproject_all_rotation_positions()
        # Rebuild list and update selection sensibly
        self.rebuild_points_list()
        # Select previous index or last available
        if self.path.path_elements:
            new_sel = min(idx_to_remove, len(self.path.path_elements) - 1)
            self.select_index(new_sel)
        self.modelStructureChanged.emit()
        try:
            tname = 'Waypoint' if isinstance(removed, Waypoint) else 'Rotation' if isinstance(removed, RotationTarget) else 'Translation'
            self.userActionOccurred.emit(f"Delete {tname}")
        except Exception:
            pass

    def _repair_rotation_at_ends(self):
        if self.path is None or not self.path.path_elements:
            return
        elems = self.path.path_elements
        # Repair start
        if isinstance(elems[0], RotationTarget):
            non_rots = sum(1 for e in elems if not isinstance(e, RotationTarget))
            if non_rots > 1:
                # Swap with the first non_rot
                swap_idx = next((i for i, e in enumerate(elems) if not isinstance(e, RotationTarget)), None)
                if swap_idx is not None:
                    elems[0], elems[swap_idx] = elems[swap_idx], elems[0]
            else:
                # Convert start to Waypoint (preserve rotation, add translation at safe pos)
                old = elems[0]
                x_pos, y_pos = self._get_safe_position_for_rotation(old, elems, 0)
                elems[0] = self._create_waypoint(
                    x_meters=float(x_pos),
                    y_meters=float(y_pos),
                    rotation_radians=float(getattr(old, 'rotation_radians', 0.0)),
                    t_ratio=float(getattr(old, 't_ratio', 0.0)),
                    profiled_rotation=bool(getattr(old, 'profiled_rotation', True)),
                )
        # Repair end
        if elems and isinstance(elems[-1], RotationTarget):
            non_rots = sum(1 for e in elems if not isinstance(e, RotationTarget))
            if non_rots > 1:
                # Swap with the last non_rot
                swap_idx = next((len(elems) - 1 - i for i, e in enumerate(reversed(elems)) if not isinstance(e, RotationTarget)), None)
                if swap_idx is not None:
                    elems[-1], elems[swap_idx] = elems[swap_idx], elems[-1]
            else:
                # Convert end to Waypoint (preserve rotation, add translation at safe pos)
                old = elems[-1]
                x_pos, y_pos = self._get_safe_position_for_rotation(old, elems, len(elems) - 1)
                elems[-1] = self._create_waypoint(
                    x_meters=float(x_pos),
                    y_meters=float(y_pos),
                    rotation_radians=float(getattr(old, 'rotation_radians', 0.0)),
                    t_ratio=float(getattr(old, 't_ratio', 0.0)),
                    profiled_rotation=bool(getattr(old, 'profiled_rotation', True)),
                )

    def _get_safe_position_for_rotation(self, rotation_target, elems, index):
        """Get a safe position for converting a RotationTarget to TranslationTarget.
        
        Args:
            rotation_target: The RotationTarget being converted
            elems: List of all path elements
            index: Index of the rotation_target in elems
            
        Returns:
            Tuple[float, float]: (x_meters, y_meters) position
        """
        # Try to find a nearby anchor element with position
        for offset in [1, -1, 2, -2]:
            nearby_idx = index + offset
            if 0 <= nearby_idx < len(elems):
                elem = elems[nearby_idx]
                if isinstance(elem, TranslationTarget):
                    return elem.x_meters, elem.y_meters
                elif isinstance(elem, Waypoint):
                    return elem.translation_target.x_meters, elem.translation_target.y_meters
        
        # If no nearby position found, use a reasonable default
        # Try to get field center or a reasonable starting position
        field_center_x = 8.0  # Rough center of FRC field
        field_center_y = 4.0
        return field_center_x, field_center_y

    def _check_and_swap_rotation_targets(self):
        """Ensure rotation targets between two anchor elements (translation/waypoint) are ordered
        in the model according to their geometric order along the line segment connecting
        those anchors.  Ordering is determined by the parametric value *t* (0-1) obtained by
        projecting each rotation target onto the anchor-to-anchor line.
        """
        if self.path is None or len(self.path.path_elements) < 3:
            return

        elems = self.path.path_elements

        # Helper to get an element's position (model coordinates)
        def _pos(el):
            if isinstance(el, TranslationTarget):
                return float(el.x_meters), float(el.y_meters)
            if isinstance(el, Waypoint):
                tt = el.translation_target
                return float(tt.x_meters), float(tt.y_meters)
            # Rotation positions are implicit via t_ratio
            return None

        # Collect indices of anchor elements (translation targets and waypoints)
        anchor_indices = [i for i, e in enumerate(elems) if isinstance(e, (TranslationTarget, Waypoint))]
        if len(anchor_indices) < 2:
            return  # not enough anchors to form segments

        changed = False

        # Iterate over each consecutive anchor pair
        for seg_idx in range(len(anchor_indices) - 1):
            start_idx = anchor_indices[seg_idx]
            end_idx = anchor_indices[seg_idx + 1]

            # Gather rotation elements between anchors
            between_indices = [j for j in range(start_idx + 1, end_idx) if isinstance(elems[j], RotationTarget)]
            if len(between_indices) < 2:
                continue  # nothing to reorder for this segment

            # Desired order based on each rotation element's t_ratio
            try:
                desired_order = sorted(between_indices, key=lambda j: float(getattr(elems[j], 't_ratio', 0.0)))
            except Exception:
                desired_order = between_indices[:]

            # Current order (model list order) is just between_indices
            if between_indices == desired_order:
                continue  # already correct

            changed = True

            # Extract the rotation elements in desired order BEFORE modifying the list
            desired_elements = [elems[idx] for idx in desired_order]

            # Remove all rotation elements between anchors (iterate in reverse to keep indices valid)
            for j in reversed(between_indices):
                elems.pop(j)

            # Re-insert in correct order starting right after start_idx
            insert_at = start_idx + 1
            for el in desired_elements:
                elems.insert(insert_at, el)
                insert_at += 1

            # After first successful reorder we stop – another call will evaluate remaining segments
            break

        if changed:
            # Rebuild UI and notify listeners
            self.rebuild_points_list()
            self.modelStructureChanged.emit()

    def on_constraint_added(self, key):
        if self.path is None:
            return
        # Translate display name back to actual key if needed
        if hasattr(self, 'optional_display_to_key') and self.optional_display_to_key:
            real_key = self.optional_display_to_key.get(key, key)
        else:
            real_key = key
        # Determine default value from config if available
        cfg_default = None
        try:
            if getattr(self, 'project_manager', None) is not None:
                cfg_default = self.project_manager.get_default_optional_value(real_key)
        except Exception:
            cfg_default = None
        # Add as path-level constraint (range edited inline via RangeSlider)
        # Announce about-to-change
        label_text = Sidebar._label(real_key).replace('<br/>', ' ')
        try:
            self.aboutToChange.emit(f"Add {label_text}")
        except Exception:
            pass
        base_val = float(cfg_default) if cfg_default is not None else 0.0
        # Create or replace a ranged constraint covering the full domain immediately
        try:
            # Determine domain size
            _domain, count = self._domain_info_for_key(real_key)
            total = int(count) if int(count) > 0 else 1
            # Remove existing ranges for this key
            self.path.ranged_constraints = [rc for rc in (getattr(self.path, 'ranged_constraints', []) or []) if rc.key != real_key]
            # Append a single full-span range with the base value
            self.path.ranged_constraints.append(RangedConstraint(key=real_key, value=base_val, start_ordinal=1, end_ordinal=total))
        except Exception:
            pass
        # Ensure flat constraint is not set (avoid duplication in JSON/UI semantics)
        try:
            if hasattr(self.path, 'constraints'):
                setattr(self.path.constraints, real_key, None)
        except Exception:
            pass
        # Refresh constraints UI
        self.refresh_current_selection()
        self.modelChanged.emit()
        try:
            self.userActionOccurred.emit(f"Add {label_text}")
        except Exception:
            pass