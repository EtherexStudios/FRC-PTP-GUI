"""Refactored modular CanvasView building on decomposed items/components.

NOTE: This is an in-progress extraction from the monolithic ui/canvas.py.
It currently reuses many original private method names for compatibility
with MainWindow and Sidebar interactions. Further pruning can follow.
"""
from __future__ import annotations
import math, os
from typing import List, Optional, Tuple
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsLineItem, QGraphicsItem, QFrame
from PySide6.QtCore import Qt, QPointF, QTimer, QRect, Signal, QPoint
from PySide6.QtGui import QPainter, QPixmap, QTransform, QColor, QPen, QBrush

from models.path_model import Path, PathElement, TranslationTarget, RotationTarget, Waypoint
from models.simulation import simulate_path, SimResult

from .constants import (
    FIELD_LENGTH_METERS, FIELD_WIDTH_METERS, CONNECT_LINE_THICKNESS_M,
    HANDLE_DISTANCE_M, HANDLE_RADIUS_M, ELEMENT_RECT_WIDTH_M, ELEMENT_RECT_HEIGHT_M
)
from .items.elements import CircleElementItem, RectElementItem, RotationHandle, HandoffRadiusVisualizer
from .items.sim import RobotSimItem
from .components.transport import TransportControls

class CanvasView(QGraphicsView):
    # Signals (mirroring original)
    elementSelected = Signal(int)
    elementMoved = Signal(int, float, float)
    elementRotated = Signal(int, float)
    elementDragFinished = Signal(int)
    deleteSelectedRequested = Signal()
    rotationDragFinished = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setFocusPolicy(Qt.StrongFocus)
        # Subtle rounded corners on the canvas frame
        try:
            self.setAttribute(Qt.WA_StyledBackground, True)
            # Keep the frame visually minimal while rounding corners
            self.setFrameShape(QFrame.NoFrame)
            # Apply rounding to both the view and its viewport to ensure clipping
            self.setStyleSheet("QGraphicsView { border-radius: 8px; background: palette(Base); }")
            if self.viewport() is not None:
                try:
                    self.viewport().setAttribute(Qt.WA_StyledBackground, True)
                    self.viewport().setStyleSheet("border-radius: 8px; background: palette(Base);")
                except Exception:
                    pass
        except Exception:
            pass
        self._is_fitting = False
        self._suppress_live_events = False
        self._rotation_t_cache: Optional[dict[int,float]] = None
        self._anchor_drag_in_progress = False
        self._zoom_factor = 1.0
        self._min_zoom = 1.0
        self._max_zoom = 8.0
        self._is_panning = False
        self._pan_start: Optional[QPoint] = None
        self.robot_length_m = ELEMENT_RECT_WIDTH_M
        self.robot_width_m = ELEMENT_RECT_HEIGHT_M
        self.graphics_scene = QGraphicsScene(self)
        self.setScene(self.graphics_scene)
        self.graphics_scene.setSceneRect(0,0,FIELD_LENGTH_METERS, FIELD_WIDTH_METERS)
        self._field_pixmap_item: Optional[QGraphicsPixmapItem] = None
        self._path: Optional[Path] = None
        self._items: List[Tuple[str, RectElementItem, Optional[RotationHandle]]] = []
        self._connect_lines: List[QGraphicsLineItem] = []
        self._handoff_visualizers: List[Optional[HandoffRadiusVisualizer]] = []
        self._load_field_background("assets/field25.png")
        # Simulation state
        self._sim_result: Optional[SimResult] = None
        self._sim_poses_by_time: dict[float, tuple[float,float,float]] = {}
        self._sim_times_sorted: list[float] = []
        self._sim_total_time_s = 0.0
        self._sim_current_time_s = 0.0
        self._sim_timer: QTimer = QTimer(self); self._sim_timer.setInterval(20); self._sim_timer.timeout.connect(self._on_sim_tick)
        self._sim_debounce: QTimer = QTimer(self); self._sim_debounce.setSingleShot(True); self._sim_debounce.setInterval(200); self._sim_debounce.timeout.connect(self._rebuild_simulation_now)
        self._sim_robot_item: Optional[RobotSimItem] = None
        self._ensure_sim_robot_item()
        self._trail_lines: List[QGraphicsLineItem] = []
        self._trail_points: List[Tuple[float,float]] = []
        self.transport = TransportControls(self); self.transport.ensure()
        self._range_overlay_lines: List[QGraphicsLineItem] = []
        self._range_overlay_saved_item_styles: dict[QGraphicsItem, Tuple[QPen, QBrush]] = {}

    # ---------------- Field Background ----------------
    def _load_field_background(self, image_path: str):
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return
        self._field_pixmap_item = QGraphicsPixmapItem(pixmap); self._field_pixmap_item.setZValue(-10)
        if pixmap.width() > 0 and pixmap.height() > 0:
            # Scale the background so it fully fits inside the logical field rectangle
            # while preserving aspect ratio. Previously a hard‑coded PPM (200) was applied
            # for field25.png which could make the scaled pixmap wider than
            # FIELD_LENGTH_METERS, causing the right edge to be clipped when the view
            # fit the sceneRect. We now always apply aspect-fit scaling.
            try:
                scale_w = FIELD_LENGTH_METERS / float(pixmap.width())
                scale_h = FIELD_WIDTH_METERS / float(pixmap.height())
                s = min(scale_w, scale_h)
            except Exception:
                s = 1.0
            self._field_pixmap_item.setTransform(QTransform().scale(s, s))
            # Bottom-align the image within the field height so (0,0) remains top-left in model coords.
            h_scaled = pixmap.height() * s
            w_scaled = pixmap.width() * s
            # If width ends up smaller than field length (letterboxing), center it; else anchor at x=0.
            x_offset = 0.0
            try:
                if w_scaled < FIELD_LENGTH_METERS:
                    x_offset = (FIELD_LENGTH_METERS - w_scaled) / 2.0
            except Exception:
                x_offset = 0.0
            self._field_pixmap_item.setPos(x_offset, FIELD_WIDTH_METERS - h_scaled)
        self.graphics_scene.addItem(self._field_pixmap_item)

    def set_project_manager(self, project_manager):
        self._project_manager = project_manager

    # ------------- Path / Items -------------
    def set_path(self, path: Path):
        self._path = path
        try: self.clear_constraint_range_overlay()
        except Exception: pass
        self._rebuild_items()
        if self._path: self._reproject_rotation_items_in_scene()
        self.request_simulation_rebuild()

    def set_robot_dimensions(self, length_m: float, width_m: float):
        try: self.robot_length_m = float(length_m); self.robot_width_m = float(width_m)
        except Exception: return
        self._rebuild_items()
        if self._path: self._reproject_rotation_items_in_scene()
        try:
            self._ensure_sim_robot_item()
            if self._sim_robot_item: self._sim_robot_item.set_dimensions(self.robot_length_m, self.robot_width_m)
        except Exception: pass

    # ----------- Handoff Radius -----------
    def update_handoff_radius_visualizers(self):
        if self._path is None or not self._items: return
        from models.path_model import TranslationTarget, Waypoint
        for i,(kind,item,_handle) in enumerate(self._items):
            if i >= len(self._handoff_visualizers): continue
            element = self._path.path_elements[i]
            pos = self._element_position_for_index(i)
            if kind == 'rotation':
                if self._handoff_visualizers[i] is not None:
                    self.graphics_scene.removeItem(self._handoff_visualizers[i]); self._handoff_visualizers[i].deleteLater(); self._handoff_visualizers[i]=None
                continue
            radius = None
            if isinstance(element, TranslationTarget): radius = getattr(element,'intermediate_handoff_radius_meters', None)
            elif isinstance(element, Waypoint): radius = getattr(element.translation_target,'intermediate_handoff_radius_meters', None)
            if radius is None or radius <=0:
                try:
                    if hasattr(self,'_project_manager') and self._project_manager:
                        default_radius = self._project_manager.get_default_optional_value('intermediate_handoff_radius_meters')
                        if default_radius and default_radius>0: radius = default_radius
                except Exception: pass
            current = self._handoff_visualizers[i]
            if radius and radius>0 and current is None:
                hv = HandoffRadiusVisualizer(self, QPointF(pos[0], pos[1]), radius); self.graphics_scene.addItem(hv); self._handoff_visualizers[i]=hv
            elif (not radius or radius<=0) and current is not None:
                self.graphics_scene.removeItem(current); current.deleteLater(); self._handoff_visualizers[i]=None
            elif radius and radius>0 and current is not None:
                current.set_center(QPointF(pos[0], pos[1])); current.set_radius(radius)
        self.request_simulation_rebuild()

    def refresh_from_model(self):
        if self._path is None or not self._items: return
        self._suppress_live_events = True
        try:
            count = min(len(self._items), len(self._path.path_elements))
            for i in range(count):
                try:
                    kind,item,handle = self._items[i]; element = self._path.path_elements[i]
                    pos = self._element_position_for_index(i); item.set_center(QPointF(pos[0], pos[1]))
                    if i < len(self._handoff_visualizers) and self._handoff_visualizers[i]:
                        self._handoff_visualizers[i].set_center(QPointF(pos[0], pos[1]))
                    if kind in ('rotation','waypoint'): angle = self._element_rotation(element)
                    else: angle = self._angle_for_translation_index(i)
                    item.set_angle_radians(angle)
                    if handle: handle.set_angle(angle); handle.sync_to_angle()
                except Exception:
                    continue
        finally:
            self._suppress_live_events = False
        self._update_connecting_lines();
        if self._path: self._reproject_rotation_items_in_scene()
        self.request_simulation_rebuild()

    def refresh_rotations_from_model(self):
        if self._path is None or not self._items: return
        max_index = len(self._path.path_elements)-1
        for i,(kind,item,handle) in enumerate(self._items):
            if i>max_index: break
            if kind!='rotation': continue
            try:
                element = self._path.path_elements[i]
                pos = self._element_position_for_index(i)
                item.set_center(QPointF(pos[0], pos[1]))
                if handle:
                    angle = self._element_rotation(element); item.set_angle_radians(angle); handle.set_angle(angle); handle.sync_to_angle()
            except Exception: continue
        self._update_connecting_lines(); self.request_simulation_rebuild()

    def select_index(self, index:int):
        if index is None or index<0 or index>=len(self._items): return
        try: _,item,_ = self._items[index]
        except Exception: return
        if item is None: return
        try:
            if item.scene() is None: return
        except Exception: return
        try:
            self.graphics_scene.clearSelection(); item.setSelected(True); QTimer.singleShot(0, lambda it=item: self._safe_center_on(it))
        except Exception: return

    def _safe_center_on(self, item: QGraphicsItem):
        try:
            if item and item.scene(): self.centerOn(item)
        except Exception: pass

    # ------------- Resize / Show -------------
    def resizeEvent(self, event):
        super().resizeEvent(event); QTimer.singleShot(0, self._fit_to_scene); QTimer.singleShot(0, self.transport.position)

    def showEvent(self, event):
        super().showEvent(event); QTimer.singleShot(0, self._fit_to_scene); QTimer.singleShot(0, self.transport.position)

    def _fit_to_scene(self):
        if self._is_fitting: return
        self._is_fitting=True
        try:
            rect = self.graphics_scene.sceneRect()
            if rect.width()>0 and rect.height()>0:
                try:
                    self.fitInView(rect, Qt.KeepAspectRatio)
                    if abs(self._zoom_factor-1.0)>1e-6: self.scale(self._zoom_factor, self._zoom_factor)
                    # After any fit/scale, reposition transport overlay to viewport corner
                    QTimer.singleShot(0, self.transport.position)
                except Exception: pass
        finally:
            self._is_fitting=False

    # ------------- Item build -------------
    def _clear_scene_items(self):
        for _,item,handle in self._items:
            self.graphics_scene.removeItem(item)
            if handle: [self.graphics_scene.removeItem(sub) for sub in handle.scene_items()]
        for line in self._connect_lines: self.graphics_scene.removeItem(line)
        for viz in self._handoff_visualizers:
            if viz: self.graphics_scene.removeItem(viz)
        self._items.clear(); self._connect_lines.clear(); self._handoff_visualizers.clear()

    def _rebuild_items(self):
        self._clear_scene_items()
        if self._path is None: return
        for i,element in enumerate(self._path.path_elements):
            pos = self._element_position_for_index(i)
            if isinstance(element, TranslationTarget):
                kind="translation"; item = CircleElementItem(self, QPointF(*pos), i, filled_color=QColor('#3aa3ff'), outline_color=QColor('#3aa3ff'), dashed_outline=False, triangle_color=None)
                rotation_handle=None; item.set_angle_radians(self._angle_for_translation_index(i))
                handoff_visualizer=None; radius=getattr(element,'intermediate_handoff_radius_meters', None)
                if (radius is None or radius<=0) and hasattr(self,'_project_manager') and self._project_manager:
                    try:
                        default_radius = self._project_manager.get_default_optional_value('intermediate_handoff_radius_meters')
                        if default_radius and default_radius>0: radius=default_radius
                    except Exception: pass
                if radius and radius>0:
                    hv=HandoffRadiusVisualizer(self, QPointF(*pos), radius); self.graphics_scene.addItem(hv); handoff_visualizer=hv
            elif isinstance(element, RotationTarget):
                kind="rotation"; item = RectElementItem(self, QPointF(*pos), i, filled_color=None, outline_color=QColor('#50c878'), dashed_outline=True, triangle_color=QColor('#50c878'))
                rotation_handle = RotationHandle(self, item, HANDLE_DISTANCE_M, HANDLE_RADIUS_M, QColor('#50c878'))
                ang = self._element_rotation(element); item.set_angle_radians(ang); rotation_handle.set_angle(ang); rotation_handle.sync_to_angle(); handoff_visualizer=None
            elif isinstance(element, Waypoint):
                kind="waypoint"; item = RectElementItem(self, QPointF(*pos), i, filled_color=None, outline_color=QColor('#ff7f3a'), dashed_outline=False, triangle_color=QColor('#ff7f3a'))
                rotation_handle = RotationHandle(self, item, HANDLE_DISTANCE_M, HANDLE_RADIUS_M, QColor('#ff7f3a'))
                ang = self._element_rotation(element); item.set_angle_radians(ang); rotation_handle.set_angle(ang); rotation_handle.sync_to_angle()
                handoff_visualizer=None; radius=getattr(element.translation_target,'intermediate_handoff_radius_meters', None)
                if (radius is None or radius<=0) and hasattr(self,'_project_manager') and self._project_manager:
                    try:
                        default_radius = self._project_manager.get_default_optional_value('intermediate_handoff_radius_meters')
                        if default_radius and default_radius>0: radius=default_radius
                    except Exception: pass
                if radius and radius>0:
                    hv=HandoffRadiusVisualizer(self, QPointF(*pos), radius); self.graphics_scene.addItem(hv); handoff_visualizer=hv
            else:
                continue
            try: self.graphics_scene.addItem(item)
            except Exception: continue
            if rotation_handle:
                for sub in rotation_handle.scene_items():
                    try: self.graphics_scene.addItem(sub)
                    except Exception: continue
            self._items.append((kind,item,rotation_handle))
            self._handoff_visualizers.append(handoff_visualizer)
        self._build_connecting_lines()

    # ------------- Geometry helpers -------------
    def _angle_for_translation_index(self, index:int)->float:
        if self._path is None or index<=0: return 0.0
        for i in range(index-1,-1,-1):
            el=self._path.path_elements[i]
            if isinstance(el,(RotationTarget,Waypoint)): return self._element_rotation(el)
        return 0.0

    def _element_position_for_index(self, index:int)->Tuple[float,float]:
        if self._path is None or index<0 or index>=len(self._path.path_elements): return 0.0,0.0
        element=self._path.path_elements[index]
        if isinstance(element,TranslationTarget): return float(element.x_meters), float(element.y_meters)
        if isinstance(element,Waypoint): return float(element.translation_target.x_meters), float(element.translation_target.y_meters)
        if isinstance(element,RotationTarget):
            prev_pos,next_pos=self._neighbor_positions_model(index)
            if prev_pos is None or next_pos is None: return 0.0,0.0
            ax,ay=prev_pos; bx,by=next_pos; t=float(getattr(element,'t_ratio',0.0)); t=max(0.0,min(1.0,t))
            return ax+t*(bx-ax), ay+t*(by-ay)
        return 0.0,0.0

    def _neighbor_positions_model(self,index:int)->Tuple[Optional[Tuple[float,float]], Optional[Tuple[float,float]]]:
        if self._path is None: return None,None
        prev_pos=None
        for i in range(index-1,-1,-1):
            e=self._path.path_elements[i]
            if isinstance(e,TranslationTarget): prev_pos=(float(e.x_meters),float(e.y_meters)); break
            if isinstance(e,Waypoint): prev_pos=(float(e.translation_target.x_meters),float(e.translation_target.y_meters)); break
        next_pos=None
        for i in range(index+1,len(self._path.path_elements)):
            e=self._path.path_elements[i]
            if isinstance(e,TranslationTarget): next_pos=(float(e.x_meters),float(e.y_meters)); break
            if isinstance(e,Waypoint): next_pos=(float(e.translation_target.x_meters),float(e.translation_target.y_meters)); break
        return prev_pos,next_pos

    def _element_rotation(self, element: PathElement) -> float:
        if isinstance(element, RotationTarget): return float(element.rotation_radians)
        if isinstance(element, Waypoint): return float(element.rotation_target.rotation_radians)
        return 0.0

    def _build_connecting_lines(self):
        self._connect_lines=[]
        if not self._items: return
        for i in range(len(self._items)-1):
            try:
                _,a,_=self._items[i]; _,b,_=self._items[i+1]
                if a and b:
                    line=QGraphicsLineItem(a.pos().x(),a.pos().y(),b.pos().x(),b.pos().y())
                    line.setPen(QPen(QColor('#cccccc'), CONNECT_LINE_THICKNESS_M)); line.setZValue(5)
                    self.graphics_scene.addItem(line); self._connect_lines.append(line)
            except Exception: continue

    def _update_connecting_lines(self):
        if not self._items or not self._connect_lines: return
        for i in range(len(self._connect_lines)):
            if i >= len(self._items)-1: break
            try:
                _,a,_=self._items[i]; _,b,_=self._items[i+1]
                if a and b: self._connect_lines[i].setLine(a.pos().x(),a.pos().y(),b.pos().x(),b.pos().y())
            except Exception: continue

    # -------- Live interactions --------
    def _on_item_live_moved(self, index:int, x_m:float, y_m:float):
        if index<0 or index>=len(self._items): return
        self._update_connecting_lines()
        try:
            kind,_,handle=self._items[index]
            if handle: handle.sync_to_angle()
        except Exception: return
        if index < len(self._handoff_visualizers) and self._handoff_visualizers[index]:
            try: self._handoff_visualizers[index].set_center(QPointF(x_m, y_m))
            except Exception: pass
        self.elementMoved.emit(index, x_m, y_m)
        if kind in ('translation','waypoint'): self._reproject_rotation_items_in_scene()
        self.request_simulation_rebuild()

    def _on_item_live_rotated(self, index:int, angle_radians: float):
        if index<0 or index>=len(self._items): return
        try:
            kind,item,handle=self._items[index]
            if kind in ('rotation','waypoint'):
                item.set_angle_radians(angle_radians)
                if handle: handle.set_angle(angle_radians)
        except Exception: return
        self.elementRotated.emit(index, angle_radians)
        for j,(k,it,_) in enumerate(self._items):
            if k=='translation':
                try: it.set_angle_radians(self._angle_for_translation_index(j))
                except Exception: continue
        self.request_simulation_rebuild()

    def _on_item_clicked(self, index:int): self.elementSelected.emit(index)

    # -------- Coordinate conversion --------
    def _scene_from_model(self, x_m:float, y_m:float)->QPointF: return QPointF(x_m, FIELD_WIDTH_METERS - y_m)
    def _model_from_scene(self, x_s:float, y_s:float)->Tuple[float,float]: return float(x_s), float(FIELD_WIDTH_METERS - y_s)
    def _clamp_scene_coords(self,x_s:float,y_s:float)->Tuple[float,float]:
        return max(0.0,min(x_s,FIELD_LENGTH_METERS)), max(0.0,min(y_s,FIELD_WIDTH_METERS))

    def _constrain_scene_coords_for_index(self,index:int,x_s:float,y_s:float)->Tuple[float,float]:
        x_s,y_s=self._clamp_scene_coords(x_s,y_s)
        if index<0 or index>=len(self._items): return x_s,y_s
        try: kind,_,_ = self._items[index]
        except Exception: return x_s,y_s
        if kind!='rotation': return x_s,y_s
        prev_pos,next_pos=self._find_neighbor_item_positions(index)
        if prev_pos is None or next_pos is None: return x_s,y_s
        ax,ay=prev_pos; bx,by=next_pos; dx=bx-ax; dy=by-ay; denom=dx*dx+dy*dy
        if denom<=0: return x_s,y_s
        t=((x_s-ax)*dx + (y_s-ay)*dy)/denom; t=max(0.0,min(1.0,t));
        proj_x=ax+t*dx; proj_y=ay+t*dy; return self._clamp_scene_coords(proj_x, proj_y)

    def _find_neighbor_item_positions(self,index:int)->Tuple[Optional[Tuple[float,float]], Optional[Tuple[float,float]]]:
        prev_pos=None
        for i in range(index-1,-1,-1):
            try:
                kind,item,_=self._items[i]
                if kind in ('translation','waypoint'): prev_pos=(item.pos().x(), item.pos().y()); break
            except Exception: continue
        next_pos=None
        for i in range(index+1,len(self._items)):
            try:
                kind,item,_=self._items[i]
                if kind in ('translation','waypoint'): next_pos=(item.pos().x(), item.pos().y()); break
            except Exception: continue
        return prev_pos,next_pos

    def _reproject_rotation_items_in_scene(self):
        self._suppress_live_events=True
        try:
            for i,(kind,item,handle) in enumerate(self._items):
                if kind!='rotation': continue
                prev_pos,next_pos=self._find_neighbor_item_positions(i)
                if prev_pos is None or next_pos is None: continue
                ax,ay=prev_pos; bx,by=next_pos
                t=0.0
                try:
                    if self._path and i < len(self._path.path_elements):
                        rt=self._path.path_elements[i]
                        if isinstance(rt, RotationTarget): t=float(getattr(rt,'t_ratio',0.0))
                except Exception: t=0.0
                t=max(0.0,min(1.0,t))
                proj_x=ax+t*(bx-ax); proj_y=ay+t*(by-ay)
                try: item.setPos(proj_x, proj_y);
                except Exception: continue
                if handle: handle.sync_to_angle()
            self._update_connecting_lines()
        finally: self._suppress_live_events=False

    def _compute_rotation_t_cache(self)->dict[int,float]:
        t_by_index={}
        for i,(kind,item,_) in enumerate(self._items):
            if kind!='rotation': continue
            prev_pos,next_pos=self._find_neighbor_item_positions(i)
            if prev_pos is None or next_pos is None: continue
            ax,ay=prev_pos; bx,by=next_pos; dx=bx-ax; dy=by-ay; denom=dx*dx+dy*dy
            if denom<=0: continue
            rx,ry=item.pos().x(), item.pos().y(); t=((rx-ax)*dx+(ry-ay)*dy)/denom; t=max(0.0,min(1.0,t)); t_by_index[i]=float(t)
        return t_by_index

    def _on_item_pressed(self,index:int):
        if index<0 or index>=len(self._items): return
        kind,_,_=self._items[index]
        if kind in ('translation','waypoint'):
            self._anchor_drag_in_progress=True
            self._rotation_t_cache=self._compute_rotation_t_cache()

    def _on_item_released(self,index:int):
        if self._anchor_drag_in_progress:
            try:
                for i,(kind,item,_) in enumerate(self._items):
                    if kind!='rotation': continue
                    mx,my=self._model_from_scene(item.pos().x(), item.pos().y())
                    self.elementMoved.emit(i, mx, my)
            finally:
                self._anchor_drag_in_progress=False; self._rotation_t_cache=None
        self.elementDragFinished.emit(index); self.request_simulation_rebuild()

    # -------- Simulation API (subset) --------
    def request_simulation_rebuild(self):
        try: self._sim_debounce.start()
        except Exception: pass

    def _ensure_sim_robot_item(self):
        try:
            if self._sim_robot_item: return
            item=RobotSimItem(self); self.graphics_scene.addItem(item); self._sim_robot_item=item; item.setVisible(False)
            try: item.set_dimensions(self.robot_length_m, self.robot_width_m)
            except Exception: pass
        except Exception: pass

    def _update_sim_robot_visibility(self):
        try:
            if self._sim_robot_item is None: return
            if not self._sim_times_sorted: self._sim_robot_item.setVisible(False); return
            if self._sim_timer.isActive(): self._sim_robot_item.setVisible(True); return
            if self._sim_current_time_s <= 1e-6: self._sim_robot_item.setVisible(False)
            else: self._sim_robot_item.setVisible(True)
        except Exception: pass

    def _clear_trail(self):
        try:
            for line in self._trail_lines:
                if line.scene(): self.graphics_scene.removeItem(line)
            self._trail_lines.clear(); self._trail_points.clear()
        except Exception: pass

    def _setup_trail(self, trail_points: List[Tuple[float,float]]):
        try:
            self._clear_trail(); self._trail_points=trail_points.copy()
            orange_pen=QPen(QColor(255,165,0), 0.05); orange_pen.setCapStyle(Qt.RoundCap)
            for i in range(len(self._trail_points)-1):
                line=QGraphicsLineItem(); line.setPen(orange_pen); line.setZValue(14); line.setVisible(False); self.graphics_scene.addItem(line); self._trail_lines.append(line)
        except Exception: pass

    def _update_trail_visibility(self,current_index:int):
        try:
            if not self._trail_points or not self._trail_lines: return
            for i,line in enumerate(self._trail_lines):
                if i < current_index and i < len(self._trail_points)-1:
                    x1,y1=self._trail_points[i]; x2,y2=self._trail_points[i+1]
                    p1=self._scene_from_model(x1,y1); p2=self._scene_from_model(x2,y2)
                    line.setLine(p1.x(),p1.y(),p2.x(),p2.y()); line.setVisible(True)
                else: line.setVisible(False)
        except Exception: pass

    # Transport control callbacks (public subset kept for TransportControls wiring)
    def _toggle_play_pause(self):
        try:
            if self._sim_timer.isActive():
                self._sim_timer.stop();
                if self.transport.btn: self.transport.btn.setText('▶')
                self._update_sim_robot_visibility()
            else:
                if not self._sim_times_sorted: return
                if self._sim_current_time_s >= self._sim_total_time_s:
                    self._sim_current_time_s=0.0; self._seek_to_time(0.0)
                    if self.transport.slider:
                        self.transport.slider.blockSignals(True); self.transport.slider.setValue(0); self.transport.slider.blockSignals(False)
                    self._update_trail_visibility(0)
                self._sim_timer.start();
                if self.transport.btn: self.transport.btn.setText('⏸')
                self._update_sim_robot_visibility()
        except Exception: pass

    def _on_slider_changed(self, value:int):
        try:
            self._sim_current_time_s=float(value)/1000.0; self._seek_to_time(self._sim_current_time_s); self._update_sim_robot_visibility()
        except Exception: pass

    def _on_slider_pressed(self):
        try:
            if self._sim_timer.isActive(): self._sim_timer.stop();
            if self.transport.btn: self.transport.btn.setText('▶')
            self._update_sim_robot_visibility()
        except Exception: pass

    def _on_slider_released(self):
        pass

    def _seek_to_time(self,t_s:float):
        try:
            if not self._sim_times_sorted or not self._sim_poses_by_time: return
            key_index=0; key=0.0
            for i,tk in enumerate(self._sim_times_sorted):
                if tk <= t_s: key=tk; key_index=i
                else: break
            x,y,th=self._sim_poses_by_time.get(key, self._sim_poses_by_time[self._sim_times_sorted[0]])
            self._set_sim_robot_pose(x,y,th); self._update_trail_visibility(key_index)
            if self.transport.label: self.transport.label.setText(f"{t_s:.2f} / {self._sim_total_time_s:.2f} s")
            self._update_sim_robot_visibility()
        except Exception: pass

    def _on_sim_tick(self):
        try:
            if not self._sim_times_sorted:
                self._sim_timer.stop();
                if self.transport.btn: self.transport.btn.setText('▶'); return
            self._sim_current_time_s += 0.02
            if self._sim_current_time_s >= self._sim_total_time_s:
                self._sim_current_time_s = self._sim_total_time_s; self._sim_timer.stop();
                if self.transport.btn: self.transport.btn.setText('▶')
            if self.transport.slider:
                self.transport.slider.blockSignals(True); self.transport.slider.setValue(int(round(self._sim_current_time_s*1000.0))); self.transport.slider.blockSignals(False)
            self._seek_to_time(self._sim_current_time_s)
        except Exception: pass

    def _set_sim_robot_pose(self,x_m:float,y_m:float,theta_rad:float):
        try:
            if not self._sim_robot_item: return
            self._sim_robot_item.set_center(QPointF(x_m,y_m)); self._sim_robot_item.set_angle_radians(theta_rad)
        except Exception: pass

    def _rebuild_simulation_now(self):
        try:
            if self._path is None:
                self._sim_result=None; self._sim_poses_by_time={}; self._sim_times_sorted=[]; self._sim_total_time_s=0.0; self._sim_current_time_s=0.0
                if self._sim_robot_item: self._sim_robot_item.setVisible(False)
                self._clear_trail()
                if self.transport.slider: self.transport.slider.setRange(0,0)
                if self.transport.label: self.transport.label.setText('0.00 / 0.00 s')
                return
            cfg={}
            try:
                if hasattr(self,'_project_manager') and self._project_manager: cfg=dict(self._project_manager.config or {})
            except Exception: cfg={}
            result=simulate_path(self._path, cfg); self._sim_result=result
            self._sim_poses_by_time=result.poses_by_time; self._sim_times_sorted=result.times_sorted
            self._sim_total_time_s=float(result.total_time_s); self._sim_current_time_s=0.0
            if self.transport.slider:
                self.transport.slider.blockSignals(True)
                self.transport.slider.setRange(0,int(round(self._sim_total_time_s*1000.0)))
                self.transport.slider.setValue(0)
                self.transport.slider.blockSignals(False)
            if self.transport.label:
                self.transport.label.setText(f"0.00 / {self._sim_total_time_s:.2f} s")
            if self._sim_robot_item and self._sim_times_sorted:
                t0=self._sim_times_sorted[0]; x,y,th=self._sim_poses_by_time.get(t0, (0.0,0.0,0.0)); self._set_sim_robot_pose(x,y,th); self._update_sim_robot_visibility()
            if hasattr(result,'trail_points') and result.trail_points: self._setup_trail(result.trail_points)
            else: self._clear_trail()
        except Exception: pass

    # -------- Keyboard & mouse --------
    def keyPressEvent(self,event):
        try:
            if event.key() in (Qt.Key_Delete, Qt.Key_Backspace): self.deleteSelectedRequested.emit(); event.accept(); return
            if event.key()==Qt.Key_Space: self._toggle_play_pause(); event.accept(); return
        except Exception: pass
        super().keyPressEvent(event)

    def wheelEvent(self,event):
        try:
            delta_y=0; delta=event.angleDelta();
            if delta: delta_y=int(delta.y())
            if delta_y==0:
                pdelta=event.pixelDelta();
                if pdelta: delta_y=int(pdelta.y())
            if delta_y==0: return super().wheelEvent(event)
            zoom_step=1.03; factor=zoom_step if delta_y>0 else (1.0/zoom_step)
            new_zoom=self._zoom_factor*factor
            if new_zoom < self._min_zoom:
                if self._zoom_factor <= self._min_zoom: return
                factor=self._min_zoom/self._zoom_factor; self._zoom_factor=self._min_zoom
            elif new_zoom > self._max_zoom:
                if self._zoom_factor >= self._max_zoom: return
                factor=self._max_zoom/self._zoom_factor; self._zoom_factor=self._max_zoom
            else: self._zoom_factor=new_zoom
            self.scale(factor,factor); event.accept()
            # Keep transport overlay anchored after zooming
            try: self.transport.position()
            except Exception: pass
        except Exception:
            try: super().wheelEvent(event)
            except Exception: pass

    def _on_rotation_handle_released(self,index:int):
        try: self.rotationDragFinished.emit(int(index))
        except Exception: pass

    def _should_start_pan(self, pos) -> bool:
        """Return True if a left-click at view position pos should start panning.
        Pan on empty/background areas; avoid panning on interactive items or the
        transport overlay.
        """
        try:
            item = self.itemAt(pos)
            if item is None:
                return True
            # Avoid panning when clicking the transport overlay
            from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsProxyWidget
            if isinstance(item, QGraphicsProxyWidget):
                return False
            # Allow panning when clicking the background pixmap
            if isinstance(item, QGraphicsPixmapItem):
                return True
            # Otherwise, assume it's an interactive scene item; don't pan
            return False
        except Exception:
            return False

    def mousePressEvent(self,event):
        try:
            # Use left-click to pan on empty/background (not on interactive items)
            if event.button()==Qt.LeftButton and self._should_start_pan(event.pos()):
                self._is_panning=True; self._pan_start=event.pos(); self.viewport().setCursor(Qt.ClosedHandCursor); event.accept(); return
        except Exception: pass
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        try:
            if self._is_panning and self._pan_start is not None:
                delta=event.pos()-self._pan_start
                hbar=self.horizontalScrollBar(); vbar=self.verticalScrollBar(); hbar.setValue(hbar.value()-delta.x()); vbar.setValue(vbar.value()-delta.y()); self._pan_start=event.pos(); event.accept(); return
        except Exception: pass
        super().mouseMoveEvent(event)

        # Reposition overlay when the view scrolls due to any movement
        try: self.transport.position()
        except Exception: pass

    def scrollContentsBy(self, dx: int, dy: int):
        # Called for any programmatic or inertial scroll; keep overlay anchored
        try:
            super().scrollContentsBy(dx, dy)
        finally:
            try: self.transport.position()
            except Exception: pass

    def mouseReleaseEvent(self,event):
        try:
            if event.button()==Qt.LeftButton and self._is_panning:
                self._is_panning=False; self._pan_start=None; self.viewport().setCursor(Qt.ArrowCursor); event.accept(); return
        except Exception: pass
        super().mouseReleaseEvent(event)

    # ---- Constraint overlay (kept simplified pass-through) ----
    def clear_constraint_range_overlay(self):
        # Restore any temporarily modified item styles
        try:
            for it, (old_pen, old_brush) in list(self._range_overlay_saved_item_styles.items()):
                try:
                    if hasattr(it, 'setPen') and old_pen is not None:
                        it.setPen(old_pen)
                    if hasattr(it, 'setBrush') and old_brush is not None:
                        it.setBrush(old_brush)
                except Exception:
                    pass
        finally:
            self._range_overlay_saved_item_styles.clear()

        if not self._range_overlay_lines: return
        for line in self._range_overlay_lines:
            if line and line.scene(): self.graphics_scene.removeItem(line)
        self._range_overlay_lines.clear()

    def show_constraint_range_overlay(self, key: str, start_ordinal:int, end_ordinal:int):
        # Simplified placeholder: leaving original logic in monolithic file for now.
        # Future work: Extract overlay-building logic similarly.
        self.clear_constraint_range_overlay()
        if self._path is None or not self._items: return
        # Choose anchor domain based on constraint key (translation vs rotation)
        rotation_keys = ("max_velocity_deg_per_sec", "max_acceleration_deg_per_sec2")
        is_rotation_domain = key in rotation_keys
        if is_rotation_domain:
            anchors=[(i,it) for i,(k,it,_h) in enumerate(self._items) if k in ('rotation','waypoint')]
        else:
            anchors=[(i,it) for i,(k,it,_h) in enumerate(self._items) if k in ('translation','waypoint')]
        if not anchors: return
        lo=int(min(start_ordinal,end_ordinal)); hi=int(max(start_ordinal,end_ordinal))
        green_pen=QPen(QColor('#15c915'), CONNECT_LINE_THICKNESS_M); green_pen.setCapStyle(Qt.RoundCap)
        if lo<1: lo=1
        if hi>len(anchors): hi=len(anchors)
        # If left handle is at the far left, tint the appropriate first element while previewing
        if lo == 1:
            try:
                first_item = None
                if is_rotation_domain:
                    for kind, it, _h in self._items:
                        if kind in ('rotation','waypoint'):
                            first_item = it
                            break
                else:
                    if self._items:
                        first_item = self._items[0][1]
                # Save current styles once per overlay
                if first_item is not None:
                    try:
                        old_pen = first_item.pen() if hasattr(first_item, 'pen') else None
                    except Exception:
                        old_pen = None
                    try:
                        old_brush = first_item.brush() if hasattr(first_item, 'brush') else None
                    except Exception:
                        old_brush = None
                    if first_item not in self._range_overlay_saved_item_styles:
                        self._range_overlay_saved_item_styles[first_item] = (old_pen, old_brush)
                    # Apply green highlight
                    try:
                        hl_pen = QPen(QColor('#15c915'), old_pen.widthF() if hasattr(old_pen, 'widthF') else CONNECT_LINE_THICKNESS_M)
                        hl_pen.setCapStyle(Qt.SquareCap)
                        hl_pen.setJoinStyle(Qt.MiterJoin)
                        first_item.setPen(hl_pen)
                    except Exception:
                        pass
                    try:
                        # Only fill if the item is a circle (translation) or already filled
                        from .items.elements import CircleElementItem
                        if isinstance(first_item, CircleElementItem) or (hasattr(first_item, 'brush') and first_item.brush() and first_item.brush().style() != Qt.NoBrush):
                            first_item.setBrush(QBrush(QColor('#15c915')))
                    except Exception:
                        pass
            except Exception:
                pass
        if is_rotation_domain:
            # Map rotation-domain ordinals to global path indices and draw along every segment in between
            rot_indices = [idx for idx,(k,_it,_h) in enumerate(self._items) if k in ('rotation','waypoint')]
            if not rot_indices:
                return
            lo = max(1, min(int(lo), len(rot_indices)))
            hi = max(1, min(int(hi), len(rot_indices)))
            if lo > hi:
                lo, hi = hi, lo
            start_anchor_i = lo-1
            if lo > 1:
                start_anchor_i = lo-2  # include the segment leading into the first selected anchor
            end_anchor_i = hi-1
            start_global = rot_indices[start_anchor_i]
            end_global = rot_indices[end_anchor_i]
            if start_global > end_global:
                start_global, end_global = end_global, start_global
            # Draw contiguous segments along the path between these global indices
            for j in range(start_global, end_global):
                if j < 0 or j+1 >= len(self._items):
                    break
                try:
                    _k1,a,_h1 = self._items[j]
                    _k2,b,_h2 = self._items[j+1]
                    if a is None or b is None:
                        continue
                    line=QGraphicsLineItem(a.pos().x(), a.pos().y(), b.pos().x(), b.pos().y()); line.setPen(green_pen); line.setZValue(25)
                    self.graphics_scene.addItem(line); self._range_overlay_lines.append(line)
                except Exception:
                    continue
            return
        # Translation-domain anchors: mirror rotation logic by mapping ordinal anchors to global indices
        tr_indices = [idx for idx,(k,_it,_h) in enumerate(self._items) if k in ('translation','waypoint')]
        if not tr_indices:
            return
        lo = max(1, min(int(lo), len(tr_indices)))
        hi = max(1, min(int(hi), len(tr_indices)))
        if lo > hi:
            lo, hi = hi, lo
        start_anchor_i = lo - 1
        if lo > 1:
            start_anchor_i = lo - 2  # include the segment leading into the first selected anchor
        end_anchor_i = hi - 1
        start_global = tr_indices[start_anchor_i]
        end_global = tr_indices[end_anchor_i]
        if start_global > end_global:
            start_global, end_global = end_global, start_global
        for j in range(start_global, end_global):
            if j < 0 or j+1 >= len(self._items):
                break
            try:
                _k1,a,_h1 = self._items[j]
                _k2,b,_h2 = self._items[j+1]
                if a is None or b is None:
                    continue
                line=QGraphicsLineItem(a.pos().x(), a.pos().y(), b.pos().x(), b.pos().y()); line.setPen(green_pen); line.setZValue(25)
                self.graphics_scene.addItem(line); self._range_overlay_lines.append(line)
            except Exception:
                continue
