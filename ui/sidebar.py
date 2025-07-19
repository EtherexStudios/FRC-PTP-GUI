from PySide6.QtWidgets import QWidget, QFormLayout, QLabel, QComboBox, QDoubleSpinBox
from PySide6.QtWidgets import QListWidget, QListWidgetItem 
from models.path_model import Path, TranslationTarget, RotationTarget, Waypoint, Translation2d, Rotation2d
from PySide6.QtCore import Qt
from PySide6.QtCore import Signal

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
            item.setText(f"{item.text().split()[0]} {i+1}")

    
class Sidebar(QWidget):
    def __init__(self):
        super().__init__()  # Parent init
        layout = QFormLayout(self)  # Form layout (label + input pairs)

        label = QLabel("Path Elements")  # Add this for QListWidget, or optional for QTreeWidget
        layout.addWidget(label)

        self.path = None
        
        self.points_list = CustomList()  # Changed to CustomList
        layout.addWidget(self.points_list)  # No header—add QLabel("Path Elements") above if needed

        # Store label references for each spinner
        self.labels = {}
     
        self.type_combo = QComboBox()
        self.type_combo.addItems(['translation', 'waypoint', 'rotation'])
        type_label = QLabel("Type:")
        layout.addRow(type_label, self.type_combo)
        self.labels[self.type_combo] = type_label

        self.x_spin = QDoubleSpinBox()
        x_label = QLabel("X (m):")
        layout.addRow(x_label, self.x_spin)
        self.labels[self.x_spin] = x_label

        self.y_spin = QDoubleSpinBox()
        y_label = QLabel("Y (m):")
        layout.addRow(y_label, self.y_spin)
        self.labels[self.y_spin] = y_label

        # Optional fields for TranslationTarget
        self.final_velocity_spin = QDoubleSpinBox()
        self.final_velocity_spin.setSingleStep(0.1)
        fv_label = QLabel("Final Velocity (m/s):")
        layout.addRow(fv_label, self.final_velocity_spin)
        self.labels[self.final_velocity_spin] = fv_label

        self.max_velocity_spin = QDoubleSpinBox()
        self.max_velocity_spin.setSingleStep(0.1)
        mv_label = QLabel("Max Velocity (m/s):")
        layout.addRow(mv_label, self.max_velocity_spin)
        self.labels[self.max_velocity_spin] = mv_label

        self.max_accel_spin = QDoubleSpinBox()
        self.max_accel_spin.setSingleStep(0.1)
        ma_label = QLabel("Max Acceleration (m/s²):")
        layout.addRow(ma_label, self.max_accel_spin)
        self.labels[self.max_accel_spin] = ma_label

        self.handoff_radius_spin = QDoubleSpinBox()
        self.handoff_radius_spin.setSingleStep(0.1)
        hr_label = QLabel("Handoff Radius (m):")
        layout.addRow(hr_label, self.handoff_radius_spin)
        self.labels[self.handoff_radius_spin] = hr_label

        # Optional fields for RotationTarget
        self.rotation_spin = QDoubleSpinBox()
        self.rotation_spin.setSingleStep(0.01)
        rot_label = QLabel("Rotation (rad):")
        layout.addRow(rot_label, self.rotation_spin)
        self.labels[self.rotation_spin] = rot_label

        self.max_rot_velocity_spin = QDoubleSpinBox()
        self.max_rot_velocity_spin.setSingleStep(0.1)
        mrv_label = QLabel("Max Rot Velocity (rad/s):")
        layout.addRow(mrv_label, self.max_rot_velocity_spin)
        self.labels[self.max_rot_velocity_spin] = mrv_label

        self.max_rot_accel_spin = QDoubleSpinBox()
        self.max_rot_accel_spin.setSingleStep(0.1)
        mra_label = QLabel("Max Rot Acceleration (rad/s²):")
        layout.addRow(mra_label, self.max_rot_accel_spin)
        self.labels[self.max_rot_accel_spin] = mra_label

        self.points_list.itemSelectionChanged.connect(self.on_item_selected)
        self.points_list.reordered.connect(self.on_points_list_reordered)

        self.type_combo.currentTextChanged.connect(self.on_type_change)
        self.x_spin.valueChanged.connect(self.on_x_change)
        self.y_spin.valueChanged.connect(self.on_y_change)
        self.final_velocity_spin.valueChanged.connect(self.on_final_velocity_change)
        self.max_velocity_spin.valueChanged.connect(self.on_max_velocity_change)
        self.max_accel_spin.valueChanged.connect(self.on_max_accel_change)
        self.handoff_radius_spin.valueChanged.connect(self.on_handoff_radius_change)
        self.rotation_spin.valueChanged.connect(self.on_rotation_change)
        self.max_rot_velocity_spin.valueChanged.connect(self.on_max_rot_velocity_change)
        self.max_rot_accel_spin.valueChanged.connect(self.on_max_rot_accel_change)

        self.rebuild_points_list()
    
    def hide_spinners(self):
        for widget in [
            self.x_spin, self.y_spin, self.type_combo,
            self.final_velocity_spin, self.max_velocity_spin, self.max_accel_spin, self.handoff_radius_spin,
            self.rotation_spin, self.max_rot_velocity_spin, self.max_rot_accel_spin
        ]:
            widget.setVisible(False)
            self.labels[widget].setVisible(False)

    def get_selected_index(self):
        selected = self.points_list.selectedItems()
        if selected:
            return selected[0].data(Qt.UserRole)
        else:
            return -1
    
    def expose_translation_element(self, element):
        if element.translation.x is not None:
            self.x_spin.setValue(element.translation.x)
            self.x_spin.setVisible(True)
            self.labels[self.x_spin].setVisible(True)
        if element.translation.y is not None:
            self.y_spin.setValue(element.translation.y)
            self.y_spin.setVisible(True)
            self.labels[self.y_spin].setVisible(True)
        if element.final_velocity_meters_per_sec is not None:
            self.final_velocity_spin.setValue(element.final_velocity_meters_per_sec)
            self.final_velocity_spin.setVisible(True)
            self.labels[self.final_velocity_spin].setVisible(True)
        if element.max_velocity_meters_per_sec is not None:
            self.max_velocity_spin.setValue(element.max_velocity_meters_per_sec)
            self.max_velocity_spin.setVisible(True)
            self.labels[self.max_velocity_spin].setVisible(True)
        if element.max_acceleration_meters_per_sec2 is not None:
            self.max_accel_spin.setValue(element.max_acceleration_meters_per_sec2)
            self.max_accel_spin.setVisible(True)
            self.labels[self.max_accel_spin].setVisible(True)
        if element.intermediate_handoff_radius_meters is not None:
            self.handoff_radius_spin.setValue(element.intermediate_handoff_radius_meters)
            self.handoff_radius_spin.setVisible(True)
            self.labels[self.handoff_radius_spin].setVisible(True)
        
    def expose_rotation_element(self, element):
        if element.translation.x is not None:
            self.x_spin.setValue(element.translation.x)
            self.x_spin.setVisible(True)
            self.labels[self.x_spin].setVisible(True)
        if element.translation.y is not None:
            self.y_spin.setValue(element.translation.y)
            self.y_spin.setVisible(True)
            self.labels[self.y_spin].setVisible(True)
        if element.rotation.radians is not None:
            self.rotation_spin.setValue(element.rotation.radians)
            self.rotation_spin.setVisible(True)
            self.labels[self.rotation_spin].setVisible(True)
        if element.max_velocity_rad_per_sec is not None:
            self.max_rot_velocity_spin.setValue(element.max_velocity_rad_per_sec)
            self.max_rot_velocity_spin.setVisible(True)
            self.labels[self.max_rot_velocity_spin].setVisible(True)
        if element.max_acceleration_rad_per_sec2 is not None:
            self.max_rot_accel_spin.setValue(element.max_acceleration_rad_per_sec2)
            self.max_rot_accel_spin.setVisible(True)
            self.labels[self.max_rot_accel_spin].setVisible(True)

    def expose_waypoint_element(self, element):
        self.expose_translation_element(element.translation_target)
        self.expose_rotation_element(element.rotation_target)

    def on_item_selected(self):
        idx = self.get_selected_index()
        if idx is None or self.path is None:
            return
        element = self.path.get_element(idx)

        self.hide_spinners()

        if isinstance(element, TranslationTarget):
            self.type_combo.setCurrentText('translation')
            self.type_combo.setVisible(True)
            self.labels[self.type_combo].setVisible(True)

            self.expose_translation_element(element)

        elif isinstance(element, RotationTarget):
            self.type_combo.setCurrentText('rotation')
            self.type_combo.setVisible(True)
            self.labels[self.type_combo].setVisible(True)

            self.expose_rotation_element(element)

        elif isinstance(element, Waypoint):
            self.type_combo.setCurrentText('waypoint')
            self.type_combo.setVisible(True)
            self.labels[self.type_combo].setVisible(True)

            self.expose_waypoint_element(element)

    def on_type_change(self, value):
        index = self.get_selected_index()
        if index >= 0 and self.path:
            self.path.update_point(index, 'type', value)
            item = self.points_list.currentItem()
            item.setText(f"{value} {index+1}")

    def on_x_change(self, value):
        idx = self.get_selected_index()
        if idx is not None and self.path is not None:
            self.path.update_element(idx, 'translation', Translation2d(value, self.y_spin.value()))

    def on_y_change(self, value):
        idx = self.get_selected_index()
        if idx is not None and self.path is not None:
            self.path.update_element(idx, 'translation', Translation2d(self.x_spin.value(), value))

    def on_final_velocity_change(self, value):
        idx = self.get_selected_index()
        if idx is not None and self.path is not None:
            self.path.update_element(idx, 'final_velocity_meters_per_sec', value)

    def on_max_velocity_change(self, value):
        idx = self.get_selected_index()
        if idx is not None and self.path is not None:
            self.path.update_element(idx, 'max_velocity_meters_per_sec', value)

    def on_max_accel_change(self, value):
        idx = self.get_selected_index()
        if idx is not None and self.path is not None:
            self.path.update_element(idx, 'max_acceleration_meters_per_sec2', value)

    def on_handoff_radius_change(self, value):
        idx = self.get_selected_index()
        if idx is not None and self.path is not None:
            self.path.update_element(idx, 'intermediate_handoff_radius_meters', value)

    def on_rotation_change(self, value):
        idx = self.get_selected_index()
        if idx is not None and self.path is not None:
            self.path.update_element(idx, 'rotation', Rotation2d(value))

    def on_max_rot_velocity_change(self, value):
        idx = self.get_selected_index()
        if idx is not None and self.path is not None:
            self.path.update_element(idx, 'max_velocity_rad_per_sec', value)

    def on_max_rot_accel_change(self, value):
        idx = self.get_selected_index()
        if idx is not None and self.path is not None:
            self.path.update_element(idx, 'max_acceleration_rad_per_sec2', value)

    def on_waypoint_rotation_change(self, value):
        idx = self.get_selected_index()
        if idx is not None and self.path is not None:
            self.path.update_element(idx, 'rotation_target', Rotation2d(value))

    def on_waypoint_x_change(self, value):
        idx = self.get_selected_index()
        if idx is not None and self.path is not None:
            self.path.update_element(idx, 'translation_target', Translation2d(value, self.waypoint_y_spin.value()))

    def on_waypoint_y_change(self, value):
        idx = self.get_selected_index()
        if idx is not None and self.path is not None:
            self.path.update_element(idx, 'translation_target', Translation2d(self.waypoint_x_spin.value(), value))

    def rebuild_points_list(self):
        self.hide_spinners()
        if (self.path):
            self.points_list.clear()
            for i, p in enumerate(self.path.path_elements):
                name = ''
                if isinstance(p, TranslationTarget):
                    name = 'Translation Target'
                elif isinstance(p, RotationTarget):
                    name = 'Rotation Target'
                elif isinstance(p, Waypoint):
                    name = 'Waypoint'
                    
                item = QListWidgetItem(name)  # Changed to QListWidgetItem, no []
                item.setData(Qt.UserRole, i)  # No column 0
                self.points_list.addItem(item)  # Changed to addItem

    def set_path(self, path: Path):
        self.path = path
        self.rebuild_points_list()
        
    def on_points_list_reordered(self):
        if (self.path):
            new_order = [self.points_list.item(i).data(Qt.UserRole) for i in range(self.points_list.count())]  # Changed to item(i), count()
            self.path.reorder_points(new_order)

            print("Model reordered: ", self.path.get_points())