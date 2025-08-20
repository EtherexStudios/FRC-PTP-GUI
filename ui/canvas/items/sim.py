"""Simulation overlay graphics items for the canvas."""
from __future__ import annotations
import math
from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsPolygonItem, QGraphicsItem
from PySide6.QtCore import QPointF
from PySide6.QtGui import QBrush, QColor, QPen, QPolygonF

class RobotSimItem(QGraphicsRectItem):
    def __init__(self, canvas_view: 'CanvasView'):
        super().__init__()
        self.canvas_view = canvas_view
        robot_width_m = 0.5; robot_length_m = 0.5
        try:
            if hasattr(canvas_view, '_project_manager') and canvas_view._project_manager:
                cfg = canvas_view._project_manager.config or {}
                robot_width_m = float(cfg.get('robot_width_meters', robot_width_m))
                robot_length_m = float(cfg.get('robot_length_meters', robot_length_m))
        except Exception:
            pass
        self.setRect(-robot_length_m/2, -robot_width_m/2, robot_length_m, robot_width_m)
        self.setBrush(QBrush(QColor(255,165,0,120)))
        self.setPen(QPen(QColor('#000000'), 0.03))
        self.setZValue(15)
        self.setFlag(QGraphicsItem.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self.triangle_item = QGraphicsPolygonItem(self)
        self._build_triangle(robot_length_m, robot_width_m)
        self._angle_radians = 0.0

    def set_dimensions(self, length_m: float, width_m: float):
        self.setRect(-length_m/2.0, -width_m/2.0, length_m, width_m)
        self._build_triangle(length_m, width_m)

    def _build_triangle(self, robot_length_m: float, robot_width_m: float):
        if not self.triangle_item:
            return
        triangle_size = min(robot_length_m, robot_width_m) * 0.3
        triangle_offset = robot_length_m * 0.3
        points = [QPointF(triangle_offset + triangle_size, 0.0),
                  QPointF(triangle_offset - triangle_size/2, triangle_size/2),
                  QPointF(triangle_offset - triangle_size/2, -triangle_size/2)]
        self.triangle_item.setPolygon(QPolygonF(points))
        self.triangle_item.setBrush(QBrush(QColor('#FFFFFF')))
        self.triangle_item.setPen(QPen(QColor('#000000'), 0.02))
        self.triangle_item.setZValue(self.zValue() + 1)

    def set_center(self, center_m: QPointF):
        self.setPos(self.canvas_view._scene_from_model(center_m.x(), center_m.y()))

    def set_angle_radians(self, radians: float):
        self._angle_radians = radians
        self.setRotation(math.degrees(-radians))
