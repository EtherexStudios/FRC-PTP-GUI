from __future__ import annotations
import math
from typing import List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem, QGraphicsLineItem, QGraphicsPathItem, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView

from models.path_model import Path, PathElement, TranslationTarget, RotationTarget, Waypoint


FIELD_LENGTH_METERS = 16.54
FIELD_WIDTH_METERS = 8.21


class DraggablePointItem(QGraphicsEllipseItem):
    def __init__(self, canvas_view: 'CanvasView', center_m: QPointF, radius_m: float, color: QColor, index_in_model: int):
        super().__init__()
        self.canvas_view = canvas_view
        self.index_in_model = index_in_model
        self.radius_m = radius_m
        # Keep ellipse centered around local origin, move using setPos
        self.setRect(QRectF(-radius_m, -radius_m, radius_m * 2, radius_m * 2))
        self.setPos(self.canvas_view._scene_from_model(center_m.x(), center_m.y()))
        self.setBrush(QBrush(color))
        self.setPen(QPen(QColor("#222222"), 0.02))
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setZValue(10)

    def set_center(self, center_m: QPointF):
        self.setPos(self.canvas_view._scene_from_model(center_m.x(), center_m.y()))

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        if change == QGraphicsItem.ItemPositionChange:
            new_pos: QPointF = value
            # Clamp in scene coordinates to keep within field
            cx, cy = self.canvas_view._clamp_scene_coords(new_pos.x(), new_pos.y())
            # Return clamped value; actual updates occur after the position is committed
            return QPointF(cx, cy)
        elif change == QGraphicsItem.ItemPositionHasChanged:
            # Now that the item's position is committed, notify for visual updates and model sync
            x_m, y_m = self.canvas_view._model_from_scene(self.pos().x(), self.pos().y())
            self.canvas_view._on_item_live_moved(self.index_in_model, x_m, y_m)
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        self.canvas_view._on_item_clicked(self.index_in_model)
        super().mousePressEvent(event)


class RotationHandle(QGraphicsEllipseItem):
    def __init__(self, canvas_view: 'CanvasView', parent_center_item: DraggablePointItem, handle_distance_m: float, handle_radius_m: float, color: QColor):
        super().__init__()
        self.canvas_view = canvas_view
        self.center_item = parent_center_item
        self.handle_distance_m = handle_distance_m
        self.handle_radius_m = handle_radius_m
        self.setBrush(QBrush(color))
        self.setPen(QPen(QColor("#222222"), 0.02))
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setZValue(12)
        self._angle_radians: float = 0.0
        self.link_line = QGraphicsLineItem()
        self.link_line.setPen(QPen(QColor("#888888"), 0.03))
        self.link_line.setZValue(11)
        # Local geometry centered on origin
        self.setRect(QRectF(-handle_radius_m, -handle_radius_m, handle_radius_m * 2, handle_radius_m * 2))
        # Initial placement
        self.sync_to_angle()

    def scene_items(self) -> List[QGraphicsItem]:
        return [self.link_line, self]

    def set_angle(self, radians: float):
        self._angle_radians = radians
        self.sync_to_angle()

    def sync_to_angle(self):
        cx = self.center_item.pos().x()
        cy = self.center_item.pos().y()
        # Convert model angle (y-up) to scene (y-down)
        angle_scene = -self._angle_radians
        hx = cx + math.cos(angle_scene) * self.handle_distance_m
        hy = cy + math.sin(angle_scene) * self.handle_distance_m
        self.setPos(QPointF(hx, hy))
        self.link_line.setLine(cx, cy, hx, hy)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        if change == QGraphicsItem.ItemPositionChange:
            new_center: QPointF = value
            cx = self.center_item.pos().x()
            cy = self.center_item.pos().y()
            dx = new_center.x() - cx
            dy = new_center.y() - cy
            angle_scene = math.atan2(dy, dx)
            # Constrain to ring distance by returning the adjusted position
            hx = cx + math.cos(angle_scene) * self.handle_distance_m
            hy = cy + math.sin(angle_scene) * self.handle_distance_m
            self.link_line.setLine(cx, cy, hx, hy)
            # Convert to model angle (y-up)
            angle_model = -angle_scene
            self._angle_radians = angle_model
            # Notify canvas
            self.canvas_view._on_item_live_rotated(self.center_item.index_in_model, angle_model)
            return QPointF(hx, hy)
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        # Prevent center item from moving while rotating
        self.center_item.setFlag(QGraphicsItem.ItemIsMovable, False)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.center_item.setFlag(QGraphicsItem.ItemIsMovable, True)
        super().mouseReleaseEvent(event)


class CanvasView(QGraphicsView):
    # Emitted when the user selects an element on the canvas
    elementSelected = Signal(int)  # index
    # Emitted when the user drags an element to a new location (meters)
    elementMoved = Signal(int, float, float)  # index, x_m, y_m
    # Emitted when the user adjusts a rotation (radians)
    elementRotated = Signal(int, float)  # index, radians

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setTransformationAnchor(QGraphicsView.AnchorViewCenter)
        self._is_fitting = False

        self.graphics_scene = QGraphicsScene(self)
        self.setScene(self.graphics_scene)
        self.graphics_scene.setSceneRect(0, 0, FIELD_LENGTH_METERS, FIELD_WIDTH_METERS)

        self._field_pixmap_item: Optional[QGraphicsPixmapItem] = None
        self._path: Optional[Path] = None
        self._items: List[Tuple[str, DraggablePointItem, Optional[RotationHandle]]] = []
        self._connect_lines: List[QGraphicsLineItem] = []

        self._load_field_background("assets/field25.png")

    def _load_field_background(self, image_path: str):
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return
        self._field_pixmap_item = QGraphicsPixmapItem(pixmap)
        self._field_pixmap_item.setZValue(-10)
        # Scale pixmap from pixels into meters preserving aspect ratio
        if pixmap.width() > 0 and pixmap.height() > 0:
            s = min(FIELD_LENGTH_METERS / float(pixmap.width()), FIELD_WIDTH_METERS / float(pixmap.height()))
            self._field_pixmap_item.setTransform(QTransform().scale(s, s))
            # Position so bottom-left aligns with (0,0) model → account for scene y-down
            h_scaled = pixmap.height() * s
            self._field_pixmap_item.setPos(0.0, FIELD_WIDTH_METERS - h_scaled)
        self.graphics_scene.addItem(self._field_pixmap_item)

    def set_path(self, path: Path):
        self._path = path
        self._rebuild_items()

    def refresh_from_model(self):
        # Update item positions and angles from model without rebuilding structure
        if self._path is None:
            return
        for i, (kind, item, handle) in enumerate(self._items):
            element = self._path.path_elements[i]
            pos = self._element_position(element)
            item.set_center(QPointF(pos[0], pos[1]))
            if handle is not None:
                angle = self._element_rotation(element)
                handle.set_angle(angle)
        self._update_connecting_lines()

    def select_index(self, index: int):
        if index is None or index < 0 or index >= len(self._items):
            return
        # visually select
        _, item, _ = self._items[index]
        self.graphics_scene.clearSelection()
        item.setSelected(True)
        self.centerOn(item)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_to_scene()

    def showEvent(self, event):
        super().showEvent(event)
        self._fit_to_scene()

    def _fit_to_scene(self):
        if self._is_fitting:
            return
        self._is_fitting = True
        try:
            rect = self.graphics_scene.sceneRect()
            if rect.width() > 0 and rect.height() > 0:
                self.fitInView(rect, Qt.KeepAspectRatio)
        finally:
            self._is_fitting = False

    # Internal helpers
    def _clear_scene_items(self):
        for _, item, handle in self._items:
            self.graphics_scene.removeItem(item)
            if handle is not None:
                for sub in handle.scene_items():
                    self.graphics_scene.removeItem(sub)
        for line in self._connect_lines:
            self.graphics_scene.removeItem(line)
        self._items.clear()
        self._connect_lines.clear()

    def _rebuild_items(self):
        self._clear_scene_items()
        if self._path is None:
            return

        for i, element in enumerate(self._path.path_elements):
            pos = self._element_position(element)

            # Choose visuals by element type
            if isinstance(element, TranslationTarget):
                color = QColor("#3aa3ff")
                radius = 0.20
                kind = "translation"
                item = DraggablePointItem(self, QPointF(pos[0], pos[1]), radius, color, i)
                rotation_handle = None
            elif isinstance(element, RotationTarget):
                color = QColor("#ff7f3a")
                radius = 0.22
                kind = "rotation"
                item = DraggablePointItem(self, QPointF(pos[0], pos[1]), radius, color, i)
                rotation_handle = RotationHandle(self, item, handle_distance_m=0.7, handle_radius_m=0.12, color=QColor("#ffaa00"))
            elif isinstance(element, Waypoint):
                color = QColor("#50c878")
                radius = 0.24
                kind = "waypoint"
                item = DraggablePointItem(self, QPointF(pos[0], pos[1]), radius, color, i)
                rotation_handle = RotationHandle(self, item, handle_distance_m=0.7, handle_radius_m=0.12, color=QColor("#c4ff00"))
                # Initialize rotation from waypoint's rotation target
                rotation_handle.set_angle(self._element_rotation(element))
            else:
                # Unknown, skip
                continue

            # Add to scene
            self.graphics_scene.addItem(item)
            if rotation_handle is not None:
                for sub in rotation_handle.scene_items():
                    self.graphics_scene.addItem(sub)

            self._items.append((kind, item, rotation_handle))

        # Build connecting lines in hierarchical order
        self._build_connecting_lines()

    def _element_position(self, element: PathElement) -> Tuple[float, float]:
        if isinstance(element, TranslationTarget):
            return float(element.x_meters), float(element.y_meters)
        if isinstance(element, RotationTarget):
            return float(element.x_meters), float(element.y_meters)
        if isinstance(element, Waypoint):
            return float(element.translation_target.x_meters), float(element.translation_target.y_meters)
        return 0.0, 0.0

    def _element_rotation(self, element: PathElement) -> float:
        if isinstance(element, RotationTarget):
            return float(element.rotation_radians)
        if isinstance(element, Waypoint):
            return float(element.rotation_target.rotation_radians)
        return 0.0

    def _build_connecting_lines(self):
        self._connect_lines = []
        for i in range(len(self._items) - 1):
            _, a, _ = self._items[i]
            _, b, _ = self._items[i + 1]
            line = QGraphicsLineItem(a.pos().x(), a.pos().y(), b.pos().x(), b.pos().y())
            line.setPen(QPen(QColor("#cccccc"), 0.05))
            line.setZValue(5)
            self.graphics_scene.addItem(line)
            self._connect_lines.append(line)

    def _update_connecting_lines(self):
        for i in range(len(self._connect_lines)):
            _, a, _ = self._items[i]
            _, b, _ = self._items[i + 1]
            self._connect_lines[i].setLine(a.pos().x(), a.pos().y(), b.pos().x(), b.pos().y())

    # Live updates while dragging/rotating for visuals, and emit changes out for model syncing
    def _on_item_live_moved(self, index: int, x_m: float, y_m: float):
        self._update_connecting_lines()
        # Keep rotation handle linked to moved point
        kind, _, handle = self._items[index]
        if handle is not None:
            handle.sync_to_angle()
        self.elementMoved.emit(index, x_m, y_m)

    def _on_item_live_rotated(self, index: int, angle_radians: float):
        self.elementRotated.emit(index, angle_radians)

    def _on_item_clicked(self, index: int):
        self.elementSelected.emit(index)

    # Coordinate conversions between model meters (y-up) and scene (y-down)
    def _scene_from_model(self, x_m: float, y_m: float) -> QPointF:
        return QPointF(x_m, FIELD_WIDTH_METERS - y_m)

    def _model_from_scene(self, x_s: float, y_s: float) -> Tuple[float, float]:
        return float(x_s), float(FIELD_WIDTH_METERS - y_s)

    def _clamp_scene_coords(self, x_s: float, y_s: float) -> Tuple[float, float]:
        min_x, min_y = 0.0, 0.0
        max_x, max_y = FIELD_LENGTH_METERS, FIELD_WIDTH_METERS
        return max(min_x, min(x_s, max_x)), max(min_y, min(y_s, max_y))


