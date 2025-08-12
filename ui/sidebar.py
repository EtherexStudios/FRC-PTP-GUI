from PySide6.QtWidgets import QWidget, QFormLayout, QLabel, QComboBox, QDoubleSpinBox, QMenu, QPushButton, QVBoxLayout, QHBoxLayout, QGroupBox, QSizePolicy, QSpacerItem, QToolBox
from PySide6.QtWidgets import QListWidget, QListWidgetItem 
from models.path_model import Path, TranslationTarget, RotationTarget, Waypoint
from PySide6.QtCore import Qt
from PySide6.QtCore import Signal, QPoint, QSize, QTimer
from enum import Enum
from typing import Optional, Tuple
import math
from PySide6.QtGui import QIcon, QGuiApplication
from ui.canvas import FIELD_LENGTH_METERS, FIELD_WIDTH_METERS
from typing import Any

class ElementType(Enum):
    TRANSLATION = 'translation'
    ROTATION = 'rotation'
    WAYPOINT = 'waypoint'

class CustomList(QListWidget):  # Changed to QListWidget    
    reordered = Signal()  # Move Signal definition here (class-level)

    def __init__(self):
        super().__init__()
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDragDropOverwriteMode(False)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QListWidget.InternalMove)  # InternalMove for flat reordering
        self.setAcceptDrops(True)

    def dropEvent(self, event):
        super().dropEvent(event)
        # Do not mutate item data or text here; items already reordered visually.
        # Emitting reordered lets the owner update the underlying model.
        self.reordered.emit()

class PopupCombobox(QWidget):
    item_selected = Signal(str)

    def __init__(self):
        super().__init__()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.button = QPushButton("Add property")
        self.button.setIcon(QIcon("assets/add_icon.png"))
        self.button.setIconSize(QSize(16,16))
        self.button.setToolTip("Add an optional property")
        self.button.setStyleSheet("QPushButton { border: none; padding: 2px 6px; }")
        self.button.setMinimumHeight(22)

        self.menu = QMenu(self)
        
        self.button.clicked.connect(self.show_menu)

        layout.addWidget(self.button)
        
    def show_menu(self):
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
        self.menu.clear()
        for item in items:
            action = self.menu.addAction(item)
            action.triggered.connect(lambda checked=False, text=item: self.item_selected.emit(text))
    def setText(self, text: str):
        self.button.setText(text)
    def setSize(self, size: QSize):
        self.button.setFixedSize(size)
        self.button.setIconSize(size)

    def setIcon(self, icon: QIcon):
        self.button.setIcon(icon)

    def setToolTip(self, text: str):
        self.button.setToolTip(text)

    def setStyleSheet(self, style: str):
        self.button.setStyleSheet(style)

    def clear(self):
        self.menu.clear()

    
class Sidebar(QWidget):
    # Emitted when a list item is selected in the sidebar
    elementSelected = Signal(int)  # index
    # Emitted when attributes are changed through the UI (positions, rotation, etc.)
    modelChanged = Signal()
    # Emitted when structure changes (reorder, type switch)
    modelStructureChanged = Signal()
    spinner_metadata = {
        # Put rotation first so it appears at the top of Core
        'rotation_degrees': {'label': 'Rotation (deg)', 'step': 1.0, 'range': (-180.0, 180.0), 'removable': False, 'section': 'core'},
        'x_meters': {'label': 'X (m)', 'step': 0.05, 'range': (0.0, float(FIELD_LENGTH_METERS)), 'removable': False, 'section': 'core'},
        'y_meters': {'label': 'Y (m)', 'step': 0.05, 'range': (0.0, float(FIELD_WIDTH_METERS)), 'removable': False, 'section': 'core'},
        # Handoff radius is a core control for TranslationTarget and Waypoint
        'intermediate_handoff_radius_meters': {'label': 'Handoff Radius (m)', 'step': 0.05, 'range': (0, 5), 'removable': False, 'section': 'core'}, 
        # Constraints (optional)
        'final_velocity_meters_per_sec': {'label': 'Final Velocity (m/s)', 'step': 0.1, 'range': (0, 15), 'removable': True, 'section': 'constraints'},
        'max_velocity_meters_per_sec': {'label': 'Max Velocity (m/s)', 'step': 0.1, 'range': (0, 15), 'removable': True, 'section': 'constraints'},
        'max_acceleration_meters_per_sec2': {'label': 'Max Acceleration (m/s²)', 'step': 0.1, 'range': (0, 20), 'removable': True, 'section': 'constraints'},
        'max_velocity_deg_per_sec': {'label': 'Max Rot Velocity (deg/s)', 'step': 1.0, 'range': (0, 720), 'removable': True, 'section': 'constraints'},
        'max_acceleration_deg_per_sec2': {'label': 'Max Rot Acceleration (deg/s²)', 'step': 1.0, 'range': (0, 7200), 'removable': True, 'section': 'constraints'}
    }        

    # Map UI spinner keys to model attribute names (for rotation fields in degrees)
    degrees_to_radians_attr_map = {
        'rotation_degrees': 'rotation_radians',
        'max_velocity_deg_per_sec': 'max_velocity_rad_per_sec',
        'max_acceleration_deg_per_sec2': 'max_acceleration_rad_per_sec2',
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

    def __init__(self, path=Path()):

        super().__init__()
        main_layout = QVBoxLayout(self)
        self.setMinimumWidth(300) # Set a minimum width for the sidebar
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        # Top section for the list label and add button in horizontal layout
        top_section = QWidget()
        top_layout = QHBoxLayout(top_section)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(6)
        
        label = QLabel("Path Elements")
        top_layout.addWidget(label)
        
        top_layout.addStretch()  # Add stretch to push button to the right
        
        self.add_element_pop = PopupCombobox()
        self.add_element_pop.setText("Add element")
        self.add_element_pop.setToolTip("Add a path element at the current selection")
        top_layout.addWidget(self.add_element_pop)
        
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
        
        self.optional_pop = PopupCombobox()
        self.optional_pop.setText("Add constraint")
        self.optional_pop.setToolTip("Add an optional constraint")
        self.optional_pop.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        title_bar_layout.addWidget(self.optional_pop)
        
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

        # Collapsible sections using QToolBox
        self.toolbox = QToolBox()
        self.toolbox.setObjectName("propertiesToolbox")
        self.toolbox.setStyleSheet(
            """
            QToolBox { background: transparent; }
            QToolBox::tab {
                font-weight: 600; padding: 6px 8px; background: #303030;
                color: #eaeaea; border: 1px solid #444; border-bottom: none;
                border-top-left-radius: 4px; border-top-right-radius: 4px; margin-left: 6px;
            }
            QToolBox::tab:selected { background: #3a3a3a; color: #ffffff; }
            QToolBox::tab:hover { background: #363636; }
            QToolBox > QWidget { background: #2a2a2a; border: 1px solid #444; }
            """
        )

        # Core section (always available): x/y and rotation (if applicable)
        self.core_page = QWidget()
        self.core_page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.core_layout = QFormLayout(self.core_page)
        self.core_layout.setLabelAlignment(Qt.AlignRight)
        self.core_layout.setVerticalSpacing(8)
        self.core_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.toolbox.addItem(self.core_page, "Core")

        # Constraints section (combined optional fields)
        self.constraints_page = QWidget()
        self.constraints_page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.constraints_layout = QFormLayout(self.constraints_page)
        self.constraints_layout.setLabelAlignment(Qt.AlignRight)
        self.constraints_layout.setVerticalSpacing(8)
        self.constraints_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.toolbox.addItem(self.constraints_page, "Constraints")

        # For remembering last-open section per element
        self._last_opened_section_by_element = {}
        self.toolbox.currentChanged.connect(self._remember_current_section)
        

        # Store label references for each spinner
        self.spinners = {}
     
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
        
        for name, data in self.spinner_metadata.items():
            spin = QDoubleSpinBox()
            spin.setSingleStep(data['step'])
            spin.setRange(*data['range'])
            spin.setValue(0)
            spin.setMinimumWidth(96) # Wider for readability
            spin.setMaximumWidth(200) # Allow expansion when sidebar is wider
            spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            label = QLabel(data['label'])
            label.setWordWrap(True)
            label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            label.setToolTip(data['label'])
            label.setMinimumWidth(120) # Ensure labels have reasonable minimum width

            # Add button next to spinner
            spin_row = QWidget()
            spin_row_layout = QHBoxLayout(spin_row)
            spin_row_layout.setContentsMargins(0, 0, 0, 0)
            spin_row_layout.setSpacing(5) # Controls space between spin and btn
            spin_row.setMinimumHeight(24)
            spin_row.setMaximumHeight(24)

            btn = QPushButton()
            btn.setIconSize(QSize(14, 14))
            btn.setFixedSize(16, 16)
            btn.setStyleSheet("QPushButton { border: none; } QPushButton:hover { background: #555; border-radius: 3px; }")

            if data.get('removable', True):
                btn.setIcon(QIcon("assets/remove_icon.png"))
                # Connect button to remove attribute
                btn.clicked.connect(lambda checked=False, n=name: self.on_attribute_removed(n))
            else:
                btn.setIcon(QIcon()) # Blank icon
                btn.setEnabled(False) # Make non-removable buttons non-interactive

            spin_row_layout.addStretch() # Push widgets to the right
            spin_row_layout.addWidget(spin)
            spin_row_layout.addWidget(btn)
            # Make the spin row expand to fill available width
            spin_row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

            # FIX: capture 'name' as a default argument in the lambda
            spin.valueChanged.connect(lambda v, n=name: self.on_attribute_change(n, v))

            # Add to the appropriate section based on metadata
            section = data.get('section', 'core')
            if section == 'core':
                self.core_layout.addRow(label, spin_row)
            elif section == 'constraints':
                self.constraints_layout.addRow(label, spin_row)
            else:
                self.core_layout.addRow(label, spin_row)
            self.spinners[name] = (spin, label, btn, spin_row)

        group_box_spinner_layout.addWidget(self.toolbox)
        # Make toolbox expand to fill available space
        self.toolbox.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Stretch to consume remaining vertical space
        group_box_spinner_layout.addStretch(1)
        # Subtle padding around the form
        self.form_container.setContentsMargins(6, 6, 6, 6)

        main_layout.addWidget(self.form_container)
        main_layout.addStretch() # Pushes all content to the top
        
        # Defer selection handling to the next event loop to avoid re-entrancy
        try:
            self.points_list.itemSelectionChanged.connect(self.on_item_selected)
        except Exception:
            pass
        self.points_list.reordered.connect(self.on_points_list_reordered)
        # Additional guard: prevent dragging rotation to start or end by enforcing after drop

        self.type_combo.currentTextChanged.connect(self.on_type_change)

        self.optional_pop.item_selected.connect(self.on_attribute_added)
        
        # Add element dropdown wiring
        self.add_element_pop.item_selected.connect(self.on_add_element_selected)
        
        self.rebuild_points_list()
    
    def hide_spinners(self):
        for name, (spin, label, btn, spin_row) in self.spinners.items():
            label.setVisible(False)
            spin_row.setVisible(False)

        self.type_combo.setVisible(False)
        self.type_label.setVisible(False)
        self.form_container.setVisible(False)
        self.title_bar.setVisible(False)

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
        # Helper: show or queue a direct attribute
        def show_attr(attr_owner, name, convert_deg=False):
            if name not in self.spinners:
                return False
            spin, label, btn, spin_row = self.spinners[name]
            if hasattr(attr_owner, name):
                value = getattr(attr_owner, name)
                if value is not None:
                    shown = math.degrees(value) if convert_deg else value
                    spin.setValue(shown)
                    label.setVisible(True)
                    spin_row.setVisible(True)
                    return True
                else:
                    display = Sidebar._label(name)
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
            spin, label, btn, spin_row = self.spinners[deg_name]
            if hasattr(owner, model_attr):
                value = getattr(owner, model_attr)
                if value is not None:
                    spin.setValue(math.degrees(value))
                    label.setVisible(True)
                    spin_row.setVisible(True)
                    return True
                else:
                    # Only force-show default for rotation_degrees; for limits queue as optional
                    if deg_name == 'rotation_degrees':
                        spin.setValue(0.0)
                        label.setVisible(True)
                        spin_row.setVisible(True)
                        return True
                    else:
                        display = Sidebar._label(deg_name)
                        optional_display_items.append(display)
                        self.optional_display_to_key[display] = deg_name
            return False

        # Decide which owners contribute which fields
        has_constraints = False
        # First hide all rows; we'll only show those that are present/selected
        for name, (spin, label, btn, spin_row) in self.spinners.items():
            label.setVisible(False)
            spin_row.setVisible(False)
        # Core: position always from translation_target if Waypoint, else from element
        if isinstance(element, Waypoint):
            # Position from translation_target
            show_attr(element.translation_target, 'x_meters')
            show_attr(element.translation_target, 'y_meters')
            # Rotation degrees from rotation_target
            show_deg_attr(element.rotation_target, 'rotation_degrees')
            # Core handoff radius (force-visible for Waypoints)
            if 'intermediate_handoff_radius_meters' in self.spinners:
                spin, label, btn, spin_row = self.spinners['intermediate_handoff_radius_meters']
                val = getattr(element.translation_target, 'intermediate_handoff_radius_meters', None)
                try:
                    spin.blockSignals(True)
                    spin.setValue(float(val) if val is not None else 0.0)
                finally:
                    spin.blockSignals(False)
                label.setVisible(True)
                spin_row.setVisible(True)
            # Constraints
            for name in ['final_velocity_meters_per_sec', 'max_velocity_meters_per_sec', 'max_acceleration_meters_per_sec2']:
                if show_attr(element.translation_target, name):
                    has_constraints = True
                else:
                    display = Sidebar._label(name)
                    optional_display_items.append(display)
                    self.optional_display_to_key[display] = name
            for name in ['max_velocity_deg_per_sec', 'max_acceleration_deg_per_sec2']:
                if show_deg_attr(element.rotation_target, name):
                    has_constraints = True
                else:
                    display = Sidebar._label(name)
                    optional_display_items.append(display)
                    self.optional_display_to_key[display] = name
        elif isinstance(element, TranslationTarget):
            show_attr(element, 'x_meters')
            show_attr(element, 'y_meters')
            # Core handoff radius for TranslationTarget
            if 'intermediate_handoff_radius_meters' in self.spinners:
                spin, label, btn, spin_row = self.spinners['intermediate_handoff_radius_meters']
                val = getattr(element, 'intermediate_handoff_radius_meters', None)
                try:
                    spin.blockSignals(True)
                    spin.setValue(float(val) if val is not None else 0.0)
                finally:
                    spin.blockSignals(False)
                label.setVisible(True)
                spin_row.setVisible(True)
            # Constraints
            for name in ['final_velocity_meters_per_sec', 'max_velocity_meters_per_sec', 'max_acceleration_meters_per_sec2']:
                if show_attr(element, name):
                    has_constraints = True
                else:
                    display = Sidebar._label(name)
                    optional_display_items.append(display)
                    self.optional_display_to_key[display] = name
        elif isinstance(element, RotationTarget):
            show_attr(element, 'x_meters')
            show_attr(element, 'y_meters')
            show_deg_attr(element, 'rotation_degrees')
            for name in ['max_velocity_deg_per_sec', 'max_acceleration_deg_per_sec2']:
                if show_deg_attr(element, name):
                    has_constraints = True
                else:
                    display = Sidebar._label(name)
                    optional_display_items.append(display)
                    self.optional_display_to_key[display] = name

        # Populate the optional dropdown sorted
        if optional_display_items:
            optional_display_items = sorted(list(dict.fromkeys(optional_display_items)))
            self.optional_pop.add_items(optional_display_items)
        else:
            self.optional_pop.clear()

        # Rebuild tabs to reflect whether constraints have any content
        self._rebuild_toolbox_pages(has_constraints)
        QTimer.singleShot(0, lambda e=element: self._restore_last_opened_section(e))

        # Rotation already first in Core via metadata order; no row surgery required
        # Ensure visible spin boxes reflect current config bounds if modified
        self._refresh_spinner_metadata_bounds()

    def update_current_values_only(self):
        idx = self.get_selected_index()
        if idx is None or self.path is None:
            return
        element = self.path.get_element(idx)
        # Helper to set a spin value safely
        def set_spin_value(name: str, value: float):
            if name not in self.spinners:
                return
            spin, _, _, _ = self.spinners[name]
            if not spin.isVisible():
                return
            try:
                spin.blockSignals(True)
                spin.setValue(value)
            finally:
                spin.blockSignals(False)

        # Update position
        if isinstance(element, Waypoint):
            set_spin_value('x_meters', element.translation_target.x_meters)
            set_spin_value('y_meters', element.translation_target.y_meters)
            # rotation degrees
            if element.rotation_target.rotation_radians is not None:
                set_spin_value('rotation_degrees', math.degrees(element.rotation_target.rotation_radians))
            # core handoff radius
            if hasattr(element.translation_target, 'intermediate_handoff_radius_meters') and element.translation_target.intermediate_handoff_radius_meters is not None:
                set_spin_value('intermediate_handoff_radius_meters', float(element.translation_target.intermediate_handoff_radius_meters))
        elif isinstance(element, TranslationTarget):
            set_spin_value('x_meters', element.x_meters)
            set_spin_value('y_meters', element.y_meters)
            # core handoff radius
            if hasattr(element, 'intermediate_handoff_radius_meters') and element.intermediate_handoff_radius_meters is not None:
                set_spin_value('intermediate_handoff_radius_meters', float(element.intermediate_handoff_radius_meters))
        elif isinstance(element, RotationTarget):
            set_spin_value('x_meters', element.x_meters)
            set_spin_value('y_meters', element.y_meters)
            if element.rotation_radians is not None:
                set_spin_value('rotation_degrees', math.degrees(element.rotation_radians))

    def _refresh_spinner_metadata_bounds(self):
        # If needed in the future: dynamically adjust ranges from config. For now, keep static.
        # Hook to refresh UI on config change.
        for name, (spin, label, btn, spin_row) in self.spinners.items():
            meta = self.spinner_metadata.get(name, {})
            rng = meta.get('range')
            if rng and isinstance(rng, tuple) and len(rng) == 2:
                try:
                    spin.blockSignals(True)
                    spin.setRange(float(rng[0]), float(rng[1]))
                finally:
                    spin.blockSignals(False)

    def _refresh_toolbox_sections(self, element):
        # Determine if constraints section has any visible rows
        def layout_has_visible_rows(layout: QFormLayout) -> bool:
            for i in range(layout.rowCount()):
                field_item = layout.itemAt(i, QFormLayout.FieldRole)
                if field_item:
                    w = field_item.widget()
                    if w and w.isVisible():
                        return True
            return False

        show_constraints = layout_has_visible_rows(self.constraints_layout)
        self._set_toolbox_enabled(show_constraints)

    def _rebuild_toolbox_pages(self, show_constraints: bool):
        self.toolbox.blockSignals(True)
        try:
            self.toolbox.setItemEnabled(1, show_constraints)  # Index 1: Constraints
            self.constraints_page.setVisible(show_constraints)
            if self.toolbox.currentIndex() > 0 and not self.toolbox.widget(self.toolbox.currentIndex()).isVisible():
                self.toolbox.setCurrentIndex(0)
        finally:
            self.toolbox.blockSignals(False)

    def _set_toolbox_enabled(self, show_constraints: bool):
        # Show/hide pages without removing them to avoid deleting widgets
        self.toolbox.blockSignals(True)
        try:
            self.core_page.setVisible(True)
            self.constraints_page.setVisible(bool(show_constraints))
            # If current page hidden, jump to Core
            cur = self.toolbox.currentIndex()
            current_widget = self.toolbox.widget(cur) if cur >= 0 else None
            if current_widget is not None and not current_widget.isVisible():
                self.toolbox.setCurrentIndex(0)
        finally:
            self.toolbox.blockSignals(False)

    def _remember_current_section(self, index: int):
        # Remember by tab text for current element
        element_index = self.get_selected_index()
        if element_index is None or self.path is None:
            return
        if index < 0 or index >= self.toolbox.count():
            return
        key = self.toolbox.itemText(index)
        try:
            element = self.path.get_element(element_index)
            self._last_opened_section_by_element[id(element)] = key
        except Exception:
            pass

    def _restore_last_opened_section(self, element):
        desired = self._last_opened_section_by_element.get(id(element))
        if desired is None:
            self.toolbox.setCurrentIndex(0)
            return
        for i in range(self.toolbox.count()):
            if self.toolbox.itemText(i) == desired:
                self.toolbox.setCurrentIndex(i)
                return
        # Fallback
        self.toolbox.setCurrentIndex(0)

    def on_item_selected(self):
        try:
            # Guard against re-entrancy and layout instability
            if getattr(self, '_suspended', False) or not getattr(self, '_ready', False):
                return
            
            idx = self.get_selected_index()
            if idx is None or self.path is None:
                self.hide_spinners()
                return
            
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
                for widget in (self.type_label, self.type_combo, self.form_container, self.title_bar):
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
        # Map degree-based keys to model attributes as needed
        if key in Sidebar.degrees_to_radians_attr_map:
            mapped = Sidebar.degrees_to_radians_attr_map[key]
            if isinstance(element, Waypoint):
                if hasattr(element.rotation_target, mapped):
                    setattr(element.rotation_target, mapped, None)
            elif hasattr(element, mapped):
                setattr(element, mapped, None)
        else:
            if isinstance(element, Waypoint):
                if hasattr(element.translation_target, key):
                    setattr(element.translation_target, key, None)
                if hasattr(element.rotation_target, key):
                    setattr(element.rotation_target, key, None)
            elif hasattr(element, key):
                setattr(element, key, None)
        
        self.on_item_selected()
        self.modelChanged.emit()

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

        if real_key in Sidebar.degrees_to_radians_attr_map:
            mapped = Sidebar.degrees_to_radians_attr_map[real_key]
            # Default from config is in degrees; convert to radians
            if cfg_default is None:
                deg_val = 0.0
            else:
                deg_val = float(cfg_default)
            rad_val = math.radians(deg_val)
            if isinstance(element, Waypoint):
                if hasattr(element.rotation_target, mapped):
                    setattr(element.rotation_target, mapped, rad_val)
            elif hasattr(element, mapped):
                setattr(element, mapped, rad_val)
        else:
            # Distance/velocity defaults use meters or m/s units
            if cfg_default is None:
                base_val = 0.0
            else:
                base_val = float(cfg_default)
            if isinstance(element, Waypoint):
                if hasattr(element.translation_target, real_key):
                    setattr(element.translation_target, real_key, base_val)
                if hasattr(element.rotation_target, real_key):
                    setattr(element.rotation_target, real_key, base_val)
            elif hasattr(element, real_key):
                setattr(element, real_key, base_val)
        # Defer UI refresh to allow QMenu to close cleanly, then rebuild dropdown
        def _refresh_and_focus_constraints(e=element):
            try:
                self.expose_element(e)
                # Auto-expand the Constraints section if it's available
                # Index 1 is Constraints
                if hasattr(self, 'constraints_page'):
                    self.toolbox.setCurrentIndex(1)
            except Exception:
                pass
        QTimer.singleShot(0, _refresh_and_focus_constraints)
        self.modelChanged.emit()


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

            # Gather all attributes from TranslationTarget and RotationTarget
            translation_attrs = [
                'x_meters',
                'y_meters',
                'final_velocity_meters_per_sec',
                'max_velocity_meters_per_sec',
                'max_acceleration_meters_per_sec2',
                'intermediate_handoff_radius_meters'
            ]
            rotation_attrs = [
                'rotation_radians',
                'x_meters',
                'y_meters',
                'max_velocity_rad_per_sec',
                'max_acceleration_rad_per_sec2'
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
                    rotation_values['rotation_radians'] if rotation_values['rotation_radians'] else 0,
                    rotation_values['x_meters'] if rotation_values['x_meters'] else 0.0,
                    rotation_values['y_meters'] if rotation_values['y_meters'] else 0.0,
                    rotation_values['max_velocity_rad_per_sec'],
                    rotation_values['max_acceleration_rad_per_sec2'],
                )
            elif new_type == ElementType.TRANSLATION:
                new_elem = TranslationTarget(
                    translation_values['x_meters'] if translation_values['x_meters'] else 0.0,
                    translation_values['y_meters'] if translation_values['y_meters'] else 0.0,
                    translation_values['final_velocity_meters_per_sec'],
                    translation_values['max_velocity_meters_per_sec'],
                    translation_values['max_acceleration_meters_per_sec2'],
                    translation_values['intermediate_handoff_radius_meters']
                )
            elif new_type == ElementType.WAYPOINT:
                if prev_type == ElementType.TRANSLATION:
                    new_elem = Waypoint(translation_target=prev)
                    new_elem.rotation_target.x_meters = new_elem.translation_target.x_meters
                    new_elem.rotation_target.y_meters = new_elem.translation_target.y_meters
                else:
                    new_elem = Waypoint(rotation_target=prev)
                    new_elem.translation_target.x_meters = new_elem.rotation_target.x_meters
                    new_elem.translation_target.y_meters = new_elem.rotation_target.y_meters

            # If we have just created or switched to a rotation element, snap its x/y to closest point on line between neighbors
            if new_type == ElementType.ROTATION:
                # Update the model first so _project_point_between_neighbors can find the correct neighbors
                self.path.path_elements[idx] = new_elem
                # Project the current position onto the line between neighbors
                proj_x, proj_y = self._project_point_between_neighbors(idx, new_elem.x_meters, new_elem.y_meters)
                new_elem.x_meters = proj_x
                new_elem.y_meters = proj_y
                # Update the model again with the corrected coordinates
                self.path.path_elements[idx] = new_elem
                
                # Check if we need to swap rotation targets to maintain visual order
                self._check_and_swap_rotation_targets()
            else:
                # For non-rotation elements, just update the model
                self.path.path_elements[idx] = new_elem

            self.rebuild_points_list()
            self.select_index(idx)
            self.modelStructureChanged.emit()

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
        if self.path is None:
            return
        for idx, e in enumerate(self.path.path_elements):
            if isinstance(e, RotationTarget):
                proj_x, proj_y = self._project_point_between_neighbors(idx, e.x_meters, e.y_meters)
                e.x_meters, e.y_meters = proj_x, proj_y

    # Removed unused getattr_deep helper for cleanliness


    def on_attribute_change(self, key, value):
        idx = self.get_selected_index()
        if idx is not None and self.path is not None:
            element = self.path.get_element(idx)
            if key in Sidebar.degrees_to_radians_attr_map:
                mapped = Sidebar.degrees_to_radians_attr_map[key]
                # Clamp using degrees-domain metadata before converting
                clamped_deg = Sidebar._clamp_from_metadata(key, float(value))
                rad_value = math.radians(clamped_deg)
                if isinstance(element, Waypoint):
                    if hasattr(element.rotation_target, mapped):
                        setattr(element.rotation_target, mapped, rad_value)
                elif hasattr(element, mapped):
                    setattr(element, mapped, rad_value)
            else:
                if isinstance(element, Waypoint):
                    if hasattr(element.translation_target, key):
                        clamped = Sidebar._clamp_from_metadata(key, float(value))
                        setattr(element.translation_target, key, clamped)
                        # Reproject all rotation targets since endpoints changed
                        self._reproject_all_rotation_positions()
                    if hasattr(element.rotation_target, key):
                        clamped = Sidebar._clamp_from_metadata(key, float(value))
                        setattr(element.rotation_target, key, clamped)
                elif hasattr(element, key):
                    if isinstance(element, RotationTarget) and key in ('x_meters', 'y_meters'):
                        # Project rotation element onto segment between neighbors; adjust both x and y
                        desired_x = float(value) if key == 'x_meters' else float(element.x_meters)
                        desired_y = float(value) if key == 'y_meters' else float(element.y_meters)
                        desired_x = Sidebar._clamp_from_metadata('x_meters', desired_x)
                        desired_y = Sidebar._clamp_from_metadata('y_meters', desired_y)
                        proj_x, proj_y = self._project_point_between_neighbors(idx, desired_x, desired_y)
                        element.x_meters = proj_x
                        element.y_meters = proj_y
                        # Keep the UI in sync immediately
                        self.update_current_values_only()
                    else:
                        clamped = Sidebar._clamp_from_metadata(key, float(value))
                        setattr(element, key, clamped)
                        # If a translation target moved, reproject rotations
                        if isinstance(element, TranslationTarget) and key in ('x_meters', 'y_meters'):
                            self._reproject_all_rotation_positions()
            self.modelChanged.emit()

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

    # External API for other widgets
    def select_index(self, index: int):
        if index is None:
            return
        if index < 0 or index >= self.points_list.count():
            return
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
                return float(e.x_meters), float(e.y_meters)
            return float(FIELD_LENGTH_METERS / 2.0), float(FIELD_WIDTH_METERS / 2.0)
        x0, y0 = current_pos_defaults()
        if new_type == ElementType.TRANSLATION:
            new_elem = TranslationTarget(x_meters=x0, y_meters=y0)
        elif new_type == ElementType.WAYPOINT:
            tt = TranslationTarget(x_meters=x0, y_meters=y0)
            rt = RotationTarget(rotation_radians=0.0, x_meters=x0, y_meters=y0)
            new_elem = Waypoint(translation_target=tt, rotation_target=rt)
        else:  # ROTATION
            new_elem = RotationTarget(rotation_radians=0.0, x_meters=x0, y_meters=y0)
        # Insert and then fix constraints/positions
        self.path.path_elements.insert(insert_pos, new_elem)
        # If we inserted a rotation, snap it to midpoint between neighbors
        if isinstance(new_elem, RotationTarget):
            mid = self._midpoint_between_neighbors(insert_pos)
            if mid is not None:
                mx, my = mid
                new_elem.x_meters = mx
                new_elem.y_meters = my
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

    def _on_remove_element(self, idx_to_remove: int):
        if self.path is None:
            return
        if idx_to_remove < 0 or idx_to_remove >= len(self.path.path_elements):
            return
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
                # Convert start to TranslationTarget
                old = elems[0]
                elems[0] = TranslationTarget(
                    x_meters=old.x_meters,
                    y_meters=old.y_meters
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
                # Convert end to TranslationTarget
                old = elems[-1]
                elems[-1] = TranslationTarget(
                    x_meters=old.x_meters,
                    y_meters=old.y_meters
                )

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
            if isinstance(el, RotationTarget):
                return float(el.x_meters), float(el.y_meters)
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

            # Anchor positions and vector
            ax, ay = _pos(elems[start_idx])
            bx, by = _pos(elems[end_idx])
            dx = bx - ax
            dy = by - ay
            denom = dx * dx + dy * dy
            if denom == 0:
                continue  # degenerate segment – skip

            # Compute parametric t for each rotation (projection onto AB, clamped to [0,1])
            rot_t_pairs = []  # (index, t)
            for j in between_indices:
                rx, ry = _pos(elems[j])
                t = ((rx - ax) * dx + (ry - ay) * dy) / denom
                rot_t_pairs.append((j, t))

            # Desired order based on increasing t
            rot_t_pairs.sort(key=lambda p: p[1])
            desired_order = [idx for idx, _ in rot_t_pairs]

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