from __future__ import annotations
import math
from typing import List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal, QTimer
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap, QPolygonF, QTransform
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem, QGraphicsLineItem, QGraphicsPixmapItem, QGraphicsPolygonItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView

from models.path_model import Path, PathElement, TranslationTarget, RotationTarget, Waypoint


FIELD_LENGTH_METERS = 16.54
FIELD_WIDTH_METERS = 8.21

# Element visual constants (in meters)
# Defaults; can be overridden at runtime from config
ELEMENT_RECT_WIDTH_M = 0.60
ELEMENT_RECT_HEIGHT_M = 0.60
ELEMENT_CIRCLE_RADIUS_M = 0.20  # radius for circle elements
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
        self.setRect(QRectF(-rw / 2.0, -rh / 2.0, rw, rh))
        self.setPos(self.canvas_view._scene_from_model(center_m.x(), center_m.y()))
        # Pen/brush
        # Use thicker border for solid-outlined elements and thinner for dashed
        thickness = OUTLINE_THICK_M if (outline_color is not None and not dashed_outline) else OUTLINE_THIN_M
        pen = QPen(outline_color if outline_color is not None else QColor("#000000"),
                   thickness if outline_color is not None else 0.0)
        if dashed_outline:
            pen.setStyle(Qt.DashLine)
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
            self.triangle_item.setPen(QPen(color, OUTLINE_THICK_M))
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setTransformationAnchor(QGraphicsView.AnchorViewCenter)
        self._is_fitting = False
        # Guard to avoid emitting elementMoved while performing programmatic updates
        self._suppress_live_events: bool = False
        # Cache of rotation t parameters during an anchor drag (index -> t in [0,1])
        self._rotation_t_cache: Optional[dict[int, float]] = None
        self._anchor_drag_in_progress: bool = False

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
        # After rebuilding, ensure rotation items are properly positioned on their constraint lines
        if self._path is not None:
            self._reproject_rotation_items_in_scene()

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
            pos = self._element_position(element)
            
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
                    pos = self._element_position(element)
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
                pos = self._element_position(element)
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

    def showEvent(self, event):
        super().showEvent(event)
        # Defer initial fit until after show completes
        QTimer.singleShot(0, self._fit_to_scene)

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
            pos = self._element_position(element)

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
        # Adjust rotation items to lie on the segment between their current visible neighbors
        # Maintain the initial t ratio along the segment during an anchor drag
        self._suppress_live_events = True
        try:
            for i, (kind, item, handle) in enumerate(self._items):
                if kind != 'rotation':
                    continue
                prev_pos, next_pos = self._find_neighbor_item_positions(i)
                if prev_pos is None or next_pos is None:
                    # Skip rotation items without valid neighbors
                    continue
                ax, ay = prev_pos
                bx, by = next_pos
                dx = bx - ax
                dy = by - ay
                denom = dx * dx + dy * dy
                if denom <= 0.0:
                    # Skip if neighbors are at the same position
                    continue
                # Use cached t if available to maintain ratio; otherwise compute from current scene position
                if self._rotation_t_cache is not None and i in self._rotation_t_cache:
                    t = self._rotation_t_cache[i]
                else:
                    # Use current scene position for t calculation to ensure accurate positioning
                    try:
                        rx, ry = item.pos().x(), item.pos().y()
                    except (AttributeError, TypeError):
                        continue
                    t = ((rx - ax) * dx + (ry - ay) * dy) / denom
                    if t < 0.0:
                        t = 0.0
                    elif t > 1.0:
                        t = 1.0
                proj_x = ax + t * dx
                proj_y = ay + t * dy
                # Move without emitting signals
                try:
                    item.setPos(proj_x, proj_y)
                    if handle is not None:
                        handle.sync_to_angle()
                except (AttributeError, TypeError):
                    continue
            # Update connecting lines once after all moves
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


