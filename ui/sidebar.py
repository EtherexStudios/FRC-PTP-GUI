from PySide6.QtWidgets import QWidget, QFormLayout, QLabel, QComboBox, QDoubleSpinBox
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

class Sidebar(QWidget):
    def __init__(self):
        super().__init__()  # Parent init
        layout = QFormLayout(self)  # Form layout (label + input pairs)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("Path Elements")
        self.tree.setDragDropMode(QTreeWidget.InternalMove)
        layout.addWidget(self.tree)
     
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

        self.tree.itemSelectionChanged.connect(self.on_item_selected)

        item1 = QTreeWidgetItem(["Element 1"])
        self.tree.addTopLevelItem(item1)
        item2 = QTreeWidgetItem(["Element 2"])
        self.tree.addTopLevelItem(item2)
        
    def on_item_selected(self):
        selected = self.tree.selectedItems()
        if selected:
            # Dummy load (later from model)
            self.type_combo.setCurrentText('translation')
            self.x_spin.setValue(1.0)
            self.y_spin.setValue(2.0)
            self.vel_spin.setValue(4.5)
            print("Selected item:", selected[0].text(0))