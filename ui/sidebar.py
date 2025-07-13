from PySide6.QtWidgets import QWidget, QFormLayout, QLabel, QComboBox, QDoubleSpinBox
from PySide6.QtWidgets import QListWidget, QListWidgetItem 
from models.path_model import PathModel
from PySide6.QtCore import Qt
from PySide6.QtCore import Signal

class CustomList(QListWidget):  # Changed to QListWidget
    reordered = Signal()
    
    def __init__(self, model):
        super().__init__()
        self.model = model
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
    def __init__(self, model):
        super().__init__()  # Parent init
        layout = QFormLayout(self)  # Form layout (label + input pairs)

        label = QLabel("Path Elements")  # Add this for QListWidget, or optional for QTreeWidget
        layout.addWidget(label)

        self.model = model
        
        self.points_list = CustomList(model)  # Changed to CustomList
        layout.addWidget(self.points_list)  # No header—add QLabel("Path Elements") above if needed
     
        self.type_combo = QComboBox()
        self.type_combo.addItems(['translation', 'waypoint', 'rotation'])
        layout.addRow("Type:", self.type_combo)

        self.x_spin = QDoubleSpinBox()
        self.x_spin.setRange(0,10)
        layout.addRow("X (m):", self.x_spin)

        self.y_spin = QDoubleSpinBox()
        self.y_spin.setRange(0,10)
        layout.addRow("Y (m):", self.y_spin)

        self.points_list.itemSelectionChanged.connect(self.on_item_selected)
        self.points_list.reordered.connect(self.on_points_list_reordered)

        self.type_combo.currentTextChanged.connect(self.on_type_change)
        self.x_spin.valueChanged.connect(self.on_x_change)
        self.y_spin.valueChanged.connect(self.on_y_change)

        self.rebuild_points_list()
    
    def get_selected_index(self):
        selected = self.points_list.selectedItems()
        if selected:
            return selected[0].data(Qt.UserRole)
        else:
            return -1
        
    def on_item_selected(self):
        index = self.get_selected_index()
        if index >= 0:
            point = self.model.get_point(index)
            self.type_combo.setCurrentText(point['type'])
            self.x_spin.setValue(point['x'])
            self.y_spin.setValue(point['y'])

    def on_type_change(self, value):
        index = self.get_selected_index()
        if index >= 0:
            self.model.update_point(index, 'type', value)
            item = self.points_list.currentItem()
            item.setText(f"{value} {index+1}")

    def on_x_change(self, value):
        index = self.get_selected_index()
        if index >= 0:
            self.model.update_point(index, 'x', value)
            print("Updated x to", value)

    def on_y_change(self, value):
        index = self.get_selected_index()
        if index >= 0:
            self.model.update_point(index, 'y', value)
            print("Updated y to", value)

    def rebuild_points_list(self):
        self.points_list.clear()
        for i, p in enumerate(self.model.get_points()):
            item = QListWidgetItem(f"{p['type']} {i+1}")  # Changed to QListWidgetItem, no []
            item.setData(Qt.UserRole, i)  # No column 0
            self.points_list.addItem(item)  # Changed to addItem
    
    def on_points_list_reordered(self):
        new_order = [self.points_list.item(i).data(Qt.UserRole) for i in range(self.points_list.count())]  # Changed to item(i), count()
        self.model.reorder_points(new_order)

        print("Model reordered: ", self.model.get_points())