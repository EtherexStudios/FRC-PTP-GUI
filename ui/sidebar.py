from PySide6.QtWidgets import QWidget, QFormLayout, QLabel, QComboBox, QDoubleSpinBox
from PySide6.QtWidgets import QListWidget, QListWidgetItem 
from models.path_model import Path, TranslationTarget, RotationTarget, Waypoint
from PySide6.QtCore import Qt
from PySide6.QtCore import Signal
from enum import Enum

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

    
class Sidebar(QWidget):
    spinner_metadata = {
        'x_meters': {'label': 'X (m)', 'step': 0.1, 'range': (-1000, 1000)},
        'y_meters': {'label': 'Y (m)', 'step': 0.1, 'range': (-1000, 1000)},
        'final_velocity_meters_per_sec': {'label': 'Final Velocity (m/s)', 'step': 0.1, 'range': (0, 100)},
        'max_velocity_meters_per_sec': {'label': 'Max Velocity (m/s)', 'step': 0.1, 'range': (0, 100)},
        'max_acceleration_meters_per_sec2': {'label': 'Max Acceleration (m/s²)', 'step': 0.1, 'range': (0, 100)},
        'intermediate_handoff_radius_meters': {'label': 'Handoff Radius (m)', 'step': 0.1, 'range': (0, 100)}, 
        'rotation_radians': {'label': 'Rotation (rad)', 'step': 0.01, 'range': (-3.14, 3.14)},
        'max_velocity_rad_per_sec': {'label': 'Max Rot Velocity (rad/s)', 'step': 0.1, 'range': (0, 100)},
        'max_acceleration_rad_per_sec2': {'label': 'Max Rot Acceleration (rad/s²)', 'step': 0.1, 'range': (0, 100)}
    }

    def __init__(self, path=Path()):

        super().__init__()  # Parent init
        layout = QFormLayout(self)  # Form layout (label + input pairs)

        label = QLabel("Path Elements")  # Add this for QListWidget, or optional for QTreeWidget
        layout.addWidget(label)

        self.path = path
        
        self.points_list = CustomList()  # Changed to CustomList
        layout.addWidget(self.points_list)  # No header—add QLabel("Path Elements") above if needed

        # Store label references for each spinner
        self.spinners = {}
     
        self.type_combo = QComboBox()
        self.type_combo.addItems([e.value for e in ElementType])
        self.type_label = QLabel("Type:")
        layout.addRow(self.type_label, self.type_combo)
    
        for name, data in self.spinner_metadata.items():
            spin = QDoubleSpinBox()
            spin.setSingleStep(data['step'])
            spin.setRange(*data['range'])
            spin.setValue(0)
            label = QLabel(data['label'])

            # FIX: capture 'name' as a default argument in the lambda
            spin.valueChanged.connect(lambda v, n=name: self.on_attribute_change(n, v))

            layout.addRow(label, spin)
            self.spinners[name] = (spin, label)

        self.points_list.itemSelectionChanged.connect(self.on_item_selected)
        self.points_list.reordered.connect(self.on_points_list_reordered)

        self.type_combo.currentTextChanged.connect(self.on_type_change)
        
        self.rebuild_points_list()
    
    def hide_spinners(self):
        for name, (spin, label) in self.spinners.items():
            spin.setVisible(False)
            label.setVisible(False)

        self.type_combo.setVisible(False)
        self.type_label.setVisible(False)

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
            self.hide_spinners()
            for name, (spin, label) in self.spinners.items():
                if hasattr(element, name) and getattr(element, name) is not None:
                    spin.setValue(getattr(element, name))
                    spin.setVisible(True)
                    label.setVisible(True)

    def on_item_selected(self):
        idx = self.get_selected_index()
        if idx is None or self.path is None:
            return
        element = self.path.get_element(idx)
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