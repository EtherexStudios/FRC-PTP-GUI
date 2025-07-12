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

        self.vel_spin = QDoubleSpinBox()
        self.vel_spin.setRange(0,10)
        layout.addRow("Max Velocity:", self.vel_spin)

        self.points_list.itemSelectionChanged.connect(self.on_item_selected)
        self.points_list.reordered.connect(self.on_points_list_reordered)

        self.rebuild_points_list()
        
    def on_item_selected(self):
        selected = self.points_list.selectedItems()
        if selected:
            # Dummy load (later from model)
            self.type_combo.setCurrentText('translation')
            self.x_spin.setValue(1.0)
            self.y_spin.setValue(2.0)
            self.vel_spin.setValue(4.5)
            print("Selected item:", selected[0].text())

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