from __future__ import annotations
import math
import os
from typing import List, Optional, Tuple

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal, QTimer
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap, QPolygonF, QTransform
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem, QGraphicsLineItem, QGraphicsPixmapItem, QGraphicsPolygonItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView

from models.path_model import Path, PathElement, TranslationTarget, RotationTarget, Waypoint, RangedConstraint
from models.simulation import simulate_path, SimResult
from PySide6.QtWidgets import QPushButton, QSlider, QLabel, QWidget, QHBoxLayout, QStyle, QToolButton
from PySide6.QtWidgets import QGraphicsProxyWidget
from PySide6.QtCore import QRect, QSize
from PySide6.QtGui import QIcon, QPixmap, QPainter, QPolygon


FIELD_LENGTH_METERS = 16.54
FIELD_WIDTH_METERS = 8.21

# Element visual constants (in meters)
# Defaults; can be overridden at runtime from config
ELEMENT_RECT_WIDTH_M = 0.60
ELEMENT_RECT_HEIGHT_M = 0.60
ELEMENT_CIRCLE_RADIUS_M = 0.1  # radius for circle elements
TRIANGLE_REL_SIZE = 0.55  # percent of the smaller rect dimension
OUTLINE_THIN_M = 0.06     # thin outline (e.g., rotation dashed)
OUTLINE_THICK_M = 0.06    # thicker outline (e.g., translation aesthetic)
CONNECT_LINE_THICKNESS_M = 0.05
HANDLE_LINK_THICKNESS_M = 0.03
HANDLE_RADIUS_M = 0.12
HANDLE_DISTANCE_M = 0.70
OUTLINE_EDGE_PEN = QPen(QColor("#222222"), 0.02)
# Handoff radius visualizer constants
HANDOFF_RADIUS_PEN = QPen(QColor("#FF00FF"), 0.03)  # Magenta with medium thickness
HANDOFF_RADIUS_PEN.setStyle(Qt.DotLine)  # Dotted line style


class CircleElementItem(QGraphicsEllipseItem):
    def __init__(
        self,
        canvas_view: 'CanvasView',
        center_m: QPointF,
        index_in_model: int,
        *,
        filled_color: Optional[QColor],
        outline_color: Optional[QColor],
        dashed_outline: bool,
        triangle_color: Optional[QColor],
    ):
        super().__init__()
        self.canvas_view = canvas_view
        self.index_in_model = index_in_model
        # Local rect centered at origin so rotation occurs around center
        self.setRect(QRectF(-ELEMENT_CIRCLE_RADIUS_M, -ELEMENT_CIRCLE_RADIUS_M, ELEMENT_CIRCLE_RADIUS_M * 2, ELEMENT_CIRCLE_RADIUS_M * 2))
        self.setPos(self.canvas_view._scene_from_model(center_m.x(), center_m.y()))
        # Pen/brush
        # Use thicker border for solid-outlined elements and thinner for dashed
        thickness = OUTLINE_THICK_M if (outline_color is not None and not dashed_outline) else OUTLINE_THIN_M
        pen = QPen(outline_color if outline_color is not None else QColor("#000000"),
                   thickness if outline_color is not None else 0.0)
        if dashed_outline:
            pen.setStyle(Qt.DashLine)
        self.setPen(pen)
        if filled_color is not None:
            self.setBrush(QBrush(filled_color))
        else:
            self.setBrush(Qt.NoBrush)
        # Interactivity flags
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setZValue(10)
        # Inscribed triangle as child so it rotates/moves with parent (only if triangle_color is provided)
        self.triangle_item = None
        if triangle_color is not None:
            self.triangle_item = QGraphicsPolygonItem(self)
            self._build_triangle(triangle_color)
        # Current rotation in model radians (y-up)
        self._angle_radians: float = 0.0

    def _build_triangle(self, color: QColor):
        if self.triangle_item is None:
            return
        # Triangle pointing to +X in local coordinates (to the right)
        # Size relative to circle diameter
        base_size = ELEMENT_CIRCLE_RADIUS_M * 2 * TRIANGLE_REL_SIZE
        half_base = base_size * 0.5
        height = base_size
        # Define a simple isosceles triangle centered at origin pointing right:
        # points: tip at (height/2, 0), back upper (-height/2, half_base), back lower (-height/2, -half_base)
        points = [
            QPointF(height / 2.0, 0.0),
            QPointF(-height / 2.0, half_base),
            QPointF(-height / 2.0, -half_base),
        ]
        polygon = QPolygonF(points)
        self.triangle_item.setPolygon(polygon)
        self.triangle_item.setBrush(QBrush(color))
        self.triangle_item.setPen(OUTLINE_EDGE_PEN)
        self.triangle_item.setZValue(self.zValue() + 1)

    def set_center(self, center_m: QPointF):
        self.setPos(self.canvas_view._scene_from_model(center_m.x(), center_m.y()))

    def set_angle_radians(self, radians: float):
        self._angle_radians = radians
        # Convert model (y-up) to scene (y-down) and set degrees
        angle_scene = -radians
        self.setRotation(math.degrees(angle_scene))

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        if change == QGraphicsItem.ItemPositionChange:
            new_pos: QPointF = value
            # Safety check for canvas_view reference
            if not hasattr(self, 'canvas_view') or self.canvas_view is None:
                return value
            # Constrain movement based on element type and neighbors
            try:
                cx, cy = self.canvas_view._constrain_scene_coords_for_index(self.index_in_model, new_pos.x(), new_pos.y())
                return QPointF(cx, cy)
            except (AttributeError, TypeError, IndexError):
                return value
        elif change == QGraphicsItem.ItemPositionHasChanged:
            # Now that the item's position is committed, notify for visual updates and model sync
            if not getattr(self.canvas_view, "_suppress_live_events", False):
                try:
                    x_m, y_m = self.canvas_view._model_from_scene(self.pos().x(), self.pos().y())
                    self.canvas_view._on_item_live_moved(self.index_in_model, x_m, y_m)
                except (AttributeError, TypeError):
                    pass
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        # Prepare for potential drag
        try:
            if hasattr(self, 'canvas_view') and self.canvas_view is not None:
                self.canvas_view._on_item_pressed(self.index_in_model)
                self.canvas_view._on_item_clicked(self.index_in_model)
        except (AttributeError, TypeError):
            pass
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        # Clear any drag state
        try:
            if hasattr(self, 'canvas_view') and self.canvas_view is not None:
                self.canvas_view._on_item_released(self.index_in_model)
        except (AttributeError, TypeError):
            pass
        super().mouseReleaseEvent(event)


class RectElementItem(QGraphicsRectItem):
    def __init__(
        self,
        canvas_view: 'CanvasView',
        center_m: QPointF,
        index_in_model: int,
        *,
        filled_color: Optional[QColor],
        outline_color: Optional[QColor],
        dashed_outline: bool,
        triangle_color: QColor,
    ):
        super().__init__()
        self.canvas_view = canvas_view
        self.index_in_model = index_in_model
        # Local rect centered at origin so rotation occurs around center
        rw = getattr(self.canvas_view, "robot_length_m", ELEMENT_RECT_WIDTH_M)
        rh = getattr(self.canvas_view, "robot_width_m", ELEMENT_RECT_HEIGHT_M)
        # Pen/brush
        # Use thicker border for solid-outlined elements and thinner for dashed
        pen_width_m = OUTLINE_THICK_M if (outline_color is not None and not dashed_outline) else OUTLINE_THIN_M
        # Adjust rect so the OUTER visual edge corresponds exactly to rw x rh in meters.
        # Qt strokes are centered on the path; shrinking the rect by the pen width keeps outer size accurate.
        inset = (pen_width_m if outline_color is not None else 0.0) * 0.5
        self.setRect(QRectF(-(rw / 2.0) + inset, -(rh / 2.0) + inset, rw - (inset * 2.0), rh - (inset * 2.0)))
        self.setPos(self.canvas_view._scene_from_model(center_m.x(), center_m.y()))
        pen = QPen(outline_color if outline_color is not None else QColor("#000000"),
                   pen_width_m if outline_color is not None else 0.0)
        if dashed_outline:
            pen.setStyle(Qt.DashLine)
        # Ensure sharp 90-degree corners and predictable pixel-to-pixel rendering
        pen.setJoinStyle(Qt.MiterJoin)
        pen.setCapStyle(Qt.SquareCap)
        pen.setCosmetic(False)
        self.setPen(pen)
        
        # For waypoints, don't fill - just show borders
        if filled_color is not None and not isinstance(self.canvas_view._path.path_elements[index_in_model], Waypoint):
            self.setBrush(QBrush(filled_color))
        else:
            self.setBrush(Qt.NoBrush)
            
        # Interactivity flags
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setZValue(10)
        # Inscribed triangle as child so it rotates/moves with parent
        self.triangle_item = QGraphicsPolygonItem(self)
        self._build_triangle(triangle_color)
        # Current rotation in model radians (y-up)
        self._angle_radians: float = 0.0

    def _build_triangle(self, color: QColor):
        # Triangle pointing to +X in local coordinates (to the right)
        # Size relative to rect
        rw = getattr(self.canvas_view, "robot_length_m", ELEMENT_RECT_WIDTH_M)
        rh = getattr(self.canvas_view, "robot_width_m", ELEMENT_RECT_HEIGHT_M)
        base_size = min(rw, rh) * TRIANGLE_REL_SIZE
        half_base = base_size * 0.5
        height = base_size
        # Define a simple isosceles triangle centered at origin pointing right:
        # points: tip at (height/2, 0), back upper (-height/2, half_base), back lower (-height/2, -half_base)
        points = [
            QPointF(height / 2.0, 0.0),
            QPointF(-height / 2.0, half_base),
            QPointF(-height / 2.0, -half_base),
        ]
        polygon = QPolygonF(points)
        self.triangle_item.setPolygon(polygon)
        
        # For waypoints, only show outline, no fill
        if isinstance(self.canvas_view._path.path_elements[self.index_in_model], Waypoint):
            self.triangle_item.setBrush(Qt.NoBrush)
            # Use the passed color for the outline with thicker line to match box outline
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
        # Convert model (y-up) to scene (y-down) and set degrees
        angle_scene = -radians
        self.setRotation(math.degrees(angle_scene))

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        if change == QGraphicsItem.ItemPositionChange:
            new_pos: QPointF = value
            # Safety check for canvas_view reference
            if not hasattr(self, 'canvas_view') or self.canvas_view is None:
                return value
            # Constrain movement based on element type and neighbors
            try:
                cx, cy = self.canvas_view._constrain_scene_coords_for_index(self.index_in_model, new_pos.x(), new_pos.y())
                return QPointF(cx, cy)
            except (AttributeError, TypeError, IndexError):
                return value
        elif change == QGraphicsItem.ItemPositionHasChanged:
            # Now that the item's position is committed, notify for visual updates and model sync
            if not getattr(self.canvas_view, "_suppress_live_events", False):
                try:
                    x_m, y_m = self.canvas_view._model_from_scene(self.pos().x(), self.pos().y())
                    self.canvas_view._on_item_live_moved(self.index_in_model, x_m, y_m)
                except (AttributeError, TypeError):
                    pass
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        # Prepare for potential drag
        try:
            if hasattr(self, 'canvas_view') and self.canvas_view is not None:
                self.canvas_view._on_item_pressed(self.index_in_model)
                self.canvas_view._on_item_clicked(self.index_in_model)
        except (AttributeError, TypeError):
            pass
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        # Clear any drag state
        try:
            if hasattr(self, 'canvas_view') and self.canvas_view is not None:
                self.canvas_view._on_item_released(self.index_in_model)
        except (AttributeError, TypeError):
            pass
        super().mouseReleaseEvent(event)

    def paint(self, painter, option, widget=None):
        # Disable antialiasing during rectangle paint to keep edges sharp and aligned to pixels
        try:
            painter.setRenderHint(QPainter.Antialiasing, False)
            painter.setRenderHint(QPainter.HighQualityAntialiasing, False)
        except Exception:
            pass
        super().paint(painter, option, widget)


class RobotSimItem(QGraphicsRectItem):
    """Graphics item that represents the robot during simulation playback."""
    
    def __init__(self, canvas_view: 'CanvasView'):
        super().__init__()
        self.canvas_view = canvas_view
        
        # Get robot dimensions from project config
        robot_width_m = 0.5
        robot_length_m = 0.5
        try:
            if hasattr(canvas_view, '_project_manager') and canvas_view._project_manager is not None:
                config = canvas_view._project_manager.config or {}
                robot_width_m = float(config.get('robot_width_meters', 0.5))
                robot_length_m = float(config.get('robot_length_meters', 0.5))
        except Exception:
            pass
        
        # Set up rectangle centered at origin
        self.setRect(QRectF(-robot_length_m/2, -robot_width_m/2, robot_length_m, robot_width_m))
        
        # Visual styling - semi-transparent orange with black outline
        self.setBrush(QBrush(QColor(255, 165, 0, 120)))  # Orange with transparency
        self.setPen(QPen(QColor("#000000"), 0.03))  # Black outline
        
        # Set z-value to appear above field but below UI elements
        self.setZValue(15)
        
        # Not interactive
        self.setFlag(QGraphicsItem.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        
        # Add directional indicator (triangle pointing forward)
        self.triangle_item = QGraphicsPolygonItem(self)
        self._build_direction_triangle(robot_length_m, robot_width_m)
        
        # Current rotation in model radians (y-up)
        self._angle_radians: float = 0.0

    def set_dimensions(self, length_m: float, width_m: float):
        """Update the robot visualization dimensions (meters)."""
        try:
            # Update rectangle geometry
            self.setRect(QRectF(-length_m/2.0, -width_m/2.0, length_m, width_m))
            # Rebuild direction indicator to match new size
            self._build_direction_triangle(length_m, width_m)
        except Exception:
            pass
    
    def _build_direction_triangle(self, robot_length_m: float, robot_width_m: float):
        """Build a triangle to show robot's forward direction."""
        if self.triangle_item is None:
            return
        
        # Triangle pointing forward (+X direction in robot frame)
        triangle_size = min(robot_length_m, robot_width_m) * 0.3
        triangle_offset = robot_length_m * 0.3  # Position it forward on the robot
        
        # Define triangle vertices (pointing right/forward)
        points = [
            QPointF(triangle_offset + triangle_size, 0.0),  # tip
            QPointF(triangle_offset - triangle_size/2, triangle_size/2),  # bottom left
            QPointF(triangle_offset - triangle_size/2, -triangle_size/2),  # top left
        ]
        
        polygon = QPolygonF(points)
        self.triangle_item.setPolygon(polygon)
        self.triangle_item.setBrush(QBrush(QColor("#FFFFFF")))  # White triangle
        self.triangle_item.setPen(QPen(QColor("#000000"), 0.02))  # Black outline
        self.triangle_item.setZValue(self.zValue() + 1)
    
    def set_center(self, center_m: QPointF):
        """Set the robot's center position in model coordinates."""
        scene_pos = self.canvas_view._scene_from_model(center_m.x(), center_m.y())
        self.setPos(scene_pos)
    
    def set_angle_radians(self, radians: float):
        """Set the robot's rotation angle in model coordinates (y-up)."""
        self._angle_radians = radians
        # Convert model (y-up) to scene (y-down) and set degrees
        angle_scene = -radians
        self.setRotation(math.degrees(angle_scene))


class RotationHandle(QGraphicsEllipseItem):
    def __init__(self, canvas_view: 'CanvasView', parent_center_item: RectElementItem, handle_distance_m: float, handle_radius_m: float, color: QColor):
        super().__init__()
        self.canvas_view = canvas_view
        self.center_item = parent_center_item
        self.handle_distance_m = handle_distance_m
        self.handle_radius_m = handle_radius_m
        # Flags to avoid re-entrant updates and distinguish user drags from programmatic syncs
        self._dragging: bool = False
        self._syncing: bool = False
        self.setBrush(QBrush(color))
        self.setPen(QPen(QColor("#222222"), 0.02))
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        # Ensure the handle itself is not selectable to avoid multi-item moves
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self.setZValue(12)
        self._angle_radians: float = 0.0
        self.link_line = QGraphicsLineItem()
        self.link_line.setPen(QPen(QColor("#888888"), HANDLE_LINK_THICKNESS_M))
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
        # Programmatic sync: suppress re-entrant rotation notifications
        self._syncing = True
        try:
            if not hasattr(self, 'center_item') or self.center_item is None:
                return
            cx = self.center_item.pos().x()
            cy = self.center_item.pos().y()
            # Convert model angle (y-up) to scene (y-down)
            angle_scene = -self._angle_radians
            hx = cx + math.cos(angle_scene) * self.handle_distance_m
            hy = cy + math.sin(angle_scene) * self.handle_distance_m
            self.setPos(QPointF(hx, hy))
            self.link_line.setLine(cx, cy, hx, hy)
        except (AttributeError, TypeError):
            pass
        finally:
            self._syncing = False

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        if change == QGraphicsItem.ItemPositionChange:
            new_center: QPointF = value
            try:
                if not hasattr(self, 'center_item') or self.center_item is None:
                    return value
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
                # Only notify the canvas when the user is actively dragging
                if not self._syncing and self._dragging:
                    if hasattr(self, 'canvas_view') and self.canvas_view is not None:
                        self.canvas_view._on_item_live_rotated(self.center_item.index_in_model, angle_model)
                return QPointF(hx, hy)
            except (AttributeError, TypeError, IndexError):
                return value
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        # On rotation start, select the associated center item and clear any previous selection
        # This prevents previously-selected items from being dragged inadvertently
        try:
            if hasattr(self, 'canvas_view') and self.canvas_view is not None and self.canvas_view.graphics_scene:
                self.canvas_view.graphics_scene.clearSelection()
            if hasattr(self, 'center_item') and self.center_item is not None:
                self.center_item.setSelected(True)
                # Notify outside listeners of selection change (sidebar, etc.)
                if hasattr(self, 'canvas_view') and self.canvas_view is not None:
                    self.canvas_view._on_item_clicked(self.center_item.index_in_model)
        except Exception:
            pass
        # Prevent center item from moving while rotating
        if hasattr(self, 'center_item') and self.center_item is not None:
            self.center_item.setFlag(QGraphicsItem.ItemIsMovable, False)
        self._dragging = True
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if hasattr(self, 'center_item') and self.center_item is not None:
            self.center_item.setFlag(QGraphicsItem.ItemIsMovable, True)
        self._dragging = False
        # Notify the canvas that a rotation drag finished so it can record undo
        try:
            if hasattr(self, 'canvas_view') and self.canvas_view is not None:
                self.canvas_view._on_rotation_handle_released(self.center_item.index_in_model)
        except Exception:
            pass
        super().mouseReleaseEvent(event)


class HandoffRadiusVisualizer(QGraphicsEllipseItem):
    """Visualizes the handoff radius for translation and waypoint elements"""
    
    def __init__(self, canvas_view: 'CanvasView', center_m: QPointF, radius_m: float):
        super().__init__()
        self.canvas_view = canvas_view
        self.radius_m = radius_m
        
        # Set the circle to be centered at origin with diameter = 2 * radius
        self.setRect(QRectF(-radius_m, -radius_m, radius_m * 2, radius_m * 2))
        self.setPos(self.canvas_view._scene_from_model(center_m.x(), center_m.y()))
        
        # Set the pen to dotted magenta
        self.setPen(HANDOFF_RADIUS_PEN)
        self.setBrush(Qt.NoBrush)  # No fill, just outline
        
        # Set higher z-value so it appears over all other elements
        self.setZValue(20)
        
        # Not interactive
        self.setFlag(QGraphicsItem.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        
    
    def set_center(self, center_m: QPointF):
        """Update the center position of the handoff radius circle"""
        self.setPos(self.canvas_view._scene_from_model(center_m.x(), center_m.y()))
    
    def set_radius(self, radius_m: float):
        """Update the radius of the handoff radius circle"""
        self.radius_m = radius_m
        self.setRect(QRectF(-radius_m, -radius_m, radius_m * 2, radius_m * 2))


class CanvasView(QGraphicsView):
    # Emitted when the user selects an element on the canvas
    elementSelected = Signal(int)  # index
    # Emitted when the user drags an element to a new location (meters)
    elementMoved = Signal(int, float, float)  # index, x_m, y_m
    # Emitted when the user adjusts a rotation (radians)
    elementRotated = Signal(int, float)  # index, radians
    # Emitted once when the user releases the mouse after dragging an item
    elementDragFinished = Signal(int)  # index
    # Emitted when user presses Delete/Backspace to delete current selection
    deleteSelectedRequested = Signal()
    # Emitted when a rotation drag via the rotation handle finishes
    rotationDragFinished = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        # Ensure the view can receive keyboard focus for shortcuts
        self.setFocusPolicy(Qt.StrongFocus)
        self._is_fitting = False
        # Guard to avoid emitting elementMoved while performing programmatic updates
        self._suppress_live_events: bool = False
        # Cache of rotation t parameters during an anchor drag (index -> t in [0,1])
        self._rotation_t_cache: Optional[dict[int, float]] = None
        self._anchor_drag_in_progress: bool = False

        # Zoom state
        self._zoom_factor: float = 1.0
        self._min_zoom: float = 1.0
        self._max_zoom: float = 8.0

        # Pan state (right-click drag)
        self._is_panning: bool = False
        self._pan_start: Optional[QPoint] = None

        # Robot element rectangle dimensions (configurable at runtime)
        self.robot_length_m: float = ELEMENT_RECT_WIDTH_M
        self.robot_width_m: float = ELEMENT_RECT_HEIGHT_M

        self.graphics_scene = QGraphicsScene(self)
        self.setScene(self.graphics_scene)
        self.graphics_scene.setSceneRect(0, 0, FIELD_LENGTH_METERS, FIELD_WIDTH_METERS)

        self._field_pixmap_item: Optional[QGraphicsPixmapItem] = None
        self._path: Optional[Path] = None
        self._items: List[Tuple[str, RectElementItem, Optional[RotationHandle]]] = []
        self._connect_lines: List[QGraphicsLineItem] = []
        # Store handoff radius visualizers
        self._handoff_visualizers: List[Optional[HandoffRadiusVisualizer]] = []

        self._load_field_background("assets/field25.png")

        # ----- Simulation state -----
        self._sim_result: Optional[SimResult] = None
        self._sim_poses_by_time: dict[float, tuple[float, float, float]] = {}
        self._sim_times_sorted: list[float] = []
        self._sim_total_time_s: float = 0.0
        self._sim_current_time_s: float = 0.0
        self._sim_timer: QTimer = QTimer(self)
        self._sim_timer.setInterval(20)
        self._sim_timer.timeout.connect(self._on_sim_tick)
        self._sim_debounce: QTimer = QTimer(self)
        self._sim_debounce.setSingleShot(True)
        self._sim_debounce.setInterval(200)
        self._sim_debounce.timeout.connect(self._rebuild_simulation_now)

        # Sim robot graphics item
        self._sim_robot_item: Optional[RobotSimItem] = None
        self._ensure_sim_robot_item()
        
        # Trail graphics items
        self._trail_lines: List[QGraphicsLineItem] = []
        self._trail_points: List[Tuple[float, float]] = []

        # Transport controls overlay
        self._transport_proxy: Optional[QGraphicsProxyWidget] = None
        self._transport_widget: Optional[QWidget] = None
        self._transport_btn: Optional[QPushButton] = None
        self._transport_slider: Optional[QSlider] = None
        self._transport_label: Optional[QLabel] = None
        self._build_transport_controls()

        # Ranged constraint preview overlay items (green path)
        self._range_overlay_lines: List[QGraphicsLineItem] = []

    def _load_field_background(self, image_path: str):
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return
        self._field_pixmap_item = QGraphicsPixmapItem(pixmap)
        self._field_pixmap_item.setZValue(-10)
        # Scale pixmap from pixels into meters preserving aspect ratio
        if pixmap.width() > 0 and pixmap.height() > 0:
            # If this is the 2025 field image, use a fixed pixels-per-meter scale
            # of 200.0 px/m so 1 meter in the scene equals 200 pixels in the image.
            s = None
            try:
                if os.path.basename(image_path) == "field25.png":
                    ppm = 200.0  # pixels per meter
                    s = 1.0 / float(ppm)  # meters per pixel
            except Exception:
                s = None
            if s is None:
                # Fallback: scale to fit the field dimensions
                s = min(
                    FIELD_LENGTH_METERS / float(pixmap.width()),
                    FIELD_WIDTH_METERS / float(pixmap.height())
                )
            self._field_pixmap_item.setTransform(QTransform().scale(s, s))
            # Position so bottom-left aligns with (0,0) model → account for scene y-down
            h_scaled = pixmap.height() * s
            self._field_pixmap_item.setPos(0.0, FIELD_WIDTH_METERS - h_scaled)
        self.graphics_scene.addItem(self._field_pixmap_item)

    def _ensure_sim_robot_item(self):
        try:
            if self._sim_robot_item is not None:
                return
            item = RobotSimItem(self)
            self.graphics_scene.addItem(item)
            self._sim_robot_item = item
            item.setVisible(False)
            # Ensure initial size matches current canvas robot dimensions
            try:
                item.set_dimensions(self.robot_length_m, self.robot_width_m)
            except Exception:
                pass
        except Exception:
            pass

    def _update_sim_robot_visibility(self):
        """Show robot overlay when playing or when paused at t>0; hide when paused at t==0 or no data."""
        try:
            if self._sim_robot_item is None:
                return
            # No simulation data -> hide
            if not self._sim_times_sorted:
                self._sim_robot_item.setVisible(False)
                return
            # Playing -> show
            if self._sim_timer.isActive():
                self._sim_robot_item.setVisible(True)
                return
            # Paused: show only if not at start
            if self._sim_current_time_s <= 1e-6:
                self._sim_robot_item.setVisible(False)
            else:
                self._sim_robot_item.setVisible(True)
        except Exception:
            pass

    def _clear_trail(self):
        """Clear all trail line items from the scene."""
        try:
            for line in self._trail_lines:
                if line.scene() is not None:
                    self.graphics_scene.removeItem(line)
            self._trail_lines.clear()
            self._trail_points.clear()
        except Exception:
            pass

    def _setup_trail(self, trail_points: List[Tuple[float, float]]):
        """Set up the trail with the given points."""
        try:
            self._clear_trail()
            self._trail_points = trail_points.copy()
            
            # Create line items for each segment but don't show them yet
            orange_pen = QPen(QColor(255, 165, 0), 0.05)  # Orange trail
            orange_pen.setCapStyle(Qt.RoundCap)
            
            for i in range(len(self._trail_points) - 1):
                line = QGraphicsLineItem()
                line.setPen(orange_pen)
                line.setZValue(14)  # Above field, below robot
                line.setVisible(False)  # Start invisible
                self.graphics_scene.addItem(line)
                self._trail_lines.append(line)
        except Exception:
            pass

    def _update_trail_visibility(self, current_index: int):
        """Update which trail segments are visible up to current_index."""
        try:
            if not self._trail_points or not self._trail_lines:
                return
            
            # Show trail segments up to current position
            for i in range(len(self._trail_lines)):
                line = self._trail_lines[i]
                if i < current_index and i < len(self._trail_points) - 1:
                    # Set line coordinates and make visible
                    x1, y1 = self._trail_points[i]
                    x2, y2 = self._trail_points[i + 1]
                    scene_p1 = self._scene_from_model(x1, y1)
                    scene_p2 = self._scene_from_model(x2, y2)
                    line.setLine(scene_p1.x(), scene_p1.y(), scene_p2.x(), scene_p2.y())
                    line.setVisible(True)
                else:
                    # Hide this segment
                    line.setVisible(False)
        except Exception:
            pass

    def _build_transport_controls(self):
        try:
            if self._transport_widget is not None:
                return
            w = QWidget()
            layout = QHBoxLayout(w)
            layout.setContentsMargins(6, 4, 6, 4)
            layout.setSpacing(8)

            btn = QPushButton()
            btn.setText("▶")
            btn.setFixedWidth(28)
            btn.clicked.connect(self._toggle_play_pause)

            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 0)
            slider.setSingleStep(10)
            slider.setPageStep(100)
            slider.valueChanged.connect(self._on_slider_changed)
            slider.sliderPressed.connect(self._on_slider_pressed)
            slider.sliderReleased.connect(self._on_slider_released)

            lbl = QLabel("0.00 / 0.00 s")
            lbl.setFixedWidth(110)

            layout.addWidget(btn)
            layout.addWidget(slider, 1)
            layout.addWidget(lbl)

            proxy = QGraphicsProxyWidget()
            proxy.setWidget(w)
            proxy.setZValue(30)
            # Keep fixed pixel size on screen
            proxy.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
            self.graphics_scene.addItem(proxy)

            self._transport_proxy = proxy
            self._transport_widget = w
            self._transport_btn = btn
            self._transport_slider = slider
            self._transport_label = lbl

            # Initial placement
            QTimer.singleShot(0, self._position_transport_controls)
        except Exception:
            pass

    # ---------- Ranged constraint overlay ----------
    def clear_constraint_range_overlay(self):
        try:
            if not self._range_overlay_lines:
                return
            for line in self._range_overlay_lines:
                if line is not None and line.scene() is not None:
                    self.graphics_scene.removeItem(line)
            self._range_overlay_lines.clear()
        except Exception:
            self._range_overlay_lines = []

    def show_constraint_range_overlay(self, key: str, start_ordinal: int, end_ordinal: int):
        """Draw a green segment overlay that follows anchor-to-anchor path segments.

        Rules (by examples):
        - Selecting only the first domain element draws nothing.
        - Selecting only the second draws the first segment.
        - Selecting only the third draws only the second segment, etc.
        - Selecting [first,last] draws the whole path.
        - Selecting [first,third] draws from first->second and second->third.
        - Selecting [second,third] draws from first->third.

        Translation-domain keys map directly from anchor ordinals to segments.
        Rotation-domain keys map events (RotationTarget/Waypoint) onto the underlying
        anchor segments they lie on (for Waypoint: the entering segment).
        """
        self.clear_constraint_range_overlay()
        if self._path is None or not self._items:
            return

        lo = int(min(start_ordinal, end_ordinal))
        hi = int(max(start_ordinal, end_ordinal))
        if lo <= 0 and hi <= 0:
            return

        # Gather anchor items (translation/waypoint) in scene order
        anchor_indices: List[int] = []
        for i, (kind, _item, _h) in enumerate(self._items):
            if kind in ("translation", "waypoint"):
                anchor_indices.append(i)

        def _pos_for_index(idx: int) -> Optional[Tuple[float, float]]:
            if idx < 0 or idx >= len(self._items):
                return None
            try:
                _, it, _ = self._items[idx]
                if it is None:
                    return None
                return (it.pos().x(), it.pos().y())
            except Exception:
                return None

        def _draw_segment(segment_j: int):
            # segment_j is 0-based between anchor_j and anchor_{j+1}
            if segment_j < 0 or segment_j >= len(anchor_indices) - 1:
                return
            idx_a = anchor_indices[segment_j]
            idx_b = anchor_indices[segment_j + 1]
            pa = _pos_for_index(idx_a)
            pb = _pos_for_index(idx_b)
            if pa is None or pb is None:
                return
            line = QGraphicsLineItem(pa[0], pa[1], pb[0], pb[1])
            line.setPen(green_pen)
            line.setZValue(25)
            self.graphics_scene.addItem(line)
            self._range_overlay_lines.append(line)

        green_pen = QPen(QColor("#15c915"), CONNECT_LINE_THICKNESS_M)
        green_pen.setCapStyle(Qt.RoundCap)

        # Determine domain type by key
        is_translation_domain = key in ("max_velocity_meters_per_sec", "max_acceleration_meters_per_sec2")

        if is_translation_domain:
            A = len(anchor_indices)
            if A < 2:
                return
            L = max(1, min(lo, A))
            H = max(1, min(hi, A))
            if L > H:
                L, H = H, L
            # Selecting only the first anchor draws nothing
            if L == 1 and H == 1:
                return
            j_start = max(0, L - 2)                 # segment entering L (previous segment)
            j_end = min(A - 2, H - 2)               # segment ending at H
            if j_end < j_start:
                return
            for j in range(j_start, j_end + 1):
                _draw_segment(j)
            return

        # Rotation domain with sub-segmentation at rotation events
        # Build list of events in path order with segment indices and t parameters
        event_item_indices: List[int] = []
        for i, (kind, _item, _h) in enumerate(self._items):
            if kind in ("rotation", "waypoint"):
                event_item_indices.append(i)
        R = len(event_item_indices)
        if R == 0 or len(anchor_indices) < 2:
            return

        # Helper: compute (seg_idx, t) and scene pos for an event item index
        class _Evt:
            def __init__(self, valid: bool, seg_idx: int, t: float, pos: Optional[Tuple[float, float]]):
                self.valid = valid
                self.seg_idx = seg_idx
                self.t = t
                self.pos = pos

        def _pos_on_segment(seg_idx: int, t: float) -> Optional[Tuple[float, float]]:
            if seg_idx < 0 or seg_idx >= len(anchor_indices) - 1:
                return None
            idx_a = anchor_indices[seg_idx]
            idx_b = anchor_indices[seg_idx + 1]
            pa = _pos_for_index(idx_a)
            pb = _pos_for_index(idx_b)
            if pa is None or pb is None:
                return None
            ax, ay = pa
            bx, by = pb
            t = max(0.0, min(1.0, float(t)))
            return (ax + t * (bx - ax), ay + t * (by - ay))

        def _event_info(item_idx: int) -> _Evt:
            try:
                kind, _it, _h = self._items[item_idx]
            except Exception:
                return _Evt(False, -1, 0.0, None)
            # Waypoint → prefer entering segment (anchor ordinal - 1, t = 1.0);
            # if none (this is the very first anchor), fall back to the next segment at t = 0.0
            if kind == "waypoint":
                try:
                    anchor_ord0 = anchor_indices.index(item_idx)
                except ValueError:
                    return _Evt(False, -1, 0.0, None)
                seg_idx = anchor_ord0 - 1
                t_val = 1.0
                if seg_idx < 0:
                    # No entering segment; use the following segment start
                    seg_idx = anchor_ord0
                    t_val = 0.0
                pos = _pos_on_segment(seg_idx, t_val)
                return _Evt(pos is not None, seg_idx, t_val, pos)
            # RotationTarget → between previous and next anchors with t from model
            if kind == "rotation":
                prev_anchor_item_idx = -1
                next_anchor_item_idx = -1
                for j in range(item_idx - 1, -1, -1):
                    knd, _a, _b = self._items[j]
                    if knd in ("translation", "waypoint"):
                        prev_anchor_item_idx = j
                        break
                for j in range(item_idx + 1, len(self._items)):
                    knd, _a, _b = self._items[j]
                    if knd in ("translation", "waypoint"):
                        next_anchor_item_idx = j
                        break
                if prev_anchor_item_idx < 0 or next_anchor_item_idx < 0:
                    return _Evt(False, -1, 0.0, None)
                try:
                    seg_idx = anchor_indices.index(prev_anchor_item_idx)
                except ValueError:
                    return _Evt(False, -1, 0.0, None)
                # Read t from model element
                t_val = 0.0
                try:
                    if self._path is not None and item_idx < len(self._path.path_elements):
                        el = self._path.path_elements[item_idx]
                        if isinstance(el, RotationTarget):
                            t_val = float(getattr(el, 't_ratio', 0.0))
                except Exception:
                    t_val = 0.0
                t_val = max(0.0, min(1.0, t_val))
                pos = _pos_on_segment(seg_idx, t_val)
                return _Evt(pos is not None, seg_idx, t_val, pos)
            return _Evt(False, -1, 0.0, None)

        # Build event info list in path order
        events_info: List[_Evt] = [_event_info(idx) for idx in event_item_indices]

        # Clamp selection to valid ordinal range
        Lr = max(1, min(lo, R))
        Hr = max(1, min(hi, R))
        if Lr > Hr:
            Lr, Hr = Hr, Lr

        # Selecting only the very first event draws nothing (mirror translation's "first only" rule)
        if Lr == 1 and Hr == 1:
            return

        # Helper to draw from (seg_a, t_a) forward to (seg_b, t_b) along path
        def _draw_between(seg_a: int, t_a: float, seg_b: int, t_b: float):
            if seg_a < 0 or seg_b < 0:
                return
            if seg_a == seg_b:
                p0 = _pos_on_segment(seg_a, t_a)
                p1 = _pos_on_segment(seg_b, t_b)
                if p0 is None or p1 is None:
                    return
                line = QGraphicsLineItem(p0[0], p0[1], p1[0], p1[1])
                line.setPen(green_pen)
                line.setZValue(25)
                self.graphics_scene.addItem(line)
                self._range_overlay_lines.append(line)
                return
            # Draw tail of starting segment
            p0 = _pos_on_segment(seg_a, t_a)
            p1 = _pos_on_segment(seg_a, 1.0)
            if p0 is not None and p1 is not None:
                line = QGraphicsLineItem(p0[0], p0[1], p1[0], p1[1])
                line.setPen(green_pen)
                line.setZValue(25)
                self.graphics_scene.addItem(line)
                self._range_overlay_lines.append(line)
            # Draw any full intermediate segments
            for s in range(seg_a + 1, seg_b):
                _draw_segment(s)
            # Draw head of ending segment
            p2 = _pos_on_segment(seg_b, 0.0)
            p3 = _pos_on_segment(seg_b, t_b)
            if p2 is not None and p3 is not None:
                line = QGraphicsLineItem(p2[0], p2[1], p3[0], p3[1])
                line.setPen(green_pen)
                line.setZValue(25)
                self.graphics_scene.addItem(line)
                self._range_overlay_lines.append(line)

        # Prefix: from the previous event (Lr-1) to the first selected event (Lr)
        if Lr - 2 >= 0:
            prev_ev = events_info[Lr - 2]
            first_ev = events_info[Lr - 1]
            if prev_ev.valid and first_ev.valid:
                _draw_between(prev_ev.seg_idx, prev_ev.t, first_ev.seg_idx, first_ev.t)

        # Between consecutive selected events [Lr..Hr]
        for i_ev in range(Lr - 1, Hr - 1):
            a = events_info[i_ev]
            b = events_info[i_ev + 1]
            if a.valid and b.valid:
                _draw_between(a.seg_idx, a.t, b.seg_idx, b.t)
            # If either is invalid, skip drawing for that pair

        # No suffix: stop at the last selected event as per spec

    def _create_arrow_icon(self, direction: str, size: int = 16) -> QIcon:
        """Create an arrow icon for undo/redo buttons."""
        try:
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            
            # Set up pen and brush
            pen = QPen(QColor("#333333"), 2)
            brush = QBrush(QColor("#333333"))
            painter.setPen(pen)
            painter.setBrush(brush)
            
            # Create arrow shape based on direction
            center_x, center_y = size // 2, size // 2
            arrow_size = size // 3
            
            if direction == "undo":  # Left arrow (curved)
                # Draw a simple left-pointing arrow
                arrow = QPolygon([
                    QPoint(center_x - arrow_size, center_y),
                    QPoint(center_x + arrow_size//2, center_y - arrow_size),
                    QPoint(center_x + arrow_size//2, center_y - arrow_size//2),
                    QPoint(center_x, center_y),
                    QPoint(center_x + arrow_size//2, center_y + arrow_size//2),
                    QPoint(center_x + arrow_size//2, center_y + arrow_size)
                ])
            else:  # "redo" - Right arrow
                arrow = QPolygon([
                    QPoint(center_x + arrow_size, center_y),
                    QPoint(center_x - arrow_size//2, center_y - arrow_size),
                    QPoint(center_x - arrow_size//2, center_y - arrow_size//2),
                    QPoint(center_x, center_y),
                    QPoint(center_x - arrow_size//2, center_y + arrow_size//2),
                    QPoint(center_x - arrow_size//2, center_y + arrow_size)
                ])
            
            painter.drawPolygon(arrow)
            painter.end()
            
            return QIcon(pixmap)
        except Exception:
            # Return empty icon on error
            return QIcon()

    def _build_undo_redo_toolbar(self):
        """Build the undo/redo toolbar overlay."""
        try:
            if self._undo_redo_widget is not None:
                return
            
            w = QWidget()
            layout = QHBoxLayout(w)
            layout.setContentsMargins(4, 4, 4, 4)
            layout.setSpacing(2)
            
            # Undo button
            undo_btn = QToolButton()
            undo_btn.setIcon(self._create_arrow_icon("undo", 20))
            undo_btn.setToolTip("Undo")
            undo_btn.setFixedSize(28, 28)
            undo_btn.setStyleSheet("""
                QToolButton {
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    background-color: #f8f9fa;
                }
                QToolButton:hover {
                    background-color: #e9ecef;
                    border-color: #adb5bd;
                }
                QToolButton:pressed {
                    background-color: #dee2e6;
                }
                QToolButton:disabled {
                    background-color: #f8f9fa;
                    border-color: #dee2e6;
                    color: #6c757d;
                }
            """)
            
            # Redo button  
            redo_btn = QToolButton()
            redo_btn.setIcon(self._create_arrow_icon("redo", 20))
            redo_btn.setToolTip("Redo")
            redo_btn.setFixedSize(28, 28)
            redo_btn.setStyleSheet(undo_btn.styleSheet())  # Same style as undo
            
            layout.addWidget(undo_btn)
            layout.addWidget(redo_btn)
            
            # Create proxy widget
            proxy = QGraphicsProxyWidget()
            proxy.setWidget(w)
            proxy.setZValue(30)  # Same level as transport controls
            # Keep fixed pixel size on screen
            proxy.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
            self.graphics_scene.addItem(proxy)
            
            self._undo_redo_proxy = proxy
            self._undo_redo_widget = w
            self._undo_btn = undo_btn
            self._redo_btn = redo_btn
            
            # Initial placement - will be positioned after transport controls
            QTimer.singleShot(0, self._position_undo_redo_toolbar)
        except Exception:
            pass

    def _position_transport_controls(self):
        try:
            if self._transport_proxy is None:
                return
            view_rect: QRect = self.viewport().rect()
            # place 12 px from bottom-left
            px = view_rect.left() + 12
            py = view_rect.bottom() - 12 - (self._transport_widget.height() if self._transport_widget else 28)
            # Map to scene
            scene_pos = self.mapToScene(QPoint(int(px), int(py)))
            self._transport_proxy.setPos(scene_pos)
        except Exception:
            pass

    def set_undo_redo_manager(self, undo_manager):
        """Connect the toolbar buttons to the undo/redo manager."""
        self._undo_manager = undo_manager
        
        if self._undo_btn is not None and self._redo_btn is not None:
            # Connect button signals
            self._undo_btn.clicked.connect(undo_manager.undo)
            self._redo_btn.clicked.connect(undo_manager.redo)
            
            # Connect to undo manager state changes to update button states
            undo_manager.add_callback(self._update_undo_redo_buttons)
            
            # Initial state update
            self._update_undo_redo_buttons()

    def _update_undo_redo_buttons(self):
        """Update the enabled state of undo/redo buttons."""
        try:
            if hasattr(self, '_undo_manager') and self._undo_manager is not None:
                if self._undo_btn is not None:
                    self._undo_btn.setEnabled(self._undo_manager.can_undo())
                    if self._undo_manager.can_undo():
                        desc = self._undo_manager.get_undo_description()
                        self._undo_btn.setToolTip(f"Undo {desc}" if desc else "Undo")
                    else:
                        self._undo_btn.setToolTip("Undo")
                
                if self._redo_btn is not None:
                    self._redo_btn.setEnabled(self._undo_manager.can_redo())
                    if self._undo_manager.can_redo():
                        desc = self._undo_manager.get_redo_description()
                        self._redo_btn.setToolTip(f"Redo {desc}" if desc else "Redo")
                    else:
                        self._redo_btn.setToolTip("Redo")
        except Exception:
            pass

    def _position_undo_redo_toolbar(self):
        """Position the undo/redo toolbar overlay."""
        try:
            if self._undo_redo_proxy is None:
                return
            view_rect: QRect = self.viewport().rect()
            # Place at top-left corner with some padding
            px = view_rect.left() + 12
            py = view_rect.top() + 12
            # Map to scene
            scene_pos = self.mapToScene(QPoint(int(px), int(py)))
            self._undo_redo_proxy.setPos(scene_pos)
        except Exception:
            pass

    def set_path(self, path: Path):
        self._path = path
        # Clear any prior overlay linked to the previous path
        try:
            self.clear_constraint_range_overlay()
        except Exception:
            pass
        self._rebuild_items()
        # After rebuilding, ensure rotation items are properly positioned on their constraint lines
        if self._path is not None:
            self._reproject_rotation_items_in_scene()
        # Request a simulation rebuild
        self.request_simulation_rebuild()

    def set_robot_dimensions(self, length_m: float, width_m: float):
        # Update and rebuild items to apply new sizes
        try:
            self.robot_length_m = float(length_m)
            self.robot_width_m = float(width_m)
        except Exception:
            return
        self._rebuild_items()
        if self._path is not None:
            self._reproject_rotation_items_in_scene()
        # Sim robot uses same size; nothing else needed
        # Also resize the simulation robot visualization
        try:
            self._ensure_sim_robot_item()
            if self._sim_robot_item is not None:
                self._sim_robot_item.set_dimensions(self.robot_length_m, self.robot_width_m)
        except Exception:
            pass

    def set_project_manager(self, project_manager):
        """Set the project manager reference to access default config values"""
        self._project_manager = project_manager

    def update_handoff_radius_visualizers(self):
        """Update handoff radius visualizers based on current model state"""
        if self._path is None or not self._items:
            return
            
        for i, (kind, item, handle) in enumerate(self._items):
            if i >= len(self._handoff_visualizers):
                continue
                
            element = self._path.path_elements[i]
            pos = self._element_position_for_index(i)
            
            # Skip rotation elements - they never get handoff radius visualizers
            if kind == 'rotation':
                # Remove any existing visualizer for rotation elements
                if self._handoff_visualizers[i] is not None:
                    self.graphics_scene.removeItem(self._handoff_visualizers[i])
                    self._handoff_visualizers[i].deleteLater()
                    self._handoff_visualizers[i] = None
                continue
            
            # Determine if we need a handoff radius visualizer
            radius = None
            if isinstance(element, TranslationTarget):
                radius = getattr(element, 'intermediate_handoff_radius_meters', None)
            elif isinstance(element, Waypoint):
                radius = getattr(element.translation_target, 'intermediate_handoff_radius_meters', None)
            
            # If no radius set, try to get default from config
            if radius is None or radius <= 0:
                try:
                    if hasattr(self, '_project_manager') and self._project_manager is not None:
                        default_radius = self._project_manager.get_default_optional_value('intermediate_handoff_radius_meters')
                        if default_radius is not None and default_radius > 0:
                            radius = default_radius
                except:
                    pass
            
            current_visualizer = self._handoff_visualizers[i]
            
            # If we need a visualizer but don't have one, create it
            if radius is not None and radius > 0 and current_visualizer is None:
                new_visualizer = HandoffRadiusVisualizer(self, QPointF(pos[0], pos[1]), radius)
                self.graphics_scene.addItem(new_visualizer)
                self._handoff_visualizers[i] = new_visualizer
            # If we have a visualizer but don't need one, remove it
            elif (radius is None or radius <= 0) and current_visualizer is not None:
                self.graphics_scene.removeItem(current_visualizer)
                current_visualizer.deleteLater()
                self._handoff_visualizers[i] = None
            # If we have a visualizer and need one, update it
            elif radius is not None and radius > 0 and current_visualizer is not None:
                current_visualizer.set_center(QPointF(pos[0], pos[1]))
                current_visualizer.set_radius(radius)
        
        # Request simulation rebuild since handoff radius affects simulation behavior
        self.request_simulation_rebuild()

    def refresh_from_model(self):
        # Update item positions and angles from model without rebuilding structure
        if self._path is None or not self._items:
            return
        self._suppress_live_events = True
        try:
            count = min(len(self._items), len(self._path.path_elements))
            for i in range(count):
                try:
                    kind, item, handle = self._items[i]
                    if item is None:
                        continue
                    # Skip if the C++ object is gone
                    try:
                        if item.scene() is None:
                            continue
                    except RuntimeError:
                        continue
                    element = self._path.path_elements[i]
                    pos = self._element_position_for_index(i)
                    item.set_center(QPointF(pos[0], pos[1]))
                    
                    # Update handoff radius visualizer if it exists
                    if i < len(self._handoff_visualizers) and self._handoff_visualizers[i] is not None:
                        visualizer = self._handoff_visualizers[i]
                        visualizer.set_center(QPointF(pos[0], pos[1]))
                        
                        # Update radius if it changed
                        radius = None
                        if isinstance(element, TranslationTarget):
                            radius = getattr(element, 'intermediate_handoff_radius_meters', None)
                        elif isinstance(element, Waypoint):
                            radius = getattr(element.translation_target, 'intermediate_handoff_radius_meters', None)
                        
                        # If no radius set, try to get default from config
                        if radius is None or radius <= 0:
                            try:
                                if hasattr(self, '_project_manager') and self._project_manager is not None:
                                    default_radius = self._project_manager.get_default_optional_value('intermediate_handoff_radius_meters')
                                    if default_radius is not None and default_radius > 0:
                                        radius = default_radius
                            except:
                                pass
                        
                        if radius is not None and radius > 0:
                            visualizer.set_radius(radius)
                    
                    # Set rotation for waypoint/rotation; translation uses previous orientation source
                    if kind in ("rotation", "waypoint"):
                        angle = self._element_rotation(element)
                    else:
                        angle = self._angle_for_translation_index(i)
                    item.set_angle_radians(angle)
                    if handle is not None:
                        handle.set_angle(angle)
                        # Ensure rotation handle is properly synchronized
                        if kind == "rotation":
                            handle.sync_to_angle()
                except (IndexError, TypeError, AttributeError):
                    # Skip invalid items to prevent crashes
                    continue
        finally:
            self._suppress_live_events = False
        self._update_connecting_lines()
        # Ensure rotation items are properly positioned on their constraint lines
        if self._path is not None:
            self._reproject_rotation_items_in_scene()
        # Request simulation rebuild due to model value changes
        self.request_simulation_rebuild()

    def refresh_rotations_from_model(self):
        # Update only rotation items from the model
        if self._path is None or not self._items:
            return
        max_index = len(self._path.path_elements) - 1
        for i, (kind, item, handle) in enumerate(self._items):
            if i > max_index:
                break
            if kind != 'rotation':
                continue
            try:
                element = self._path.path_elements[i]
                pos = self._element_position_for_index(i)
                item.set_center(QPointF(pos[0], pos[1]))
                if handle is not None:
                    angle = self._element_rotation(element)
                    item.set_angle_radians(angle)
                    handle.set_angle(angle)
                    # Ensure rotation handle is properly synchronized
                    handle.sync_to_angle()
            except (IndexError, TypeError, AttributeError):
                # Skip invalid items to prevent crashes
                continue
        self._update_connecting_lines()
        # Debounce sim rebuild on rotation changes
        self.request_simulation_rebuild()

    def select_index(self, index: int):
        if index is None or index < 0 or index >= len(self._items):
            return
        # visually select (defensively handle deleted/invalid C++ objects)
        try:
            _, item, _ = self._items[index]
        except Exception:
            return
        if item is None:
            return
        # If the underlying C++ object has been deleted, PySide can segfault.
        # Check that the item is still attached to a scene before using it.
        try:
            if getattr(item, 'scene', None) is None:
                return
            if item.scene() is None:
                return
        except RuntimeError:
            # Wrapped C++ object was deleted
            return
        except Exception:
            return
        try:
            if hasattr(self, 'graphics_scene') and self.graphics_scene is not None:
                self.graphics_scene.clearSelection()
            item.setSelected(True)
            # centerOn can crash during rapid resize/fullscreen; defer to event loop
            QTimer.singleShot(0, lambda it=item: self._safe_center_on(it))
        except RuntimeError:
            # e.g., wrapped C++ object has been deleted
            return
        except Exception:
            return

    def _safe_center_on(self, item: QGraphicsItem):
        """Center on item if still valid; separated to use in singleShot."""
        try:
            if item is None:
                return
            # Re-validate C++ object
            if getattr(item, 'scene', None) is None:
                return
            if item.scene() is None:
                return
            self.centerOn(item)
        except RuntimeError:
            return
        except Exception:
            return

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Defer fit to avoid re-entrancy during fullscreen transitions
        QTimer.singleShot(0, self._fit_to_scene)
        # Reposition transport controls after resize
        QTimer.singleShot(0, self._position_transport_controls)
        # Undo/redo toolbar moved to main window
        # QTimer.singleShot(0, self._position_undo_redo_toolbar)

    def showEvent(self, event):
        super().showEvent(event)
        # Defer initial fit until after show completes
        QTimer.singleShot(0, self._fit_to_scene)
        QTimer.singleShot(0, self._position_transport_controls)
        # QTimer.singleShot(0, self._position_undo_redo_toolbar)

    def _fit_to_scene(self):
        if self._is_fitting:
            return
        self._is_fitting = True
        try:
            if hasattr(self, 'graphics_scene') and self.graphics_scene is not None:
                rect = self.graphics_scene.sceneRect()
                if rect.width() > 0 and rect.height() > 0:
                    # Guard against rare crashes during rapid resizes/fullscreen toggles
                    try:
                        self.fitInView(rect, Qt.KeepAspectRatio)
                        # Re-apply any user zoom so it persists across resizes
                        if abs(self._zoom_factor - 1.0) > 1e-6:
                            self.scale(self._zoom_factor, self._zoom_factor)
                    except RuntimeError:
                        # Underlying view/scene not ready
                        pass
        except (AttributeError, TypeError):
            # If there's any error, just return safely
            pass
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
        # Remove handoff radius visualizers
        for visualizer in self._handoff_visualizers:
            if visualizer is not None:
                self.graphics_scene.removeItem(visualizer)
        self._items.clear()
        self._connect_lines.clear()
        self._handoff_visualizers.clear()

    def _rebuild_items(self):
        self._clear_scene_items()
        if self._path is None:
            return

        for i, element in enumerate(self._path.path_elements):
            pos = self._element_position_for_index(i)

            # Choose visuals by element type
            if isinstance(element, TranslationTarget):
                kind = "translation"
                item = CircleElementItem(
                    self,
                    QPointF(pos[0], pos[1]),
                    i,
                    filled_color=QColor("#3aa3ff"),
                    outline_color=QColor("#3aa3ff"),
                    dashed_outline=False,
                    triangle_color=None,
                )
                rotation_handle = None
                item.set_angle_radians(self._angle_for_translation_index(i))
                
                # Add handoff radius visualizer if radius is set or use default from config
                handoff_visualizer = None
                radius = getattr(element, 'intermediate_handoff_radius_meters', None)
                if radius is None or radius <= 0:
                    # Try to get default from project manager if available
                    try:
                        if hasattr(self, '_project_manager') and self._project_manager is not None:
                            default_radius = self._project_manager.get_default_optional_value('intermediate_handoff_radius_meters')
                            if default_radius is not None and default_radius > 0:
                                radius = default_radius
                    except:
                        pass
                
                if radius is not None and radius > 0:
                    handoff_visualizer = HandoffRadiusVisualizer(
                        self, 
                        QPointF(pos[0], pos[1]), 
                        radius
                    )
                    self.graphics_scene.addItem(handoff_visualizer)
                
            elif isinstance(element, RotationTarget):
                kind = "rotation"
                item = RectElementItem(
                    self,
                    QPointF(pos[0], pos[1]),
                    i,
                    filled_color=None,
                    outline_color=QColor("#50c878"),
                    dashed_outline=True,
                    triangle_color=QColor("#50c878"),
                )
                rotation_handle = RotationHandle(self, item, handle_distance_m=HANDLE_DISTANCE_M, handle_radius_m=HANDLE_RADIUS_M, color=QColor("#50c878"))
                item.set_angle_radians(self._element_rotation(element))
                # Ensure rotation handle is properly synchronized
                rotation_handle.set_angle(self._element_rotation(element))
                rotation_handle.sync_to_angle()
                
                # No handoff radius for rotation elements
                handoff_visualizer = None
                
            elif isinstance(element, Waypoint):
                kind = "waypoint"
                item = RectElementItem(
                    self,
                    QPointF(pos[0], pos[1]),
                    i,
                    filled_color=None,  # No fill for waypoints
                    outline_color=QColor("#ff7f3a"),
                    dashed_outline=False,
                    triangle_color=QColor("#ff7f3a"),
                )
                rotation_handle = RotationHandle(self, item, handle_distance_m=HANDLE_DISTANCE_M, handle_radius_m=HANDLE_RADIUS_M, color=QColor("#ff7f3a"))
                # Initialize rotation from waypoint's rotation target
                item.set_angle_radians(self._element_rotation(element))
                rotation_handle.set_angle(self._element_rotation(element))
                rotation_handle.sync_to_angle()
                
                # Add handoff radius visualizer if radius is set on translation target or use default from config
                handoff_visualizer = None
                radius = getattr(element.translation_target, 'intermediate_handoff_radius_meters', None)
                if radius is None or radius <= 0:
                    # Try to get default from project manager if available
                    try:
                        if hasattr(self, '_project_manager') and self._project_manager is not None:
                            default_radius = self._project_manager.get_default_optional_value('intermediate_handoff_radius_meters')
                            if default_radius is not None and default_radius > 0:
                                radius = default_radius
                    except:
                        pass
                
                if radius is not None and radius > 0:
                    handoff_visualizer = HandoffRadiusVisualizer(
                        self, 
                        QPointF(pos[0], pos[1]), 
                        radius
                    )
                    self.graphics_scene.addItem(handoff_visualizer)
                
            else:
                # Unknown, skip
                continue

            # Add to scene
            # Guard against adding invalid items during resize/fullscreen
            try:
                self.graphics_scene.addItem(item)
            except RuntimeError:
                continue
            if rotation_handle is not None:
                for sub in rotation_handle.scene_items():
                    try:
                        self.graphics_scene.addItem(sub)
                    except RuntimeError:
                        continue

            self._items.append((kind, item, rotation_handle))
            self._handoff_visualizers.append(handoff_visualizer)

        # Build connecting lines in hierarchical order
        self._build_connecting_lines()

    def _angle_for_translation_index(self, index: int) -> float:
        # Find the most recent orientation source (RotationTarget or Waypoint) before this index
        if self._path is None or index <= 0:
            return 0.0
        for i in range(index - 1, -1, -1):
            elem = self._path.path_elements[i]
            if isinstance(elem, RotationTarget) or isinstance(elem, Waypoint):
                return self._element_rotation(elem)
        return 0.0

    def _element_position_for_index(self, index: int) -> Tuple[float, float]:
        if self._path is None or index < 0 or index >= len(self._path.path_elements):
            return 0.0, 0.0
        element = self._path.path_elements[index]
        if isinstance(element, TranslationTarget):
            return float(element.x_meters), float(element.y_meters)
        if isinstance(element, Waypoint):
            return float(element.translation_target.x_meters), float(element.translation_target.y_meters)
        if isinstance(element, RotationTarget):
            # Compute position along the segment defined by neighbors using t_ratio
            prev_pos, next_pos = self._neighbor_positions_model(index)
            if prev_pos is None or next_pos is None:
                return 0.0, 0.0
            ax, ay = prev_pos
            bx, by = next_pos
            t = float(getattr(element, "t_ratio", 0.0))
            if t < 0.0:
                t = 0.0
            elif t > 1.0:
                t = 1.0
            return ax + t * (bx - ax), ay + t * (by - ay)
        return 0.0, 0.0

    def _neighbor_positions_model(self, index: int) -> Tuple[Optional[Tuple[float, float]], Optional[Tuple[float, float]]]:
        """Find the model positions of the previous and next anchor elements (TranslationTarget or Waypoint)."""
        if self._path is None:
            return None, None
        # prev
        prev_pos = None
        for i in range(index - 1, -1, -1):
            e = self._path.path_elements[i]
            if isinstance(e, TranslationTarget):
                prev_pos = (float(e.x_meters), float(e.y_meters))
                break
            if isinstance(e, Waypoint):
                prev_pos = (float(e.translation_target.x_meters), float(e.translation_target.y_meters))
                break
        # next
        next_pos = None
        for i in range(index + 1, len(self._path.path_elements)):
            e = self._path.path_elements[i]
            if isinstance(e, TranslationTarget):
                next_pos = (float(e.x_meters), float(e.y_meters))
                break
            if isinstance(e, Waypoint):
                next_pos = (float(e.translation_target.x_meters), float(e.translation_target.y_meters))
                break
        return prev_pos, next_pos

    def _element_rotation(self, element: PathElement) -> float:
        if isinstance(element, RotationTarget):
            return float(element.rotation_radians)
        if isinstance(element, Waypoint):
            return float(element.rotation_target.rotation_radians)
        return 0.0

    def _build_connecting_lines(self):
        self._connect_lines = []
        if not self._items:
            return
        try:
            for i in range(len(self._items) - 1):
                try:
                    _, a, _ = self._items[i]
                    _, b, _ = self._items[i + 1]
                    if a is not None and b is not None:
                        line = QGraphicsLineItem(a.pos().x(), a.pos().y(), b.pos().x(), b.pos().y())
                        line.setPen(QPen(QColor("#cccccc"), CONNECT_LINE_THICKNESS_M))
                        line.setZValue(5)
                        self.graphics_scene.addItem(line)
                        self._connect_lines.append(line)
                except (IndexError, TypeError, AttributeError):
                    # Skip invalid items to prevent crashes
                    continue
        except (IndexError, TypeError):
            # If there's any error, just return safely
            pass

    def _update_connecting_lines(self):
        if not self._items or not self._connect_lines:
            return
        try:
            for i in range(len(self._connect_lines)):
                if i >= len(self._items) - 1:
                    break
                try:
                    _, a, _ = self._items[i]
                    _, b, _ = self._items[i + 1]
                    if a is not None and b is not None:
                        self._connect_lines[i].setLine(a.pos().x(), a.pos().y(), b.pos().x(), b.pos().y())
                except (IndexError, TypeError, AttributeError):
                    # Skip invalid items to prevent crashes
                    continue
        except (IndexError, TypeError):
            # If there's any error, just return safely
            pass

    # Live updates while dragging/rotating for visuals, and emit changes out for model syncing
    def _on_item_live_moved(self, index: int, x_m: float, y_m: float):
        # Safety check to prevent segmentation faults
        if index < 0 or index >= len(self._items):
            return
            
        self._update_connecting_lines()
        # Keep rotation handle linked to moved point
        try:
            kind, _, handle = self._items[index]
            if handle is not None:
                handle.sync_to_angle()
        except (IndexError, TypeError):
            return
            
        # Update handoff radius visualizer position
        if index < len(self._handoff_visualizers) and self._handoff_visualizers[index] is not None:
            try:
                self._handoff_visualizers[index].set_center(QPointF(x_m, y_m))
            except (AttributeError, TypeError):
                pass
            
        # Emit move for the item being dragged first so model updates promptly
        self.elementMoved.emit(index, x_m, y_m)
        # If an anchor moved, reproject any rotation items so they stay inline in real-time
        if kind in ('translation', 'waypoint'):
            self._reproject_rotation_items_in_scene()
        # Live moves: debounce sim rebuild
        self.request_simulation_rebuild()

    def _on_item_live_rotated(self, index: int, angle_radians: float):
        # Safety check to prevent segmentation faults
        if index < 0 or index >= len(self._items):
            return
            
        # Update visual rotation immediately
        try:
            kind, item, handle = self._items[index]
            if kind in ("rotation", "waypoint"):
                item.set_angle_radians(angle_radians)
                if handle is not None:
                    handle.set_angle(angle_radians)
        except (IndexError, TypeError):
            return
            
        self.elementRotated.emit(index, angle_radians)
        # Also update orientations of translation elements that depend on this orientation source
        # A translation's orientation is taken from the nearest previous rotation/waypoint
        for j, (k, it, _) in enumerate(self._items):
            if k == 'translation':
                try:
                    it.set_angle_radians(self._angle_for_translation_index(j))
                except (AttributeError, TypeError):
                    continue
        # Debounce sim rebuild on rotation changes
        self.request_simulation_rebuild()

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

    def _constrain_scene_coords_for_index(self, index: int, x_s: float, y_s: float) -> Tuple[float, float]:
        # Default clamp to field bounds
        x_s, y_s = self._clamp_scene_coords(x_s, y_s)
        if index < 0 or index >= len(self._items):
            return x_s, y_s
        try:
            kind, _, _ = self._items[index]
        except (IndexError, TypeError):
            return x_s, y_s
            
        # Only constrain rotation elements along line segment between nearest translation/waypoint neighbors
        if kind != 'rotation':
            return x_s, y_s
        prev_pos, next_pos = self._find_neighbor_item_positions(index)
        if prev_pos is None or next_pos is None:
            return x_s, y_s
        ax, ay = prev_pos
        bx, by = next_pos
        dx = bx - ax
        dy = by - ay
        denom = dx * dx + dy * dy
        if denom <= 0.0:
            return x_s, y_s
        t = ((x_s - ax) * dx + (y_s - ay) * dy) / denom
        # Clamp to segment
        if t < 0.0:
            t = 0.0
        elif t > 1.0:
            t = 1.0
        proj_x = ax + t * dx
        proj_y = ay + t * dy
        # Ensure still inside field bounds
        return self._clamp_scene_coords(proj_x, proj_y)

    def _find_neighbor_item_positions(self, index: int) -> Tuple[Optional[Tuple[float, float]], Optional[Tuple[float, float]]]:
        # Search upward for nearest translation/waypoint
        prev_pos: Optional[Tuple[float, float]] = None
        for i in range(index - 1, -1, -1):
            try:
                kind, item, _ = self._items[i]
                if kind in ('translation', 'waypoint'):
                    prev_pos = (item.pos().x(), item.pos().y())
                    break
            except (IndexError, TypeError, AttributeError):
                continue
        next_pos: Optional[Tuple[float, float]] = None
        for i in range(index + 1, len(self._items)):
            try:
                kind, item, _ = self._items[i]
                if kind in ('translation', 'waypoint'):
                    next_pos = (item.pos().x(), item.pos().y())
                    break
            except (IndexError, TypeError, AttributeError):
                continue
        return prev_pos, next_pos

    def _reproject_rotation_items_in_scene(self):
        # Position rotation items strictly according to their model t_ratio and current anchor positions
        self._suppress_live_events = True
        try:
            for i, (kind, item, handle) in enumerate(self._items):
                if kind != 'rotation':
                    continue
                # Determine anchor positions from current scene items
                prev_pos, next_pos = self._find_neighbor_item_positions(i)
                if prev_pos is None or next_pos is None:
                    continue
                ax, ay = prev_pos
                bx, by = next_pos
                # Read t_ratio from model
                t = 0.0
                try:
                    if self._path is not None and i < len(self._path.path_elements):
                        rt = self._path.path_elements[i]
                        if isinstance(rt, RotationTarget):
                            t = float(getattr(rt, 't_ratio', 0.0))
                except Exception:
                    t = 0.0
                if t < 0.0:
                    t = 0.0
                elif t > 1.0:
                    t = 1.0
                proj_x = ax + t * (bx - ax)
                proj_y = ay + t * (by - ay)
                try:
                    item.setPos(proj_x, proj_y)
                    if handle is not None:
                        handle.sync_to_angle()
                except (AttributeError, TypeError):
                    continue
            self._update_connecting_lines()
        finally:
            self._suppress_live_events = False

    def _compute_rotation_t_cache(self) -> dict[int, float]:
        t_by_index: dict[int, float] = {}
        for i, (kind, item, _) in enumerate(self._items):
            if kind != 'rotation':
                continue
            prev_pos, next_pos = self._find_neighbor_item_positions(i)
            if prev_pos is None or next_pos is None:
                continue
            ax, ay = prev_pos
            bx, by = next_pos
            dx = bx - ax
            dy = by - ay
            denom = dx * dx + dy * dy
            if denom <= 0.0:
                continue
            rx, ry = item.pos().x(), item.pos().y()
            t = ((rx - ax) * dx + (ry - ay) * dy) / denom
            if t < 0.0:
                t = 0.0
            elif t > 1.0:
                t = 1.0
            t_by_index[i] = float(t)
        return t_by_index

    def _on_item_pressed(self, index: int):
        # If an anchor is pressed, record current t for rotation items
        if index < 0 or index >= len(self._items):
            return
        kind, _, _ = self._items[index]
        if kind in ('translation', 'waypoint'):
            self._anchor_drag_in_progress = True
            self._rotation_t_cache = self._compute_rotation_t_cache()

    def _on_item_released(self, index: int):
        # If an anchor drag just finished, commit current rotation positions to the model
        if self._anchor_drag_in_progress:
            try:
                for i, (kind, item, _) in enumerate(self._items):
                    if kind != 'rotation':
                        continue
                    mx, my = self._model_from_scene(item.pos().x(), item.pos().y())
                    self.elementMoved.emit(i, mx, my)
            finally:
                self._anchor_drag_in_progress = False
                self._rotation_t_cache = None

        # Notify that a drag operation for this item has completed (for any item type)
        self.elementDragFinished.emit(index)
        # Ensure a rebuild after a drag completes
        self.request_simulation_rebuild()

    # ---------------- Simulation API ----------------
    def request_simulation_rebuild(self):
        try:
            self._sim_debounce.start()
        except Exception:
            pass

    def _rebuild_simulation_now(self):
        try:
            if self._path is None:
                self._sim_result = None
                self._sim_poses_by_time = {}
                self._sim_times_sorted = []
                self._sim_total_time_s = 0.0
                self._sim_current_time_s = 0.0
                if self._sim_robot_item is not None:
                    self._sim_robot_item.setVisible(False)
                self._clear_trail()
                if self._transport_slider is not None:
                    self._transport_slider.setRange(0, 0)
                if self._transport_label is not None:
                    self._transport_label.setText("0.00 / 0.00 s")
                return

            # Gather config if project manager exists
            cfg = {}
            try:
                if hasattr(self, "_project_manager") and self._project_manager is not None:
                    cfg = dict(self._project_manager.config or {})
            except Exception:
                cfg = {}

            result = simulate_path(self._path, cfg)
            self._sim_result = result
            self._sim_poses_by_time = result.poses_by_time
            self._sim_times_sorted = result.times_sorted
            self._sim_total_time_s = float(result.total_time_s)
            self._sim_current_time_s = 0.0

            # Update UI controls
            if self._transport_slider is not None:
                self._transport_slider.blockSignals(True)
                self._transport_slider.setRange(0, int(round(self._sim_total_time_s * 1000.0)))
                self._transport_slider.setValue(0)
                self._transport_slider.blockSignals(False)
            if self._transport_label is not None:
                self._transport_label.setText(f"0.00 / {self._sim_total_time_s:.2f} s")

            # Place robot at start and set up trail if available
            if self._sim_robot_item is not None:
                if self._sim_times_sorted:
                    t0 = self._sim_times_sorted[0]
                    x, y, th = self._sim_poses_by_time.get(t0, (0.0, 0.0, 0.0))
                    self._set_sim_robot_pose(x, y, th)
                # Update overlay visibility based on paused/zero rule
                self._update_sim_robot_visibility()
            
            # Set up trail from simulation result
            if hasattr(result, 'trail_points') and result.trail_points:
                self._setup_trail(result.trail_points)
            else:
                self._clear_trail()
        except Exception:
            pass

    def _set_sim_robot_pose(self, x_m: float, y_m: float, theta_rad: float):
        try:
            if self._sim_robot_item is None:
                return
            self._sim_robot_item.set_center(QPointF(x_m, y_m))
            self._sim_robot_item.set_angle_radians(theta_rad)
        except Exception:
            pass

    def _toggle_play_pause(self):
        try:
            if self._sim_timer.isActive():
                self._sim_timer.stop()
                if self._transport_btn is not None:
                    self._transport_btn.setText("▶")
                # Update visibility when pausing
                self._update_sim_robot_visibility()
            else:
                # Do not start if no sim data
                if not self._sim_times_sorted:
                    return
                
                # If we're at or near the end of the simulation, restart from the beginning
                if self._sim_current_time_s >= self._sim_total_time_s:
                    self._sim_current_time_s = 0.0
                    self._seek_to_time(0.0)
                    # Update slider position
                    if self._transport_slider is not None:
                        self._transport_slider.blockSignals(True)
                        self._transport_slider.setValue(0)
                        self._transport_slider.blockSignals(False)
                    # Reset trail to beginning
                    self._update_trail_visibility(0)
                
                self._sim_timer.start()
                if self._transport_btn is not None:
                    self._transport_btn.setText("⏸")
                # Ensure visible when starting
                self._update_sim_robot_visibility()
        except Exception:
            pass

    def _on_slider_changed(self, value: int):
        try:
            # Update current time; if playing, it will be used on next tick
            self._sim_current_time_s = float(value) / 1000.0
            self._seek_to_time(self._sim_current_time_s)
            # Update visibility when seeking via slider
            self._update_sim_robot_visibility()
        except Exception:
            pass

    def _on_slider_pressed(self):
        try:
            if self._sim_timer.isActive():
                self._sim_timer.stop()
                if self._transport_btn is not None:
                    self._transport_btn.setText("▶")
            # Update visibility on pause while scrubbing
            self._update_sim_robot_visibility()
        except Exception:
            pass

    def _on_slider_released(self):
        # Do nothing; user can press play to resume
        pass

    def _seek_to_time(self, t_s: float):
        try:
            if not self._sim_times_sorted or not self._sim_poses_by_time:
                return
            # Find nearest key at or before t_s; linear scan is fine for now; could use bisect
            key_index = 0
            key = 0.0
            for i, tk in enumerate(self._sim_times_sorted):
                if tk <= t_s:
                    key = tk
                    key_index = i
                else:
                    break
            x, y, th = self._sim_poses_by_time.get(key, self._sim_poses_by_time[self._sim_times_sorted[0]])
            self._set_sim_robot_pose(x, y, th)
            
            # Update trail to show path up to current time
            self._update_trail_visibility(key_index)
            
            if self._transport_label is not None:
                self._transport_label.setText(f"{t_s:.2f} / {self._sim_total_time_s:.2f} s")
            # Keep robot overlay visibility consistent with paused/zero rule
            self._update_sim_robot_visibility()
        except Exception:
            pass

    def _on_sim_tick(self):
        try:
            if not self._sim_times_sorted:
                self._sim_timer.stop()
                if self._transport_btn is not None:
                    self._transport_btn.setText("▶")
                return
            self._sim_current_time_s += 0.02
            if self._sim_current_time_s >= self._sim_total_time_s:
                self._sim_current_time_s = self._sim_total_time_s
                self._sim_timer.stop()
                if self._transport_btn is not None:
                    self._transport_btn.setText("▶")
            # Update slider and pose
            if self._transport_slider is not None:
                self._transport_slider.blockSignals(True)
                self._transport_slider.setValue(int(round(self._sim_current_time_s * 1000.0)))
                self._transport_slider.blockSignals(False)
            self._seek_to_time(self._sim_current_time_s)
        except Exception:
            pass



    def keyPressEvent(self, event):
        """Handle Delete/Backspace to request deletion of the current element selection."""
        try:
            if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                self.deleteSelectedRequested.emit()
                event.accept()
                return
            # Toggle play/pause with Spacebar
            if event.key() == Qt.Key_Space:
                self._toggle_play_pause()
                event.accept()
                return
        except Exception:
            pass
        super().keyPressEvent(event)

    def wheelEvent(self, event):
        """Zoom the view with the mouse wheel, anchored under the cursor, with limits."""
        try:
            # Determine scroll delta (support both angleDelta and pixelDelta)
            delta_y = 0
            try:
                delta = event.angleDelta()
                if delta is not None:
                    delta_y = int(delta.y())
            except Exception:
                delta_y = 0
            if delta_y == 0:
                try:
                    pdelta = event.pixelDelta()
                    if pdelta is not None:
                        delta_y = int(pdelta.y())
                except Exception:
                    delta_y = 0

            if delta_y == 0:
                # No usable delta; defer to default behavior
                return super().wheelEvent(event)

            zoom_step = 1.03
            factor = zoom_step if delta_y > 0 else (1.0 / zoom_step)

            # Compute new zoom and clamp
            new_zoom = self._zoom_factor * factor
            if new_zoom < self._min_zoom:
                if self._zoom_factor <= self._min_zoom:
                    return
                factor = self._min_zoom / self._zoom_factor
                self._zoom_factor = self._min_zoom
            elif new_zoom > self._max_zoom:
                if self._zoom_factor >= self._max_zoom:
                    return
                factor = self._max_zoom / self._zoom_factor
                self._zoom_factor = self._max_zoom
            else:
                self._zoom_factor = new_zoom

            # Apply incremental scale; anchor is UnderMouse so it zooms to cursor
            self.scale(factor, factor)
            event.accept()
        except Exception:
            # Fallback to default behavior on error
            try:
                super().wheelEvent(event)
            except Exception:
                pass

    # Internal hook called by RotationHandle on mouse release
    def _on_rotation_handle_released(self, index: int):
        try:
            self.rotationDragFinished.emit(int(index))
        except Exception:
            pass

    def mousePressEvent(self, event):
        """Start panning on right button; otherwise, default behavior."""
        try:
            if event.button() == Qt.RightButton:
                self._is_panning = True
                self._pan_start = event.pos()
                try:
                    self.viewport().setCursor(Qt.ClosedHandCursor)
                except Exception:
                    pass
                event.accept()
                return
        except Exception:
            pass
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """While panning, move view by scrollbar deltas."""
        try:
            if self._is_panning and self._pan_start is not None:
                delta = event.pos() - self._pan_start
                try:
                    hbar = self.horizontalScrollBar()
                    vbar = self.verticalScrollBar()
                    hbar.setValue(hbar.value() - delta.x())
                    vbar.setValue(vbar.value() - delta.y())
                except Exception:
                    pass
                self._pan_start = event.pos()
                event.accept()
                return
        except Exception:
            pass
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Stop panning on right button release; otherwise, default behavior."""
        try:
            if event.button() == Qt.RightButton and self._is_panning:
                self._is_panning = False
                self._pan_start = None
                try:
                    self.viewport().setCursor(Qt.ArrowCursor)
                except Exception:
                    pass
                event.accept()
                return
        except Exception:
            pass
        super().mouseReleaseEvent(event)
