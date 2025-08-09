from PySide6.QtWidgets import QWidget, QFormLayout, QLabel, QComboBox, QDoubleSpinBox, QMenu, QPushButton, QVBoxLayout, QHBoxLayout, QGroupBox, QSizePolicy, QSpacerItem, QToolBox
from PySide6.QtWidgets import QListWidget, QListWidgetItem 
from models.path_model import Path, TranslationTarget, RotationTarget, Waypoint
from PySide6.QtCore import Qt
from PySide6.QtCore import Signal, QPoint, QSize, QTimer
from enum import Enum
from typing import Optional, Tuple
import math
from PySide6.QtGui import QIcon
from ui.canvas import FIELD_LENGTH_METERS, FIELD_WIDTH_METERS

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

        self.reordered.emit()

        for i in range(self.count()):  # Changed to count() for QListWidget
            item = self.item(i)  # Changed to item(i)
            item.setData(Qt.UserRole, i)  # No column
            item.setText(f"{item.text().split()[0]}")

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
        self.menu.popup(self.button.mapToGlobal(QPoint(0, self.button.height())))

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
        'final_velocity_meters_per_sec': {'label': 'Final Velocity (m/s)', 'step': 0.1, 'range': (0, 15), 'removable': True, 'section': 'translation_limits'},
        'max_velocity_meters_per_sec': {'label': 'Max Velocity (m/s)', 'step': 0.1, 'range': (0, 15), 'removable': True, 'section': 'translation_limits'},
        'max_acceleration_meters_per_sec2': {'label': 'Max Acceleration (m/s²)', 'step': 0.1, 'range': (0, 20), 'removable': True, 'section': 'translation_limits'},
        'intermediate_handoff_radius_meters': {'label': 'Handoff Radius (m)', 'step': 0.05, 'range': (0, 5), 'removable': True, 'section': 'translation_limits'}, 
        'max_velocity_deg_per_sec': {'label': 'Max Rot Velocity (deg/s)', 'step': 1.0, 'range': (0, 720), 'removable': True, 'section': 'rotation_limits'},
        'max_acceleration_deg_per_sec2': {'label': 'Max Rot Acceleration (deg/s²)', 'step': 1.0, 'range': (0, 7200), 'removable': True, 'section': 'rotation_limits'}
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

        # Top section for the list label
        label = QLabel("Path Elements")
        main_layout.addWidget(label)

        self.path = path
        
        self.points_list = CustomList()
        main_layout.addWidget(self.points_list)

        main_layout.addSpacing(10) # Add space between list and groupbox

        # Create a container for the title bar to style it
        self.title_bar = QWidget()
        self.title_bar.setObjectName("titleBar")
        self.title_bar.setStyleSheet("""
            QWidget#titleBar {
                background-color: #404040; /* A more distinct grey */
                border: 1px solid #666666;
                border-radius: 5px;
            }
        """)
        title_bar_layout = QHBoxLayout(self.title_bar)
        title_bar_layout.setContentsMargins(10, 0, 10, 0) # Remove vertical margins
        title_bar_layout.setSpacing(0)
        
        title_label = QLabel("Element Properties")
        title_label.setStyleSheet("""
            font-size: 14px; 
            font-weight: bold;
            background: transparent;
            border: none;
            padding: 4px 0;
        """)
        title_bar_layout.addWidget(title_label)
        
        title_bar_layout.addStretch()
        
        self.optional_pop = PopupCombobox()
        self.optional_pop.setText("Add property")
        title_bar_layout.addWidget(self.optional_pop)
        
        main_layout.addWidget(self.title_bar)
        
        # Form section for editable properties
        self.form_container = QGroupBox()
        self.form_container.setStyleSheet("""
            QGroupBox {
                background-color: #404040; /* A more distinct grey */
                border: 1px solid #666666;
                border-radius: 5px;
            }
        """)
        
        # Main layout for the group box
        group_box_spinner_layout = QVBoxLayout(self.form_container)
        group_box_spinner_layout.setContentsMargins(6, 6, 6, 6)

        # Collapsible sections using QToolBox
        self.toolbox = QToolBox()
        self.toolbox.setObjectName("propertiesToolbox")
        self.toolbox.setStyleSheet(
            """
            QToolBox {
                background: transparent;
            }
            QToolBox::tab {
                font-weight: 600;
                padding: 6px 8px;
                background: #3a3a3a;
                color: #f0f0f0;
                border: 0px;
                border-bottom: 1px solid #ffffff; /* divider under every tab */
            }
            QToolBox::tab:selected {
                background: #4a4a4a;
                color: #ffffff;
                border-bottom: 1px solid #ffffff; /* keep divider when expanded */
            }
            QToolBox::tab:!selected {
                background: #3a3a3a;
                color: #dddddd;
                border-bottom: 1px solid #ffffff;
            }
            /* Ensure a visible white divider between the selected tab and its page */
            QToolBox > QWidget {
                background: #404040;
                border-top: 1px solid #ffffff;
            }
            """
        )

        # Core section (always available): x/y and rotation (if applicable)
        self.core_page = QWidget()
        self.core_layout = QFormLayout(self.core_page)
        self.core_layout.setLabelAlignment(Qt.AlignRight)
        self.core_layout.setVerticalSpacing(6)
        self.core_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.toolbox.addItem(self.core_page, "Core")

        # Translation Limits section (optional fields)
        self.translation_limits_page = QWidget()
        self.translation_limits_layout = QFormLayout(self.translation_limits_page)
        self.translation_limits_layout.setLabelAlignment(Qt.AlignRight)
        self.translation_limits_layout.setVerticalSpacing(6)
        self.translation_limits_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.toolbox.addItem(self.translation_limits_page, "Translation Limits")

        # Rotation Limits section (optional fields)
        self.rotation_limits_page = QWidget()
        self.rotation_limits_layout = QFormLayout(self.rotation_limits_page)
        self.rotation_limits_layout.setLabelAlignment(Qt.AlignRight)
        self.rotation_limits_layout.setVerticalSpacing(6)
        self.rotation_limits_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.toolbox.addItem(self.rotation_limits_page, "Rotation Limits")

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
            spin.setMinimumWidth(72) # Wider for readability
            spin.setMaximumWidth(90)
            label = QLabel(data['label'])
            label.setWordWrap(True)
            label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            label.setToolTip(data['label'])

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

            # FIX: capture 'name' as a default argument in the lambda
            spin.valueChanged.connect(lambda v, n=name: self.on_attribute_change(n, v))

            # Add to the appropriate section based on metadata
            section = data.get('section', 'core')
            if section == 'core':
                self.core_layout.addRow(label, spin_row)
            elif section == 'translation_limits':
                self.translation_limits_layout.addRow(label, spin_row)
            elif section == 'rotation_limits':
                self.rotation_limits_layout.addRow(label, spin_row)
            else:
                self.core_layout.addRow(label, spin_row)
            self.spinners[name] = (spin, label, btn, spin_row)

        group_box_spinner_layout.addWidget(self.toolbox)
        # Subtle padding around the form
        self.form_container.setContentsMargins(6, 6, 6, 6)

        main_layout.addWidget(self.form_container)
        main_layout.addStretch() # Pushes all content to the top
        
        self.points_list.itemSelectionChanged.connect(self.on_item_selected)
        self.points_list.reordered.connect(self.on_points_list_reordered)
        # Additional guard: prevent dragging rotation to start or end by enforcing after drop

        self.type_combo.currentTextChanged.connect(self.on_type_change)

        self.optional_pop.item_selected.connect(self.on_attribute_added)
        
        self.rebuild_points_list()
    
    def hide_spinners(self):
        for name, (spin, label, btn, spin_row) in self.spinners.items():
            label.setVisible(False)
            spin_row.setVisible(False)

        self.type_combo.setVisible(False)
        self.type_label.setVisible(False)
        self.form_container.setVisible(False)
        self.title_bar.setVisible(False)

    def get_selected_index(self):
        selected = self.points_list.selectedItems()
        if selected:
            return selected[0].data(Qt.UserRole)
        else:
            return None
    
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
        has_translation_limits = False
        has_rotation_limits = False
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
            # Limits
            for name in ['final_velocity_meters_per_sec', 'max_velocity_meters_per_sec', 'max_acceleration_meters_per_sec2', 'intermediate_handoff_radius_meters']:
                if show_attr(element.translation_target, name):
                    has_translation_limits = True
            for name in ['max_velocity_deg_per_sec', 'max_acceleration_deg_per_sec2']:
                if show_deg_attr(element.rotation_target, name):
                    has_rotation_limits = True
        elif isinstance(element, TranslationTarget):
            show_attr(element, 'x_meters')
            show_attr(element, 'y_meters')
            for name in ['final_velocity_meters_per_sec', 'max_velocity_meters_per_sec', 'max_acceleration_meters_per_sec2', 'intermediate_handoff_radius_meters']:
                if show_attr(element, name):
                    has_translation_limits = True
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
                    has_rotation_limits = True

        # Populate the optional dropdown sorted
        if optional_display_items:
            optional_display_items = sorted(list(dict.fromkeys(optional_display_items)))
            self.optional_pop.add_items(optional_display_items)
        else:
            self.optional_pop.clear()

        # Rebuild tabs to reflect which sections actually have content
        self._rebuild_toolbox_pages(has_translation_limits, has_rotation_limits)
        QTimer.singleShot(0, lambda e=element: self._restore_last_opened_section(e))

        # Rotation already first in Core via metadata order; no row surgery required

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
        elif isinstance(element, TranslationTarget):
            set_spin_value('x_meters', element.x_meters)
            set_spin_value('y_meters', element.y_meters)
        elif isinstance(element, RotationTarget):
            set_spin_value('x_meters', element.x_meters)
            set_spin_value('y_meters', element.y_meters)
            if element.rotation_radians is not None:
                set_spin_value('rotation_degrees', math.degrees(element.rotation_radians))

    def _refresh_toolbox_sections(self, element):
        # Determine if translation/rotation limits have any visible rows
        def layout_has_visible_rows(layout: QFormLayout) -> bool:
            for i in range(layout.rowCount()):
                field_item = layout.itemAt(i, QFormLayout.FieldRole)
                if field_item:
                    w = field_item.widget()
                    if w and w.isVisible():
                        return True
            return False

        show_translation = layout_has_visible_rows(self.translation_limits_layout)
        show_rotation = layout_has_visible_rows(self.rotation_limits_layout)
        self._set_toolbox_enabled(show_translation, show_rotation)

    def _rebuild_toolbox_pages(self, show_translation: bool, show_rotation: bool):
        # Rebuild toolbox items to exactly match what should be visible
        self.toolbox.blockSignals(True)
        try:
            current_text = self.toolbox.itemText(self.toolbox.currentIndex()) if self.toolbox.count() > 0 else None
            while self.toolbox.count() > 0:
                self.toolbox.removeItem(0)
            self.toolbox.addItem(self.core_page, "Core")
            if show_translation:
                self.toolbox.addItem(self.translation_limits_page, "Translation Limits")
            if show_rotation:
                self.toolbox.addItem(self.rotation_limits_page, "Rotation Limits")
            # Restore previous tab if possible
            if current_text is not None:
                for i in range(self.toolbox.count()):
                    if self.toolbox.itemText(i) == current_text:
                        self.toolbox.setCurrentIndex(i)
                        break
            # Ensure a valid tab is selected
            if self.toolbox.currentIndex() < 0 and self.toolbox.count() > 0:
                self.toolbox.setCurrentIndex(0)
        finally:
            self.toolbox.blockSignals(False)

    def _set_toolbox_enabled(self, show_translation: bool, show_rotation: bool):
        # Show/hide pages without removing them to avoid deleting widgets
        self.toolbox.blockSignals(True)
        try:
            self.core_page.setVisible(True)
            self.translation_limits_page.setVisible(bool(show_translation))
            self.rotation_limits_page.setVisible(bool(show_rotation))
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
            idx = self.get_selected_index()
            if idx is None or self.path is None:
                self.hide_spinners()
                return
            element = self.path.get_element(idx)
            self.optional_pop.clear()
            self.hide_spinners()

            self.expose_element(element)
            # expose combo box
            if isinstance(element, TranslationTarget):
                current_type = ElementType.TRANSLATION
            elif isinstance(element, RotationTarget):
                current_type = ElementType.ROTATION
            else:
                current_type = ElementType.WAYPOINT
            self._rebuild_type_combo_for_index(idx, current_type)
            
            self.type_label.setVisible(True)
            self.type_combo.setVisible(True)
            self.form_container.setVisible(True)
            self.title_bar.setVisible(True)
            # Emit selection for outside listeners (e.g., canvas) after UI is ready
            QTimer.singleShot(0, lambda i=idx: self.elementSelected.emit(i))
        except Exception as e:
            # Fail safe: keep UI alive
            print("Sidebar on_item_selected error:", e)
    
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

        if real_key in Sidebar.degrees_to_radians_attr_map:
            mapped = Sidebar.degrees_to_radians_attr_map[real_key]
            # Initialize with 0 rad (0 deg)
            if isinstance(element, Waypoint):
                if hasattr(element.rotation_target, mapped):
                    setattr(element.rotation_target, mapped, 0.0)
            elif hasattr(element, mapped):
                setattr(element, mapped, 0.0)
        else:
            if (isinstance(element, Waypoint)):
                if hasattr(element.translation_target, real_key):
                    setattr(element.translation_target, real_key, 0)
                if hasattr(element.rotation_target, real_key):
                    setattr(element.rotation_target, real_key, 0)
            elif hasattr(element, real_key):
                setattr(element, real_key, 0)
        # Defer UI refresh to allow QMenu to close cleanly, then rebuild dropdown
        QTimer.singleShot(0, lambda e=element: self.expose_element(e))
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

            # If we have just created or switched to a rotation element, snap its x/y to midpoint
            if new_type == ElementType.ROTATION:
                mid = self._midpoint_between_neighbors(idx)
                if mid is not None:
                    mx, my = mid
                    new_elem.x_meters = mx
                    new_elem.y_meters = my

            self.path.path_elements[idx] = new_elem
            item = self.points_list.currentItem()
            item.setText(f"{new_type.value}")
            self.on_item_selected()  # Refresh fields
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
        self.points_list.clear()
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
                    
                item = QListWidgetItem(name)  # Changed to QListWidgetItem, no []
                item.setData(Qt.UserRole, i)  # No column 0
                self.points_list.addItem(item)  # Changed to addItem

    def set_path(self, path: Path):
        self.path = path
        # Pre-check: ensure rotation elements are projected between neighbors
        self._reproject_all_rotation_positions()
        self.rebuild_points_list()
        # No signal here; caller coordinates initial sync
        
    def on_points_list_reordered(self):
        if self.path is None:
            return
        # New order by original indices from UI items
        new_order = [self.points_list.item(i).data(Qt.UserRole) for i in range(self.points_list.count())]
        corrected = list(new_order)
        # Prevent rotation at start
        if corrected:
            first_idx = corrected[0]
            if isinstance(self.path.path_elements[first_idx], RotationTarget):
                # Find first non-rotation to place at start
                for j in range(1, len(corrected)):
                    if not isinstance(self.path.path_elements[corrected[j]], RotationTarget):
                        corrected[0], corrected[j] = corrected[j], corrected[0]
                        break
        # Prevent rotation at end
        if corrected:
            last_idx = corrected[-1]
            if isinstance(self.path.path_elements[last_idx], RotationTarget):
                for j in range(len(corrected) - 2, -1, -1):
                    if not isinstance(self.path.path_elements[corrected[j]], RotationTarget):
                        corrected[-1], corrected[j] = corrected[j], corrected[-1]
                        break
        # Apply corrected order to model
        self.path.reorder_elements(corrected)
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
        self.points_list.setCurrentRow(index)
        self.on_item_selected()

    def refresh_current_selection(self):
        # Re-run expose for current selection using current model values
        self.on_item_selected()