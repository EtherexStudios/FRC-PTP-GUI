"""Graphics items for canvas visualization."""

from __future__ import annotations
from typing import Optional, List, TYPE_CHECKING
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsEllipseItem, QGraphicsItem, QGraphicsLineItem, 
    QGraphicsPolygonItem, QGraphicsRectItem
)

from models.path_model import Waypoint
from .constants import *

if TYPE_CHECKING:
    from .canvas_view import CanvasView


class CircleElementItem(QGraphicsEllipseItem):
    """Circle visualization for translation target elements."""
    
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
    ) -> None:
        """
        Initialize a circle element item.
        
        Args:
            canvas_view: Parent canvas view
            center_m: Center position in meters
            index_in_model: Index in the path model
            filled_color: Fill color (None for no fill)
            outline_color: Outline color (None for no outline)
            dashed_outline: Whether to use dashed outline
            triangle_color: Color for direction triangle (None for no triangle)
        """
        super().__init__()
        self.canvas_view = canvas_view
        self.index_in_model = index_in_model
        
        # Local rect centered at origin so rotation occurs around center
        self.setRect(QRectF(
            -ELEMENT_CIRCLE_RADIUS_M, -ELEMENT_CIRCLE_RADIUS_M, 
            ELEMENT_CIRCLE_RADIUS_M * 2, ELEMENT_CIRCLE_RADIUS_M * 2
        ))
        self.setPos(self.canvas_view._scene_from_model(center_m.x(), center_m.y()))
        
        # Pen/brush
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
        
        # Inscribed triangle as child so it rotates/moves with parent
        self.triangle_item: Optional[QGraphicsPolygonItem] = None
        if triangle_color is not None:
            self.triangle_item = QGraphicsPolygonItem(self)
            self._build_triangle(triangle_color)
            
        # Current rotation in model radians (y-up)
        self._angle_radians: float = 0.0

    def _build_triangle(self, color: QColor) -> None:
        """Build the direction triangle indicator."""
        if self.triangle_item is None:
            return
            
        # Triangle pointing to +X in local coordinates (to the right)
        base_size = ELEMENT_CIRCLE_RADIUS_M * 2 * TRIANGLE_REL_SIZE
        half_base = base_size * 0.5
        height = base_size
        
        # Define a simple isosceles triangle centered at origin pointing right
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

    def set_center(self, center_m: QPointF) -> None:
        """Set the center position in model coordinates."""
        self.setPos(self.canvas_view._scene_from_model(center_m.x(), center_m.y()))

    def set_angle_radians(self, radians: float) -> None:
        """Set the rotation angle in model radians."""
        self._angle_radians = radians
        # Convert model (y-up) to scene (y-down) and set degrees
        angle_scene = -radians
        self.setRotation(math.degrees(angle_scene))

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        """Handle item changes like position updates."""
        if change == QGraphicsItem.ItemPositionChange:
            new_pos: QPointF = value
            # Safety check for canvas_view reference
            if not hasattr(self, 'canvas_view') or self.canvas_view is None:
                return value
            # Constrain movement based on element type and neighbors
            try:
                cx, cy = self.canvas_view._constrain_scene_coords_for_index(
                    self.index_in_model, new_pos.x(), new_pos.y()
                )
                return QPointF(cx, cy)
            except (AttributeError, TypeError, IndexError):
                return value
        elif change == QGraphicsItem.ItemPositionHasChanged:
            # Now that the item's position is committed, notify for visual updates
            if not getattr(self.canvas_view, "_suppress_live_events", False):
                try:
                    x_m, y_m = self.canvas_view._model_from_scene(self.pos().x(), self.pos().y())
                    self.canvas_view._on_item_live_moved(self.index_in_model, x_m, y_m)
                except (AttributeError, TypeError):
                    pass
        return super().itemChange(change, value)

    def mousePressEvent(self, event) -> None:
        """Handle mouse press events."""
        try:
            if hasattr(self, 'canvas_view') and self.canvas_view is not None:
                self.canvas_view._on_item_pressed(self.index_in_model)
                self.canvas_view._on_item_clicked(self.index_in_model)
        except (AttributeError, TypeError):
            pass
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        """Handle mouse release events."""
        try:
            if hasattr(self, 'canvas_view') and self.canvas_view is not None:
                self.canvas_view._on_item_released(self.index_in_model)
        except (AttributeError, TypeError):
            pass
        super().mouseReleaseEvent(event)


class RectElementItem(QGraphicsRectItem):
    """Rectangle visualization for waypoint and rotation elements."""
    
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
    ) -> None:
        """
        Initialize a rectangle element item.
        
        Args:
            canvas_view: Parent canvas view
            center_m: Center position in meters
            index_in_model: Index in the path model
            filled_color: Fill color (None for no fill)
            outline_color: Outline color (None for no outline)
            dashed_outline: Whether to use dashed outline
            triangle_color: Color for direction triangle
        """
        super().__init__()
        self.canvas_view = canvas_view
        self.index_in_model = index_in_model
        
        # Local rect centered at origin so rotation occurs around center
        rw = getattr(self.canvas_view, "robot_length_m", ELEMENT_RECT_WIDTH_M)
        rh = getattr(self.canvas_view, "robot_width_m", ELEMENT_RECT_HEIGHT_M)
        
        # Pen/brush
        pen_width_m = OUTLINE_THICK_M if (outline_color is not None and not dashed_outline) else OUTLINE_THIN_M
        
        # Adjust rect so the OUTER visual edge corresponds exactly to rw x rh in meters
        inset = (pen_width_m if outline_color is not None else 0.0) * 0.5
        self.setRect(QRectF(
            -(rw / 2.0) + inset, -(rh / 2.0) + inset, 
            rw - (inset * 2.0), rh - (inset * 2.0)
        ))
        self.setPos(self.canvas_view._scene_from_model(center_m.x(), center_m.y()))
        
        pen = QPen(outline_color if outline_color is not None else QColor("#000000"),
                   pen_width_m if outline_color is not None else 0.0)
        if dashed_outline:
            pen.setStyle(Qt.DashLine)
        pen.setJoinStyle(Qt.MiterJoin)
        pen.setCapStyle(Qt.SquareCap)
        pen.setCosmetic(False)
        self.setPen(pen)
        
        # For waypoints, don't fill - just show borders
        if filled_color is not None and not isinstance(
            self.canvas_view._path.path_elements[index_in_model], Waypoint
        ):
            self.setBrush(QBrush(filled_color))
        else:
            self.setBrush(Qt.NoBrush)
            
        # Interactivity flags
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setZValue(10)
        
        # Inscribed triangle
        self.triangle_item = QGraphicsPolygonItem(self)
        self._build_triangle(triangle_color)
        
        # Current rotation in model radians (y-up)
        self._angle_radians: float = 0.0

    def _build_triangle(self, color: QColor) -> None:
        """Build the direction triangle indicator."""
        # Triangle pointing to +X in local coordinates (to the right)
        rw = getattr(self.canvas_view, "robot_length_m", ELEMENT_RECT_WIDTH_M)
        rh = getattr(self.canvas_view, "robot_width_m", ELEMENT_RECT_HEIGHT_M)
        base_size = min(rw, rh) * TRIANGLE_REL_SIZE
        half_base = base_size * 0.5
        height = base_size
        
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
            p = QPen(color, OUTLINE_THICK_M)
            p.setJoinStyle(Qt.MiterJoin)
            p.setCapStyle(Qt.SquareCap)
            p.setCosmetic(False)
            self.triangle_item.setPen(p)
        else:
            self.triangle_item.setBrush(QBrush(color))
            self.triangle_item.setPen(OUTLINE_EDGE_PEN)
            
        self.triangle_item.setZValue(self.zValue() + 1)

    def set_center(self, center_m: QPointF) -> None:
        """Set the center position in model coordinates."""
        self.setPos(self.canvas_view._scene_from_model(center_m.x(), center_m.y()))

    def set_angle_radians(self, radians: float) -> None:
        """Set the rotation angle in model radians."""
        self._angle_radians = radians
        angle_scene = -radians
        self.setRotation(math.degrees(angle_scene))

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        """Handle item changes like position updates."""
        if change == QGraphicsItem.ItemPositionChange:
            new_pos: QPointF = value
            if not hasattr(self, 'canvas_view') or self.canvas_view is None:
                return value
            try:
                cx, cy = self.canvas_view._constrain_scene_coords_for_index(
                    self.index_in_model, new_pos.x(), new_pos.y()
                )
                return QPointF(cx, cy)
            except (AttributeError, TypeError, IndexError):
                return value
        elif change == QGraphicsItem.ItemPositionHasChanged:
            if not getattr(self.canvas_view, "_suppress_live_events", False):
                try:
                    x_m, y_m = self.canvas_view._model_from_scene(self.pos().x(), self.pos().y())
                    self.canvas_view._on_item_live_moved(self.index_in_model, x_m, y_m)
                except (AttributeError, TypeError):
                    pass
        return super().itemChange(change, value)

    def mousePressEvent(self, event) -> None:
        """Handle mouse press events."""
        try:
            if hasattr(self, 'canvas_view') and self.canvas_view is not None:
                self.canvas_view._on_item_pressed(self.index_in_model)
                self.canvas_view._on_item_clicked(self.index_in_model)
        except (AttributeError, TypeError):
            pass
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        """Handle mouse release events."""
        try:
            if hasattr(self, 'canvas_view') and self.canvas_view is not None:
                self.canvas_view._on_item_released(self.index_in_model)
        except (AttributeError, TypeError):
            pass
        super().mouseReleaseEvent(event)

    def paint(self, painter, option, widget=None) -> None:
        """Custom painting to disable antialiasing for sharp edges."""
        try:
            painter.setRenderHint(QPainter.Antialiasing, False)
            painter.setRenderHint(QPainter.HighQualityAntialiasing, False)
        except Exception:
            pass
        super().paint(painter, option, widget)


class RotationHandle(QGraphicsEllipseItem):
    """Handle for adjusting rotation of elements."""
    
    def __init__(
        self, 
        canvas_view: 'CanvasView', 
        parent_center_item: RectElementItem, 
        handle_distance_m: float, 
        handle_radius_m: float, 
        color: QColor
    ) -> None:
        """
        Initialize a rotation handle.
        
        Args:
            canvas_view: Parent canvas view
            parent_center_item: The element this handle controls
            handle_distance_m: Distance from center in meters
            handle_radius_m: Radius of the handle in meters
            color: Handle color
        """
        super().__init__()
        self.canvas_view = canvas_view
        self.center_item = parent_center_item
        self.handle_distance_m = handle_distance_m
        self.handle_radius_m = handle_radius_m
        
        # Flags to avoid re-entrant updates
        self._dragging: bool = False
        self._syncing: bool = False
        
        self.setBrush(QBrush(color))
        self.setPen(QPen(QColor("#222222"), 0.02))
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self.setZValue(12)
        
        self._angle_radians: float = 0.0
        self.link_line = QGraphicsLineItem()
        self.link_line.setPen(QPen(QColor("#888888"), HANDLE_LINK_THICKNESS_M))
        self.link_line.setZValue(11)
        
        # Local geometry centered on origin
        self.setRect(QRectF(
            -handle_radius_m, -handle_radius_m, 
            handle_radius_m * 2, handle_radius_m * 2
        ))
        
        # Initial placement
        self.sync_to_angle()

    def scene_items(self) -> List[QGraphicsItem]:
        """Get all scene items associated with this handle."""
        return [self.link_line, self]

    def set_angle(self, radians: float) -> None:
        """Set the handle angle in radians."""
        self._angle_radians = radians
        self.sync_to_angle()

    def sync_to_angle(self) -> None:
        """Synchronize handle position to current angle."""
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
        """Handle item changes during drag."""
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
                # Constrain to ring distance
                hx = cx + math.cos(angle_scene) * self.handle_distance_m
                hy = cy + math.sin(angle_scene) * self.handle_distance_m
                self.link_line.setLine(cx, cy, hx, hy)
                # Convert to model angle (y-up)
                angle_model = -angle_scene
                self._angle_radians = angle_model
                # Only notify when user is actively dragging
                if not self._syncing and self._dragging:
                    if hasattr(self, 'canvas_view') and self.canvas_view is not None:
                        self.canvas_view._on_item_live_rotated(
                            self.center_item.index_in_model, angle_model
                        )
                return QPointF(hx, hy)
            except (AttributeError, TypeError, IndexError):
                return value
        return super().itemChange(change, value)

    def mousePressEvent(self, event) -> None:
        """Handle mouse press to start rotation."""
        try:
            if hasattr(self, 'canvas_view') and self.canvas_view is not None and self.canvas_view.graphics_scene:
                self.canvas_view.graphics_scene.clearSelection()
            if hasattr(self, 'center_item') and self.center_item is not None:
                self.center_item.setSelected(True)
                if hasattr(self, 'canvas_view') and self.canvas_view is not None:
                    self.canvas_view._on_item_clicked(self.center_item.index_in_model)
        except Exception:
            pass
        # Prevent center item from moving while rotating
        if hasattr(self, 'center_item') and self.center_item is not None:
            self.center_item.setFlag(QGraphicsItem.ItemIsMovable, False)
        self._dragging = True
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        """Handle mouse release to finish rotation."""
        if hasattr(self, 'center_item') and self.center_item is not None:
            self.center_item.setFlag(QGraphicsItem.ItemIsMovable, True)
        self._dragging = False
        try:
            if hasattr(self, 'canvas_view') and self.canvas_view is not None:
                self.canvas_view._on_rotation_handle_released(self.center_item.index_in_model)
        except Exception:
            pass
        super().mouseReleaseEvent(event)


class HandoffRadiusVisualizer(QGraphicsEllipseItem):
    """Visualizes the handoff radius for translation and waypoint elements."""
    
    def __init__(self, canvas_view: 'CanvasView', center_m: QPointF, radius_m: float) -> None:
        """
        Initialize a handoff radius visualizer.
        
        Args:
            canvas_view: Parent canvas view
            center_m: Center position in meters
            radius_m: Radius in meters
        """
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
    
    def set_center(self, center_m: QPointF) -> None:
        """Update the center position of the handoff radius circle."""
        self.setPos(self.canvas_view._scene_from_model(center_m.x(), center_m.y()))
    
    def set_radius(self, radius_m: float) -> None:
        """Update the radius of the handoff radius circle."""
        self.radius_m = radius_m
        self.setRect(QRectF(-radius_m, -radius_m, radius_m * 2, radius_m * 2))


class RobotSimItem(QGraphicsRectItem):
    """Graphics item that represents the robot during simulation playback."""
    
    def __init__(self, canvas_view: 'CanvasView') -> None:
        """
        Initialize robot simulation item.
        
        Args:
            canvas_view: Parent canvas view
        """
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

    def set_dimensions(self, length_m: float, width_m: float) -> None:
        """
        Update the robot visualization dimensions.
        
        Args:
            length_m: Robot length in meters
            width_m: Robot width in meters
        """
        try:
            self.setRect(QRectF(-length_m/2.0, -width_m/2.0, length_m, width_m))
            self._build_direction_triangle(length_m, width_m)
        except Exception:
            pass
    
    def _build_direction_triangle(self, robot_length_m: float, robot_width_m: float) -> None:
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
    
    def set_center(self, center_m: QPointF) -> None:
        """Set the robot's center position in model coordinates."""
        scene_pos = self.canvas_view._scene_from_model(center_m.x(), center_m.y())
        self.setPos(scene_pos)
    
    def set_angle_radians(self, radians: float) -> None:
        """Set the robot's rotation angle in model coordinates (y-up)."""
        self._angle_radians = radians
        # Convert model (y-up) to scene (y-down) and set degrees
        angle_scene = -radians
        self.setRotation(math.degrees(angle_scene))