"""Graphics item subclasses for path elements (circle/rect + rotation handle + handoff radius)."""
from __future__ import annotations
import math
from typing import Optional, List
from PySide6.QtWidgets import (
    QGraphicsEllipseItem, QGraphicsRectItem, QGraphicsPolygonItem, QGraphicsItem,
    QGraphicsLineItem
)
from PySide6.QtGui import QBrush, QColor, QPen, QPolygonF
from PySide6.QtCore import QPointF, Qt

from ..constants import (
    ELEMENT_CIRCLE_RADIUS_M, TRIANGLE_REL_SIZE, OUTLINE_THIN_M, OUTLINE_THICK_M,
    OUTLINE_EDGE_PEN, HANDLE_LINK_THICKNESS_M, HANDLE_DISTANCE_M, HANDLE_RADIUS_M,
    HANDOFF_RADIUS_PEN
)
from models.path_model import Waypoint, TranslationTarget

class CircleElementItem(QGraphicsEllipseItem):
    def __init__(self, canvas_view: 'CanvasView', center_m: QPointF, index_in_model: int,
                 *, filled_color: Optional[QColor], outline_color: Optional[QColor],
                 dashed_outline: bool, triangle_color: Optional[QColor]):
        super().__init__()
        self.canvas_view = canvas_view
        self.index_in_model = index_in_model
        self.setRect(-ELEMENT_CIRCLE_RADIUS_M, -ELEMENT_CIRCLE_RADIUS_M, ELEMENT_CIRCLE_RADIUS_M * 2, ELEMENT_CIRCLE_RADIUS_M * 2)
        self.setPos(self.canvas_view._scene_from_model(center_m.x(), center_m.y()))
        thickness = OUTLINE_THICK_M if (outline_color and not dashed_outline) else OUTLINE_THIN_M
        pen = QPen(outline_color or QColor("#000"), thickness if outline_color else 0.0)
        if dashed_outline:
            pen.setStyle(Qt.DashLine)
        self.setPen(pen)
        self.setBrush(QBrush(filled_color) if filled_color else Qt.NoBrush)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setZValue(10)
        self.triangle_item: Optional[QGraphicsPolygonItem] = None
        if triangle_color is not None:
            self.triangle_item = QGraphicsPolygonItem(self)
            self._build_triangle(triangle_color)
        self._angle_radians: float = 0.0

    def _build_triangle(self, color: QColor):
        if not self.triangle_item:
            return
        base_size = ELEMENT_CIRCLE_RADIUS_M * 2 * TRIANGLE_REL_SIZE
        half_base = base_size * 0.5
        height = base_size
        points = [QPointF(height/2.0, 0.0), QPointF(-height/2.0, half_base), QPointF(-height/2.0, -half_base)]
        self.triangle_item.setPolygon(QPolygonF(points))
        self.triangle_item.setBrush(QBrush(color))
        self.triangle_item.setPen(OUTLINE_EDGE_PEN)
        self.triangle_item.setZValue(self.zValue() + 1)

    def set_center(self, center_m: QPointF):
        self.setPos(self.canvas_view._scene_from_model(center_m.x(), center_m.y()))

    def set_angle_radians(self, radians: float):
        self._angle_radians = radians
        self.setRotation(math.degrees(-radians))

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        if change == QGraphicsItem.ItemPositionChange:
            new_pos: QPointF = value
            try:
                cx, cy = self.canvas_view._constrain_scene_coords_for_index(self.index_in_model, new_pos.x(), new_pos.y())
                return QPointF(cx, cy)
            except Exception:
                return value
        elif change == QGraphicsItem.ItemPositionHasChanged:
            if not getattr(self.canvas_view, "_suppress_live_events", False):
                try:
                    x_m, y_m = self.canvas_view._model_from_scene(self.pos().x(), self.pos().y())
                    self.canvas_view._on_item_live_moved(self.index_in_model, x_m, y_m)
                except Exception:
                    pass
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        try:
            self.canvas_view._on_item_pressed(self.index_in_model)
            self.canvas_view._on_item_clicked(self.index_in_model)
        except Exception:
            pass
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        try:
            self.canvas_view._on_item_released(self.index_in_model)
        except Exception:
            pass
        super().mouseReleaseEvent(event)

class RectElementItem(QGraphicsRectItem):
    def __init__(self, canvas_view: 'CanvasView', center_m: QPointF, index_in_model: int,
                 *, filled_color: Optional[QColor], outline_color: Optional[QColor],
                 dashed_outline: bool, triangle_color: QColor):
        super().__init__()
        self.canvas_view = canvas_view
        self.index_in_model = index_in_model
        rw = getattr(self.canvas_view, "robot_length_m", 0.60)
        rh = getattr(self.canvas_view, "robot_width_m", 0.60)
        pen_width_m = OUTLINE_THICK_M if (outline_color and not dashed_outline) else OUTLINE_THIN_M
        inset = (pen_width_m if outline_color else 0.0) * 0.5
        self.setRect(-(rw/2.0) + inset, -(rh/2.0) + inset, rw - inset*2, rh - inset*2)
        self.setPos(self.canvas_view._scene_from_model(center_m.x(), center_m.y()))
        pen = QPen(outline_color or QColor("#000"), pen_width_m if outline_color else 0.0)
        if dashed_outline:
            try:
                # Frequent dash pattern with visible gaps; use FlatCap so gaps remain open
                pen.setStyle(Qt.CustomDashLine)
                pen.setDashPattern([1, .5])
            except Exception:
                pen.setStyle(Qt.DashLine)
            pen.setCapStyle(Qt.FlatCap)
            # Slightly thin the dashed stroke so it doesn't read as solid
            try:
                current_w = float(pen.widthF())
                pen.setWidthF(max(0.02, current_w * 0.8))
            except Exception:
                pass
        else:
            pen.setCapStyle(Qt.SquareCap)
        pen.setJoinStyle(Qt.MiterJoin)
        pen.setCosmetic(False)
        self.setPen(pen)
        if filled_color and not isinstance(self.canvas_view._path.path_elements[index_in_model], Waypoint):
            self.setBrush(QBrush(filled_color))
        else:
            self.setBrush(Qt.NoBrush)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setZValue(10)
        self.triangle_item = QGraphicsPolygonItem(self)
        self._build_triangle(triangle_color)
        # Tiny squares at corners to avoid voids with dashed outline
        self._corner_squares: List[QGraphicsRectItem] = []
        if dashed_outline:
            try:
                self._create_corner_squares(outline_color or QColor("#000"), float(pen.widthF()))
            except Exception:
                self._corner_squares = []
        self._angle_radians: float = 0.0

    def _build_triangle(self, color: QColor):
        rw = getattr(self.canvas_view, "robot_length_m", 0.60)
        rh = getattr(self.canvas_view, "robot_width_m", 0.60)
        base_size = min(rw, rh) * TRIANGLE_REL_SIZE
        half_base = base_size * 0.5
        height = base_size
        points = [QPointF(height/2.0, 0.0), QPointF(-height/2.0, half_base), QPointF(-height/2.0, -half_base)]
        self.triangle_item.setPolygon(QPolygonF(points))
        from models.path_model import Waypoint  # local import to avoid cycle
        if isinstance(self.canvas_view._path.path_elements[self.index_in_model], Waypoint):
            self.triangle_item.setBrush(Qt.NoBrush)
            p = QPen(color, OUTLINE_THICK_M)
            p.setJoinStyle(Qt.MiterJoin)
            p.setCapStyle(Qt.SquareCap)
            p.setCosmetic(False)
            self.triangle_item.setPen(p)
        else:
            self.triangle_item.setBrush(QBrush(color))
            self.triangle_item.setPen(OUTLINE_EDGE_PEN)
        self.triangle_item.setZValue(self.zValue() + 1)

    def set_center(self, center_m: QPointF):
        self.setPos(self.canvas_view._scene_from_model(center_m.x(), center_m.y()))

    def set_angle_radians(self, radians: float):
        self._angle_radians = radians
        self.setRotation(math.degrees(-radians))

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        if change == QGraphicsItem.ItemPositionChange:
            new_pos: QPointF = value
            try:
                cx, cy = self.canvas_view._constrain_scene_coords_for_index(self.index_in_model, new_pos.x(), new_pos.y())
                return QPointF(cx, cy)
            except Exception:
                return value
        elif change == QGraphicsItem.ItemPositionHasChanged:
            if not getattr(self.canvas_view, "_suppress_live_events", False):
                try:
                    x_m, y_m = self.canvas_view._model_from_scene(self.pos().x(), self.pos().y())
                    self.canvas_view._on_item_live_moved(self.index_in_model, x_m, y_m)
                except Exception:
                    pass
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        try:
            self.canvas_view._on_item_pressed(self.index_in_model)
            self.canvas_view._on_item_clicked(self.index_in_model)
        except Exception:
            pass
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        try:
            self.canvas_view._on_item_released(self.index_in_model)
        except Exception:
            pass
        super().mouseReleaseEvent(event)

    def paint(self, painter, option, widget=None):  # noqa: D401
        try:
            painter.setRenderHint(painter.Antialiasing, False)  # type: ignore
            painter.setRenderHint(painter.HighQualityAntialiasing, False)  # type: ignore
        except Exception:
            pass
        super().paint(painter, option, widget)

    def _create_corner_caps(self, color: QColor, pen_width_m: float, subtle: bool = False):
        # Deprecated: kept for reference
        for it in getattr(self, '_corner_caps', []) or []:
            try:
                if it.scene():
                    it.scene().removeItem(it)
            except Exception:
                pass
        self._corner_caps = []
        r = self.rect()
        left = r.left(); right = r.right(); top = r.top(); bottom = r.bottom()
        # Make very short caps; if subtle, reduce width and length
        cap_len = max(0.04, (pen_width_m * (1.5 if subtle else 3.0)))
        pen = QPen(color, (pen_width_m*0.6 if subtle else pen_width_m))
        # Flat caps keep caps from extending beyond endpoints
        pen.setCapStyle(Qt.FlatCap)
        pen.setJoinStyle(Qt.MiterJoin)
        pen.setCosmetic(False)
        def _add_line(x1,y1,x2,y2):
            ln = QGraphicsLineItem(self)
            ln.setLine(x1, y1, x2, y2)
            ln.setPen(pen)
            ln.setZValue(self.zValue() + 0.5)
            self._corner_caps.append(ln)
        # Top-left
        _add_line(left, top, left + cap_len, top)
        _add_line(left, top, left, top + cap_len)
        # Top-right
        _add_line(right - cap_len, top, right, top)
        _add_line(right, top, right, top + cap_len)
        # Bottom-left
        _add_line(left, bottom, left + cap_len, bottom)
        _add_line(left, bottom - cap_len, left, bottom)
        # Bottom-right
        _add_line(right - cap_len, bottom, right, bottom)
        _add_line(right, bottom - cap_len, right, bottom)

    def _create_corner_squares(self, color: QColor, pen_width_m: float):
        # Clear any existing squares
        for it in getattr(self, '_corner_squares', []) or []:
            try:
                if it.scene():
                    it.scene().removeItem(it)
            except Exception:
                pass
        self._corner_squares = []
        r = self.rect()
        left = r.left(); right = r.right(); top = r.top(); bottom = r.bottom()
        size = max(0.01, float(pen_width_m))
        half = size * 0.5
        def _add_square(cx, cy):
            sq = QGraphicsRectItem(self)
            sq.setRect(cx - half, cy - half, size, size)
            sq.setBrush(QBrush(color))
            sq.setPen(Qt.NoPen)
            sq.setZValue(self.zValue() + 0.6)
            self._corner_squares.append(sq)
        _add_square(left, top)
        _add_square(right, top)
        _add_square(left, bottom)
        _add_square(right, bottom)

class RotationHandle(QGraphicsEllipseItem):
    def __init__(self, canvas_view: 'CanvasView', parent_center_item: RectElementItem,
                 handle_distance_m: float, handle_radius_m: float, color: QColor):
        super().__init__()
        self.canvas_view = canvas_view
        self.center_item = parent_center_item
        self.handle_distance_m = handle_distance_m
        self.handle_radius_m = handle_radius_m
        self._dragging: bool = False
        self._syncing: bool = False
        # Make the handle invisible but still interactive: fully transparent fill, no pen
        self.setBrush(QBrush(QColor(0, 0, 0, 0)))
        self.setPen(Qt.NoPen)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self.setZValue(12)
        self._angle_radians: float = 0.0
        # Remove the visual link line; keep an instance for legacy calls but make it non-drawing
        self.link_line = QGraphicsLineItem()
        self.link_line.setPen(Qt.NoPen)
        self.link_line.setZValue(11)
        self.setRect(-handle_radius_m, -handle_radius_m, handle_radius_m * 2, handle_radius_m * 2)
        self.sync_to_angle()

    def scene_items(self) -> List[QGraphicsItem]:
        # Only the (invisible) handle participates in the scene; the link line is omitted
        return [self]

    def set_angle(self, radians: float):
        self._angle_radians = radians
        self.sync_to_angle()

    def sync_to_angle(self):
        self._syncing = True
        try:
            cx, cy = self.center_item.pos().x(), self.center_item.pos().y()
            angle_scene = -self._angle_radians
            # Place handle at the midpoint of the front (forward-facing) edge of the rectangle
            front_offset_m = float(self.center_item.rect().width()) * 0.5
            hx = cx + math.cos(angle_scene) * front_offset_m
            hy = cy + math.sin(angle_scene) * front_offset_m
            self.setPos(QPointF(hx, hy))
            # No link line to update (kept for legacy but non-drawing)
        finally:
            self._syncing = False

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        if change == QGraphicsItem.ItemPositionChange:
            new_center: QPointF = value
            try:
                cx = self.center_item.pos().x(); cy = self.center_item.pos().y()
                dx = new_center.x() - cx; dy = new_center.y() - cy
                angle_scene = math.atan2(dy, dx)
                # Constrain movement to the front-edge midpoint radius
                front_offset_m = float(self.center_item.rect().width()) * 0.5
                hx = cx + math.cos(angle_scene) * front_offset_m
                hy = cy + math.sin(angle_scene) * front_offset_m
                angle_model = -angle_scene
                self._angle_radians = angle_model
                if not self._syncing and self._dragging:
                    self.canvas_view._on_item_live_rotated(self.center_item.index_in_model, angle_model)
                return QPointF(hx, hy)
            except Exception:
                return value
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        try:
            self.canvas_view.graphics_scene.clearSelection()
            self.center_item.setSelected(True)
            self.canvas_view._on_item_clicked(self.center_item.index_in_model)
        except Exception:
            pass
        self.center_item.setFlag(QGraphicsItem.ItemIsMovable, False)
        self._dragging = True
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        try:
            self.center_item.setFlag(QGraphicsItem.ItemIsMovable, True)
            self.canvas_view._on_rotation_handle_released(self.center_item.index_in_model)
        except Exception:
            pass
        self._dragging = False
        super().mouseReleaseEvent(event)

class HandoffRadiusVisualizer(QGraphicsEllipseItem):
    def __init__(self, canvas_view: 'CanvasView', center_m: QPointF, radius_m: float):
        super().__init__()
        self.canvas_view = canvas_view
        self.radius_m = radius_m
        self.setRect(-radius_m, -radius_m, radius_m * 2, radius_m * 2)
        self.setPos(self.canvas_view._scene_from_model(center_m.x(), center_m.y()))
        self.setPen(HANDOFF_RADIUS_PEN)
        self.setBrush(Qt.NoBrush)
        self.setZValue(20)
        self.setFlag(QGraphicsItem.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)

    def set_center(self, center_m: QPointF):
        self.setPos(self.canvas_view._scene_from_model(center_m.x(), center_m.y()))

    def set_radius(self, radius_m: float):
        self.radius_m = radius_m
        self.setRect(-radius_m, -radius_m, radius_m * 2, radius_m * 2)
