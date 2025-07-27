from PySide6.QtWidgets import QWidget, QFormLayout, QLabel, QComboBox, QDoubleSpinBox, QMenu, QPushButton, QVBoxLayout, QHBoxLayout, QGroupBox, QSizePolicy, QSpacerItem
from PySide6.QtWidgets import QListWidget, QListWidgetItem 
from models.path_model import Path, TranslationTarget, RotationTarget, Waypoint
from PySide6.QtCore import Qt
from PySide6.QtCore import Signal, QPoint, QSize
from enum import Enum
from PySide6.QtGui import QIcon

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
        
        self.button = QPushButton()
        self.button.setIcon(QIcon("assets/add_icon.png"))
        self.button.setIconSize(QSize(18,18))
        self.button.setToolTip("Optional Elements")
        self.button.setStyleSheet("QPushButton { border: none; }")
        self.button.setFixedSize(18, 18)

        self.menu = QMenu(self)
        
        self.button.clicked.connect(self.show_menu)

        layout.addWidget(self.button)
        
    def show_menu(self):
        self.menu.popup(self.button.mapToGlobal(QPoint(0, self.button.height())))

    def add_items(self, items):
        for item in items:
            action = self.menu.addAction(item)
            action.triggered.connect(lambda checked=False, text=item: self.item_selected.emit(text))
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
    spinner_metadata = {
        'x_meters': {'label': 'X (m)', 'step': 0.1, 'range': (-1000, 1000), 'removable': False},
        'y_meters': {'label': 'Y (m)', 'step': 0.1, 'range': (-1000, 1000), 'removable': False},
        'final_velocity_meters_per_sec': {'label': 'Final Velocity (m/s)', 'step': 0.1, 'range': (0, 100), 'removable': True},
        'max_velocity_meters_per_sec': {'label': 'Max Velocity (m/s)', 'step': 0.1, 'range': (0, 100), 'removable': True},
        'max_acceleration_meters_per_sec2': {'label': 'Max Acceleration (m/s²)', 'step': 0.1, 'range': (0, 100), 'removable': True},
        'intermediate_handoff_radius_meters': {'label': 'Handoff Radius (m)', 'step': 0.1, 'range': (0, 100), 'removable': True}, 
        'rotation_radians': {'label': 'Rotation (rad)', 'step': 0.01, 'range': (-3.14, 3.14), 'removable': False},
        'max_velocity_rad_per_sec': {'label': 'Max Rot Velocity (rad/s)', 'step': 0.1, 'range': (0, 100), 'removable': True},
        'max_acceleration_rad_per_sec2': {'label': 'Max Rot Acceleration (rad/s²)', 'step': 0.1, 'range': (0, 100), 'removable': True}
    }        

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
        group_box_spinner_layout.setContentsMargins(5, 5, 5, 5) # Reduced top margin

        # Form layout for the properties
        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignRight)
        form_layout.setVerticalSpacing(4)  # Consistent, small vertical spacing
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

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

        form_layout.addRow(self.type_label, self.optional_container)
        
        for name, data in self.spinner_metadata.items():
            spin = QDoubleSpinBox()
            spin.setSingleStep(data['step'])
            spin.setRange(*data['range'])
            spin.setValue(0)
            spin.setMinimumWidth(65) # Set uniform minimum width for alignment
            spin.setMaximumWidth(65)
            label = QLabel(data['label'])

            # Add button next to spinner
            spin_row = QWidget()
            spin_row_layout = QHBoxLayout(spin_row)
            spin_row_layout.setContentsMargins(0, 0, 0, 0)
            spin_row_layout.setSpacing(5) # Controls space between spin and btn
            spin_row.setMinimumHeight(24)
            spin_row.setMaximumHeight(24)

            btn = QPushButton()
            btn.setIconSize(QSize(18, 18))
            btn.setFixedSize(18, 18)
            btn.setStyleSheet("QPushButton { border: none; }")

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

            form_layout.addRow(label, spin_row)
            self.spinners[name] = (spin, label, btn, spin_row)

        group_box_spinner_layout.addLayout(form_layout)

        main_layout.addWidget(self.form_container)
        main_layout.addStretch() # Pushes all content to the top
        
        self.points_list.itemSelectionChanged.connect(self.on_item_selected)
        self.points_list.reordered.connect(self.on_points_list_reordered)

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
        if isinstance(element, Waypoint):
            self.expose_element(element.translation_target)
            self.expose_element(element.rotation_target)
        else:
            for name, (spin, label, btn, spin_row) in self.spinners.items():
                if hasattr(element, name) and getattr(element, name) is not None:
                    spin.setValue(getattr(element, name))
                    label.setVisible(True)
                    spin_row.setVisible(True)
                elif hasattr(element, name):
                    self.optional_pop.add_items([name])

    def on_item_selected(self):
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
            self.type_combo.setCurrentText(ElementType.TRANSLATION.value)
        elif isinstance(element, RotationTarget):
            self.type_combo.setCurrentText(ElementType.ROTATION.value)
        else:
            self.type_combo.setCurrentText(ElementType.WAYPOINT.value)
        
        self.type_label.setVisible(True)
        self.type_combo.setVisible(True)
        self.form_container.setVisible(True)
        self.title_bar.setVisible(True)
    
    def on_attribute_removed(self, key):
        idx = self.get_selected_index()
        if idx is None or self.path is None:
            return
        
        element = self.path.get_element(idx)
        if isinstance(element, Waypoint):
            if hasattr(element.translation_target, key):
                setattr(element.translation_target, key, None)
            if hasattr(element.rotation_target, key):
                setattr(element.rotation_target, key, None)
        elif hasattr(element, key):
            setattr(element, key, None)
        
        self.on_item_selected()

    def on_attribute_added(self, key):
        idx = self.get_selected_index()
        if idx is None or self.path is None:
            return
        element = self.path.get_element(idx)
        if (isinstance(element, Waypoint)):
            if hasattr(element.translation_target, key):
                setattr(element.translation_target, key, 0)
            if hasattr(element.rotation_target, key):
                setattr(element.rotation_target, key, 0)
        elif hasattr(element, key):
            setattr(element, key, 0)
        self.on_item_selected()


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

            self.path.path_elements[idx] = new_elem
            item = self.points_list.currentItem()
            item.setText(f"{new_type.value}")
            self.on_item_selected()  # Refresh fields

    def getattr_deep(obj, path):
        attrs = path.split('.')
        for attr in attrs:
            obj = getattr(obj, attr, None)
        return obj


    def on_attribute_change(self, key, value):
        idx = self.get_selected_index()
        if idx is not None and self.path is not None:
            element = self.path.get_element(idx)
            if isinstance(element, Waypoint):
                if hasattr(element.translation_target, key):
                    setattr(element.translation_target, key, value)
                if hasattr(element.rotation_target, key):
                    setattr(element.rotation_target, key, value)
            elif hasattr(element, key):
                setattr(element, key, value)

    def rebuild_points_list(self):
        self.hide_spinners()
        self.points_list.clear()
        if (self.path):
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
        self.rebuild_points_list()
        
    def on_points_list_reordered(self):
        if self.path is None:
            return
        new_order = [self.points_list.item(i).data(Qt.UserRole) for i in range(self.points_list.count())]  # Changed to item(i), count()
        self.path.reorder_elements(new_order)

        print("Model reordered: ", self.path.path_elements)