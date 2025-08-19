from __future__ import annotations

import os
import math
from typing import List, Optional, Tuple

from PySide6.QtCore import QPoint, QPointF, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
)

from models.path_model import Path, PathElement, TranslationTarget, RotationTarget, Waypoint
from models.simulation import simulate_path, SimResult

from .canvas_constants import (
    FIELD_LENGTH_METERS,
    FIELD_WIDTH_METERS,
    ELEMENT_RECT_WIDTH_M,
    ELEMENT_RECT_HEIGHT_M,
    CONNECT_LINE_THICKNESS_M,
    HANDLE_DISTANCE_M,
    HANDLE_RADIUS_M,
)
from .canvas_items import (
    CircleElementItem,
    RectElementItem,
    RobotSimItem,
    RotationHandle,
    HandoffRadiusVisualizer,
)
from .canvas_transport import TransportControls


class CanvasView(QGraphicsView):
    elementSelected = Signal(int)
    elementMoved = Signal(int, float, float)
    elementRotated = Signal(int, float)
    elementDragFinished = Signal(int)
    rotationDragFinished = Signal(int)
    deleteSelectedRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setFocusPolicy(Qt.StrongFocus)

        self._is_fitting: bool = False
        self._suppress_live_events: bool = False
        self._rotation_t_cache: Optional[dict[int, float]] = None
        self._anchor_drag_in_progress: bool = False

        # Robot element rectangle dimensions
        self.robot_length_m: float = ELEMENT_RECT_WIDTH_M
        self.robot_width_m: float = ELEMENT_RECT_HEIGHT_M

        # Scene and background
        self.graphics_scene = QGraphicsScene(self)
        self.setScene(self.graphics_scene)
        self.graphics_scene.setSceneRect(0, 0, FIELD_LENGTH_METERS, FIELD_WIDTH_METERS)
        self._field_pixmap_item: Optional[QGraphicsPixmapItem] = None
        self._load_field_background("assets/field25.png")

        # Model and items
        self._path: Optional[Path] = None
        self._items: List[Tuple[str, RectElementItem, Optional[RotationHandle]]] = []
        self._connect_lines: List[QGraphicsLineItem] = []
        self._handoff_visualizers: List[Optional[HandoffRadiusVisualizer]] = []

        # Simulation state
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

        self._sim_robot_item: Optional[RobotSimItem] = None
        self._ensure_sim_robot_item()
        self._trail_lines: List[QGraphicsLineItem] = []
        self._trail_points: List[Tuple[float, float]] = []

        # Transport controls overlay (modular)
        self._transport = TransportControls(self)
        self._transport.build()

        # Ranged overlay lines
        self._range_overlay_lines: List[QGraphicsLineItem] = []

        # Zoom/pan state
        self._zoom_factor: float = 1.0
        self._min_zoom: float = 1.0
        self._max_zoom: float = 8.0
        self._is_panning: bool = False
        self._pan_start: Optional[QPoint] = None

    # ---------------- Scene setup ----------------
    def _load_field_background(self, image_path: str):
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return
        self._field_pixmap_item = QGraphicsPixmapItem(pixmap)
        self._field_pixmap_item.setZValue(-10)
        if pixmap.width() > 0 and pixmap.height() > 0:
            s = None
            try:
                if os.path.basename(image_path) == "field25.png":
                    ppm = 200.0
                    s = 1.0 / float(ppm)
            except Exception:
                s = None
            if s is None:
                s = min(
                    FIELD_LENGTH_METERS / float(pixmap.width()),
                    FIELD_WIDTH_METERS / float(pixmap.height()),
                )
            self._field_pixmap_item.setTransform(QTransform().scale(s, s))
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
            try:
                item.set_dimensions(self.robot_length_m, self.robot_width_m)
            except Exception:
                pass
        except Exception:
            pass

    # ---------------- Public API ----------------
    def set_project_manager(self, project_manager):
        self._project_manager = project_manager

    def set_path(self, path: Path):
        self._path = path
        try:
            self.clear_constraint_range_overlay()
        except Exception:
            pass
        self._rebuild_items()
        if self._path is not None:
            self._reproject_rotation_items_in_scene()
        self.request_simulation_rebuild()

    def refresh_from_model(self):
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
                    element = self._path.path_elements[i]
                    pos = self._element_position_for_index(i)
                    item.set_center(QPointF(pos[0], pos[1]))
                    if kind in ("rotation", "waypoint"):
                        angle = self._element_rotation(element)
                    else:
                        angle = self._angle_for_translation_index(i)
                    item.set_angle_radians(angle)
                    if handle is not None:
                        handle.set_angle(angle)
                except Exception:
                    continue
        finally:
            self._suppress_live_events = False
        self._update_connecting_lines()

    # ---------------- Simulation ----------------
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
                if self._transport.slider is not None:
                    self._transport.slider.setRange(0, 0)
                if self._transport.label is not None:
                    self._transport.label.setText("0.00 / 0.00 s")
                return

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

            if self._transport.slider is not None:
                self._transport.slider.blockSignals(True)
                self._transport.slider.setRange(0, int(round(self._sim_total_time_s * 1000.0)))
                self._transport.slider.setValue(0)
                self._transport.slider.blockSignals(False)
            if self._transport.label is not None:
                self._transport.label.setText(f"0.00 / {self._sim_total_time_s:.2f} s")

            if self._sim_robot_item is not None:
                if self._sim_times_sorted:
                    t0 = self._sim_times_sorted[0]
                    x, y, th = self._sim_poses_by_time.get(t0, (0.0, 0.0, 0.0))
                    self._set_sim_robot_pose(x, y, th)
                self._update_sim_robot_visibility()

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
                if self._transport.button is not None:
                    self._transport.button.setText("▶")
                self._update_sim_robot_visibility()
            else:
                if not self._sim_times_sorted:
                    return
                if self._sim_current_time_s >= self._sim_total_time_s:
                    self._sim_current_time_s = 0.0
                    self._seek_to_time(0.0)
                    if self._transport.slider is not None:
                        self._transport.slider.blockSignals(True)
                        self._transport.slider.setValue(0)
                        self._transport.slider.blockSignals(False)
                    self._update_trail_visibility(0)
                self._sim_timer.start()
                if self._transport.button is not None:
                    self._transport.button.setText("⏸")
                self._update_sim_robot_visibility()
        except Exception:
            pass

    def _on_slider_changed(self, value: int):
        try:
            self._sim_current_time_s = float(value) / 1000.0
            self._seek_to_time(self._sim_current_time_s)
            self._update_sim_robot_visibility()
        except Exception:
            pass

    def _on_slider_pressed(self):
        try:
            if self._sim_timer.isActive():
                self._sim_timer.stop()
                if self._transport.button is not None:
                    self._transport.button.setText("▶")
            self._update_sim_robot_visibility()
        except Exception:
            pass

    def _on_slider_released(self):
        pass

    def _seek_to_time(self, t_s: float):
        try:
            if not self._sim_times_sorted or not self._sim_poses_by_time:
                return
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
            self._update_trail_visibility(key_index)
            if self._transport.label is not None:
                self._transport.label.setText(f"{t_s:.2f} / {self._sim_total_time_s:.2f} s")
            self._update_sim_robot_visibility()
        except Exception:
            pass

    def _on_sim_tick(self):
        try:
            if not self._sim_times_sorted:
                self._sim_timer.stop()
                if self._transport.button is not None:
                    self._transport.button.setText("▶")
                return
            self._sim_current_time_s += 0.02
            if self._sim_current_time_s >= self._sim_total_time_s:
                self._sim_current_time_s = self._sim_total_time_s
                self._sim_timer.stop()
                if self._transport.button is not None:
                    self._transport.button.setText("▶")
            if self._transport.slider is not None:
                self._transport.slider.blockSignals(True)
                self._transport.slider.setValue(int(round(self._sim_current_time_s * 1000.0)))
                self._transport.slider.blockSignals(False)
            self._seek_to_time(self._sim_current_time_s)
        except Exception:
            pass

    # ---------------- Ranged constraint overlay ----------------
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
        self.clear_constraint_range_overlay()
        if self._path is None or not self._items:
            return

        lo = int(min(start_ordinal, end_ordinal))
        hi = int(max(start_ordinal, end_ordinal))
        if lo <= 0 and hi <= 0:
            return

        anchor_indices: List[int] = [i for i, (k, _it, _h) in enumerate(self._items) if k in ("translation", "waypoint")]

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

        def _draw_segment(j: int):
            if j < 0 or j >= len(anchor_indices) - 1:
                return
            ia = anchor_indices[j]
            ib = anchor_indices[j + 1]
            pa = _pos_for_index(ia)
            pb = _pos_for_index(ib)
            if pa is None or pb is None:
                return
            line = QGraphicsLineItem(pa[0], pa[1], pb[0], pb[1])
            line.setPen(QPen(QColor("#15c915"), CONNECT_LINE_THICKNESS_M))
            line.setZValue(25)
            self.graphics_scene.addItem(line)
            self._range_overlay_lines.append(line)

        is_translation_domain = key in ("max_velocity_meters_per_sec", "max_acceleration_meters_per_sec2")
        if is_translation_domain:
            A = len(anchor_indices)
            if A < 2:
                return
            L = max(1, min(lo, A))
            H = max(1, min(hi, A))
            if L > H:
                L, H = H, L
            if L == 1 and H == 1:
                return
            j_start = max(0, L - 2)
            j_end = min(A - 2, H - 2)
            if j_end < j_start:
                return
            for j in range(j_start, j_end + 1):
                _draw_segment(j)
            return

        # Rotation-domain helper
        def _pos_on_segment(seg_idx: int, t: float) -> Optional[Tuple[float, float]]:
            if seg_idx < 0 or seg_idx >= len(anchor_indices) - 1:
                return None
            ia = anchor_indices[seg_idx]
            ib = anchor_indices[seg_idx + 1]
            pa = _pos_for_index(ia)
            pb = _pos_for_index(ib)
            if pa is None or pb is None:
                return None
            ax, ay = pa
            bx, by = pb
            t = max(0.0, min(1.0, float(t)))
            return (ax + t * (bx - ax), ay + t * (by - ay))

        event_item_indices: List[int] = [i for i, (k, _it, _h) in enumerate(self._items) if k in ("rotation", "waypoint")]
        R = len(event_item_indices)
        if R == 0 or len(anchor_indices) < 2:
            return

        class _Evt:
            def __init__(self, valid: bool, seg_idx: int, t: float):
                self.valid = valid
                self.seg_idx = seg_idx
                self.t = t

        def _event_info(item_idx: int) -> _Evt:
            try:
                kind, _it, _h = self._items[item_idx]
            except Exception:
                return _Evt(False, -1, 0.0)
            if kind == "waypoint":
                try:
                    anchor_ord0 = anchor_indices.index(item_idx)
                except ValueError:
                    return _Evt(False, -1, 0.0)
                seg_idx = anchor_ord0 - 1
                t_val = 1.0
                if seg_idx < 0:
                    seg_idx = anchor_ord0
                    t_val = 0.0
                return _Evt(True, seg_idx, t_val)
            if kind == "rotation":
                prev_anchor_item_idx = -1
                for j in range(item_idx - 1, -1, -1):
                    knd, _a, _b = self._items[j]
                    if knd in ("translation", "waypoint"):
                        prev_anchor_item_idx = j
                        break
                if prev_anchor_item_idx < 0:
                    return _Evt(False, -1, 0.0)
                try:
                    seg_idx = anchor_indices.index(prev_anchor_item_idx)
                except ValueError:
                    return _Evt(False, -1, 0.0)
                t_val = 0.0
                try:
                    if self._path is not None and item_idx < len(self._path.path_elements):
                        el = self._path.path_elements[item_idx]
                        if isinstance(el, RotationTarget):
                            t_val = float(getattr(el, 't_ratio', 0.0))
                except Exception:
                    t_val = 0.0
                t_val = max(0.0, min(1.0, t_val))
                return _Evt(True, seg_idx, t_val)
            return _Evt(False, -1, 0.0)

        events_info: List[_Evt] = [_event_info(idx) for idx in event_item_indices]
        Lr = max(1, min(lo, R))
        Hr = max(1, min(hi, R))
        if Lr > Hr:
            Lr, Hr = Hr, Lr
        if Lr == 1 and Hr == 1:
            return

        green_pen = QPen(QColor("#15c915"), CONNECT_LINE_THICKNESS_M)
        green_pen.setCapStyle(Qt.RoundCap)

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
            p0 = _pos_on_segment(seg_a, t_a)
            p1 = _pos_on_segment(seg_a, 1.0)
            if p0 is not None and p1 is not None:
                line = QGraphicsLineItem(p0[0], p0[1], p1[0], p1[1])
                line.setPen(green_pen)
                line.setZValue(25)
                self.graphics_scene.addItem(line)
                self._range_overlay_lines.append(line)
            for s in range(seg_a + 1, seg_b):
                _draw_segment(s)
            p2 = _pos_on_segment(seg_b, 0.0)
            p3 = _pos_on_segment(seg_b, t_b)
            if p2 is not None and p3 is not None:
                line = QGraphicsLineItem(p2[0], p2[1], p3[0], p3[1])
                line.setPen(green_pen)
                line.setZValue(25)
                self.graphics_scene.addItem(line)
                self._range_overlay_lines.append(line)

        if Lr - 2 >= 0:
            prev_ev = events_info[Lr - 2]
            first_ev = events_info[Lr - 1]
            if prev_ev.valid and first_ev.valid:
                _draw_between(prev_ev.seg_idx, prev_ev.t, first_ev.seg_idx, first_ev.t)
        for i_ev in range(Lr - 1, Hr - 1):
            a = events_info[i_ev]
            b = events_info[i_ev + 1]
            if a.valid and b.valid:
                _draw_between(a.seg_idx, a.t, b.seg_idx, b.t)

    # ---------------- Items and geometry ----------------
    def _clear_scene_items(self):
        for _, item, handle in self._items:
            self.graphics_scene.removeItem(item)
            if handle is not None:
                for sub in handle.scene_items():
                    self.graphics_scene.removeItem(sub)
        for line in self._connect_lines:
            self.graphics_scene.removeItem(line)
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
            if isinstance(element, TranslationTarget):
                kind = "translation"
                item = CircleElementItem(self, QPointF(pos[0], pos[1]), i,
                                         filled_color=QColor("#3aa3ff"), outline_color=QColor("#3aa3ff"),
                                         dashed_outline=False, triangle_color=None)
                rotation_handle = None
                item.set_angle_radians(self._angle_for_translation_index(i))
                handoff_visualizer = None
            elif isinstance(element, RotationTarget):
                kind = "rotation"
                item = RectElementItem(self, QPointF(pos[0], pos[1]), i,
                                       filled_color=None, outline_color=QColor("#50c878"),
                                       dashed_outline=True, triangle_color=QColor("#50c878"))
                rotation_handle = RotationHandle(self, item, handle_distance_m=HANDLE_DISTANCE_M,
                                                 handle_radius_m=HANDLE_RADIUS_M, color=QColor("#50c878"))
                item.set_angle_radians(self._element_rotation(element))
                rotation_handle.set_angle(self._element_rotation(element))
                rotation_handle.sync_to_angle()
                handoff_visualizer = None
            elif isinstance(element, Waypoint):
                kind = "waypoint"
                item = RectElementItem(self, QPointF(pos[0], pos[1]), i,
                                       filled_color=None, outline_color=QColor("#ff7f3a"),
                                       dashed_outline=False, triangle_color=QColor("#ff7f3a"))
                rotation_handle = RotationHandle(self, item, handle_distance_m=HANDLE_DISTANCE_M,
                                                 handle_radius_m=HANDLE_RADIUS_M, color=QColor("#ff7f3a"))
                item.set_angle_radians(self._element_rotation(element))
                rotation_handle.set_angle(self._element_rotation(element))
                rotation_handle.sync_to_angle()
                handoff_visualizer = None
            else:
                continue
            try:
                self.graphics_scene.addItem(item)
            except Exception:
                continue
            if rotation_handle is not None:
                for sub in rotation_handle.scene_items():
                    try:
                        self.graphics_scene.addItem(sub)
                    except Exception:
                        continue
            self._items.append((kind, item, rotation_handle))
            self._handoff_visualizers.append(handoff_visualizer)
        self._build_connecting_lines()

    def _angle_for_translation_index(self, index: int) -> float:
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
            prev_pos, next_pos = self._neighbor_positions_model(index)
            if prev_pos is None or next_pos is None:
                return 0.0, 0.0
            ax, ay = prev_pos
            bx, by = next_pos
            t = float(getattr(element, "t_ratio", 0.0))
            t = max(0.0, min(1.0, t))
            return ax + t * (bx - ax), ay + t * (by - ay)
        return 0.0, 0.0

    def _neighbor_positions_model(self, index: int) -> Tuple[Optional[Tuple[float, float]], Optional[Tuple[float, float]]]:
        if self._path is None:
            return None, None
        prev_pos = None
        for i in range(index - 1, -1, -1):
            e = self._path.path_elements[i]
            if isinstance(e, TranslationTarget):
                prev_pos = (float(e.x_meters), float(e.y_meters))
                break
            if isinstance(e, Waypoint):
                prev_pos = (float(e.translation_target.x_meters), float(e.translation_target.y_meters))
                break
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
            except Exception:
                continue

    def _update_connecting_lines(self):
        if not self._items or not self._connect_lines:
            return
        for i in range(len(self._connect_lines)):
            if i >= len(self._items) - 1:
                break
            try:
                _, a, _ = self._items[i]
                _, b, _ = self._items[i + 1]
                if a is not None and b is not None:
                    self._connect_lines[i].setLine(a.pos().x(), a.pos().y(), b.pos().x(), b.pos().y())
            except Exception:
                continue

    # ---------------- Live interactions ----------------
    def _on_item_live_moved(self, index: int, x_m: float, y_m: float):
        if index < 0 or index >= len(self._items):
            return
        self._update_connecting_lines()
        try:
            _, _, handle = self._items[index]
            if handle is not None:
                handle.sync_to_angle()
        except Exception:
            pass
        if index < len(self._handoff_visualizers) and self._handoff_visualizers[index] is not None:
            try:
                self._handoff_visualizers[index].set_center(QPointF(x_m, y_m))
            except Exception:
                pass
        self.elementMoved.emit(index, x_m, y_m)
        kind, _, _ = self._items[index]
        if kind in ('translation', 'waypoint'):
            self._reproject_rotation_items_in_scene()

    def _on_item_live_rotated(self, index: int, angle_radians: float):
        if index < 0 or index >= len(self._items):
            return
        try:
            kind, item, handle = self._items[index]
            if kind in ("rotation", "waypoint"):
                item.set_angle_radians(angle_radians)
                if handle is not None:
                    handle.set_angle(angle_radians)
        except Exception:
            return
        self.elementRotated.emit(index, angle_radians)
        for j, (k, it, _) in enumerate(self._items):
            if k == 'translation':
                try:
                    it.set_angle_radians(self._angle_for_translation_index(j))
                except Exception:
                    continue

    def _on_item_clicked(self, index: int):
        self.elementSelected.emit(index)

    def _on_rotation_handle_released(self, index: int):
        self.rotationDragFinished.emit(index)

    def _on_item_pressed(self, index: int):
        if index < 0 or index >= len(self._items):
            return
        kind, _, _ = self._items[index]
        if kind in ('translation', 'waypoint'):
            self._anchor_drag_in_progress = True
            self._rotation_t_cache = self._compute_rotation_t_cache()

    def _on_item_released(self, index: int):
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
        self.elementDragFinished.emit(index)
        self.request_simulation_rebuild()

    # ---------------- Selection & view ----------------
    def select_index(self, index: int):
        if index is None or index < 0 or index >= len(self._items):
            return
        try:
            _, item, _ = self._items[index]
        except Exception:
            return
        if item is None:
            return
        try:
            if getattr(item, 'scene', None) is None:
                return
            if item.scene() is None:
                return
            self.graphics_scene.clearSelection()
            item.setSelected(True)
            QTimer.singleShot(0, lambda it=item: self._safe_center_on(it))
        except Exception:
            return

    def _safe_center_on(self, item: QGraphicsItem):
        try:
            if item is None:
                return
            if getattr(item, 'scene', None) is None:
                return
            if item.scene() is None:
                return
            self.centerOn(item)
        except Exception:
            return

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._fit_to_scene)
        QTimer.singleShot(0, self._position_transport_controls)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._fit_to_scene)
        QTimer.singleShot(0, self._position_transport_controls)

    def _fit_to_scene(self):
        if self._is_fitting:
            return
        self._is_fitting = True
        try:
            rect = self.graphics_scene.sceneRect()
            if rect.width() > 0 and rect.height() > 0:
                try:
                    self.fitInView(rect, Qt.KeepAspectRatio)
                    if abs(self._zoom_factor - 1.0) > 1e-6:
                        self.scale(self._zoom_factor, self._zoom_factor)
                except RuntimeError:
                    pass
        except Exception:
            pass
        finally:
            self._is_fitting = False

    def _position_transport_controls(self):
        try:
            self._transport.position()
        except Exception:
            pass

    # ---------------- Coordinates & constraints ----------------
    def _scene_from_model(self, x_m: float, y_m: float) -> QPointF:
        return QPointF(x_m, FIELD_WIDTH_METERS - y_m)

    def _model_from_scene(self, x_s: float, y_s: float) -> Tuple[float, float]:
        return float(x_s), float(FIELD_WIDTH_METERS - y_s)

    def _clamp_scene_coords(self, x_s: float, y_s: float) -> Tuple[float, float]:
        min_x, min_y = 0.0, 0.0
        max_x, max_y = FIELD_LENGTH_METERS, FIELD_WIDTH_METERS
        return max(min_x, min(x_s, max_x)), max(min_y, min(y_s, max_y))

    def _constrain_scene_coords_for_index(self, index: int, x_s: float, y_s: float) -> Tuple[float, float]:
        x_s, y_s = self._clamp_scene_coords(x_s, y_s)
        if index < 0 or index >= len(self._items):
            return x_s, y_s
        try:
            kind, _, _ = self._items[index]
        except Exception:
            return x_s, y_s
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
        t = max(0.0, min(1.0, t))
        proj_x = ax + t * dx
        proj_y = ay + t * dy
        return self._clamp_scene_coords(proj_x, proj_y)

    def _find_neighbor_item_positions(self, index: int) -> Tuple[Optional[Tuple[float, float]], Optional[Tuple[float, float]]]:
        prev_pos: Optional[Tuple[float, float]] = None
        for i in range(index - 1, -1, -1):
            try:
                kind, item, _ = self._items[i]
                if kind in ('translation', 'waypoint'):
                    prev_pos = (item.pos().x(), item.pos().y())
                    break
            except Exception:
                continue
        next_pos: Optional[Tuple[float, float]] = None
        for i in range(index + 1, len(self._items)):
            try:
                kind, item, _ = self._items[i]
                if kind in ('translation', 'waypoint'):
                    next_pos = (item.pos().x(), item.pos().y())
                    break
            except Exception:
                continue
        return prev_pos, next_pos

    def _reproject_rotation_items_in_scene(self):
        self._suppress_live_events = True
        try:
            for i, (kind, item, handle) in enumerate(self._items):
                if kind != 'rotation':
                    continue
                prev_pos, next_pos = self._find_neighbor_item_positions(i)
                if prev_pos is None or next_pos is None:
                    continue
                ax, ay = prev_pos
                bx, by = next_pos
                t = 0.0
                try:
                    if self._path is not None and i < len(self._path.path_elements):
                        rt = self._path.path_elements[i]
                        if isinstance(rt, RotationTarget):
                            t = float(getattr(rt, 't_ratio', 0.0))
                except Exception:
                    t = 0.0
                t = max(0.0, min(1.0, t))
                proj_x = ax + t * (bx - ax)
                proj_y = ay + t * (by - ay)
                try:
                    item.setPos(proj_x, proj_y)
                    if handle is not None:
                        handle.sync_to_angle()
                except Exception:
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
            t = max(0.0, min(1.0, t))
            t_by_index[i] = float(t)
        return t_by_index

    # ---------------- Keyboard/mouse ----------------
    def keyPressEvent(self, event):
        try:
            if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                self.deleteSelectedRequested.emit()
                event.accept()
                return
            if event.key() == Qt.Key_Space:
                self._toggle_play_pause()
                event.accept()
                return
        except Exception:
            pass
        super().keyPressEvent(event)

    def wheelEvent(self, event):
        try:
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
                return super().wheelEvent(event)
            zoom_step = 1.03
            factor = zoom_step if delta_y > 0 else (1.0 / zoom_step)
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
            self.scale(factor, factor)
            event.accept()
        except Exception:
            try:
                super().wheelEvent(event)
            except Exception:
                pass

    def mousePressEvent(self, event):
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

from __future__ import annotations

import os
from typing import List, Optional, Tuple

from PySide6.QtCore import QPoint, QPointF, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPixmapItem,
    QGraphicsProxyWidget,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QWidget,
)

from models.path_model import Path, PathElement, TranslationTarget, RotationTarget, Waypoint
from models.simulation import simulate_path, SimResult

from .canvas_constants import (
    FIELD_LENGTH_METERS,
    FIELD_WIDTH_METERS,
    CONNECT_LINE_THICKNESS_M,
)
from .canvas_items import (
    CircleElementItem,
    RectElementItem,
    RobotSimItem,
    RotationHandle,
    HandoffRadiusVisualizer,
)
from .canvas_transport import TransportControls


class CanvasView(QGraphicsView):
    elementSelected = Signal(int)
    elementMoved = Signal(int, float, float)
    elementRotated = Signal(int, float)
    elementDragFinished = Signal(int)
    rotationDragFinished = Signal(int)
    deleteSelectedRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setFocusPolicy(Qt.StrongFocus)

        self._suppress_live_events: bool = False
        self._anchor_drag_in_progress: bool = False
        self._rotation_t_cache: Optional[dict[int, float]] = None

        self.graphics_scene = QGraphicsScene(self)
        self.setScene(self.graphics_scene)
        self.graphics_scene.setSceneRect(0, 0, FIELD_LENGTH_METERS, FIELD_WIDTH_METERS)

        self._field_pixmap_item: Optional[QGraphicsPixmapItem] = None
        self._path: Optional[Path] = None
        self._items: List[Tuple[str, RectElementItem, Optional[RotationHandle]]] = []
        self._connect_lines: List[QGraphicsLineItem] = []
        self._handoff_visualizers: List[Optional[HandoffRadiusVisualizer]] = []
        self._range_overlay_lines: List[QGraphicsLineItem] = []

        self._load_field_background("assets/field25.png")

        # Simulation
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

        self._sim_robot_item: Optional[RobotSimItem] = None
        self._ensure_sim_robot_item()
        self._trail_lines: List[QGraphicsLineItem] = []
        self._trail_points: List[Tuple[float, float]] = []

        # Transport controls overlay
        self._transport = TransportControls(self)
        self._transport.build()

    # ---------- scene ----------
    def _load_field_background(self, image_path: str):
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return
        self._field_pixmap_item = QGraphicsPixmapItem(pixmap)
        self._field_pixmap_item.setZValue(-10)
        if pixmap.width() > 0 and pixmap.height() > 0:
            s = min(
                FIELD_LENGTH_METERS / float(pixmap.width()),
                FIELD_WIDTH_METERS / float(pixmap.height())
            )
            self._field_pixmap_item.setTransform(QTransform().scale(s, s))
            h_scaled = pixmap.height() * s
            self._field_pixmap_item.setPos(0.0, FIELD_WIDTH_METERS - h_scaled)
        self.graphics_scene.addItem(self._field_pixmap_item)

    def _ensure_sim_robot_item(self):
        if self._sim_robot_item is not None:
            return
        item = RobotSimItem(self)
        self.graphics_scene.addItem(item)
        self._sim_robot_item = item
        item.setVisible(False)

    # ---------- external api ----------
    def set_project_manager(self, project_manager):
        self._project_manager = project_manager

    def set_path(self, path: Path):
        self._path = path
        try:
            self.clear_constraint_range_overlay()
        except Exception:
            pass
        self._rebuild_items()
        self.request_simulation_rebuild()

    def refresh_from_model(self):
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
                    element = self._path.path_elements[i]
                    pos = self._element_position_for_index(i)
                    item.set_center(QPointF(pos[0], pos[1]))
                    if kind in ("rotation", "waypoint"):
                        angle = self._element_rotation(element)
                    else:
                        angle = self._angle_for_translation_index(i)
                    item.set_angle_radians(angle)
                    if handle is not None:
                        handle.set_angle(angle)
                except Exception:
                    continue
        finally:
            self._suppress_live_events = False
        self._update_connecting_lines()

    # ---------- simulation ----------
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
                if self._transport.slider is not None:
                    self._transport.slider.setRange(0, 0)
                if self._transport.label is not None:
                    self._transport.label.setText("0.00 / 0.00 s")
                return

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

            if self._transport.slider is not None:
                self._transport.slider.blockSignals(True)
                self._transport.slider.setRange(0, int(round(self._sim_total_time_s * 1000.0)))
                self._transport.slider.setValue(0)
                self._transport.slider.blockSignals(False)
            if self._transport.label is not None:
                self._transport.label.setText(f"0.00 / {self._sim_total_time_s:.2f} s")

            if self._sim_robot_item is not None and self._sim_times_sorted:
                t0 = self._sim_times_sorted[0]
                x, y, th = self._sim_poses_by_time.get(t0, (0.0, 0.0, 0.0))
                self._set_sim_robot_pose(x, y, th)
            self._update_sim_robot_visibility()

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
                if self._transport.button is not None:
                    self._transport.button.setText("▶")
                self._update_sim_robot_visibility()
            else:
                if not self._sim_times_sorted:
                    return
                if self._sim_current_time_s >= self._sim_total_time_s:
                    self._sim_current_time_s = 0.0
                    self._seek_to_time(0.0)
                    if self._transport.slider is not None:
                        self._transport.slider.blockSignals(True)
                        self._transport.slider.setValue(0)
                        self._transport.slider.blockSignals(False)
                    self._update_trail_visibility(0)
                self._sim_timer.start()
                if self._transport.button is not None:
                    self._transport.button.setText("⏸")
                self._update_sim_robot_visibility()
        except Exception:
            pass

    def _on_slider_changed(self, value: int):
        try:
            self._sim_current_time_s = float(value) / 1000.0
            self._seek_to_time(self._sim_current_time_s)
            self._update_sim_robot_visibility()
        except Exception:
            pass

    def _on_slider_pressed(self):
        try:
            if self._sim_timer.isActive():
                self._sim_timer.stop()
                if self._transport.button is not None:
                    self._transport.button.setText("▶")
            self._update_sim_robot_visibility()
        except Exception:
            pass

    def _on_slider_released(self):
        pass

    def _seek_to_time(self, t_s: float):
        try:
            if not self._sim_times_sorted or not self._sim_poses_by_time:
                return
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
            self._update_trail_visibility(key_index)
            if self._transport.label is not None:
                self._transport.label.setText(f"{t_s:.2f} / {self._sim_total_time_s:.2f} s")
            self._update_sim_robot_visibility()
        except Exception:
            pass

    def _on_sim_tick(self):
        try:
            if not self._sim_times_sorted:
                self._sim_timer.stop()
                if self._transport.button is not None:
                    self._transport.button.setText("▶")
                return
            self._sim_current_time_s += 0.02
            if self._sim_current_time_s >= self._sim_total_time_s:
                self._sim_current_time_s = self._sim_total_time_s
                self._sim_timer.stop()
                if self._transport.button is not None:
                    self._transport.button.setText("▶")
            if self._transport.slider is not None:
                self._transport.slider.blockSignals(True)
                self._transport.slider.setValue(int(round(self._sim_current_time_s * 1000.0)))
                self._transport.slider.blockSignals(False)
            self._seek_to_time(self._sim_current_time_s)
        except Exception:
            pass

    # ---------- items and geometry ----------
    def _clear_scene_items(self):
        for _, item, handle in self._items:
            self.graphics_scene.removeItem(item)
            if handle is not None:
                for sub in handle.scene_items():
                    self.graphics_scene.removeItem(sub)
        for line in self._connect_lines:
            self.graphics_scene.removeItem(line)
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
        from .canvas_constants import HANDLE_DISTANCE_M, HANDLE_RADIUS_M
        for i, element in enumerate(self._path.path_elements):
            pos = self._element_position_for_index(i)
            if isinstance(element, TranslationTarget):
                kind = "translation"
                item = CircleElementItem(self, QPointF(pos[0], pos[1]), i, filled_color=QColor("#3aa3ff"), outline_color=QColor("#3aa3ff"), dashed_outline=False, triangle_color=None)
                rotation_handle = None
                item.set_angle_radians(self._angle_for_translation_index(i))
                handoff_visualizer = None
            elif isinstance(element, RotationTarget):
                kind = "rotation"
                item = RectElementItem(self, QPointF(pos[0], pos[1]), i, filled_color=None, outline_color=QColor("#50c878"), dashed_outline=True, triangle_color=QColor("#50c878"))
                rotation_handle = RotationHandle(self, item, handle_distance_m=HANDLE_DISTANCE_M, handle_radius_m=HANDLE_RADIUS_M, color=QColor("#50c878"))
                item.set_angle_radians(self._element_rotation(element))
                rotation_handle.set_angle(self._element_rotation(element))
                rotation_handle.sync_to_angle()
                handoff_visualizer = None
            elif isinstance(element, Waypoint):
                kind = "waypoint"
                item = RectElementItem(self, QPointF(pos[0], pos[1]), i, filled_color=None, outline_color=QColor("#ff7f3a"), dashed_outline=False, triangle_color=QColor("#ff7f3a"))
                rotation_handle = RotationHandle(self, item, handle_distance_m=HANDLE_DISTANCE_M, handle_radius_m=HANDLE_RADIUS_M, color=QColor("#ff7f3a"))
                item.set_angle_radians(self._element_rotation(element))
                rotation_handle.set_angle(self._element_rotation(element))
                rotation_handle.sync_to_angle()
                handoff_visualizer = None
            else:
                continue
            try:
                self.graphics_scene.addItem(item)
            except Exception:
                continue
            if rotation_handle is not None:
                for sub in rotation_handle.scene_items():
                    try:
                        self.graphics_scene.addItem(sub)
                    except Exception:
                        continue
            self._items.append((kind, item, rotation_handle))
            self._handoff_visualizers.append(handoff_visualizer)
        self._build_connecting_lines()

    def _angle_for_translation_index(self, index: int) -> float:
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
            prev_pos, next_pos = self._neighbor_positions_model(index)
            if prev_pos is None or next_pos is None:
                return 0.0, 0.0
            ax, ay = prev_pos
            bx, by = next_pos
            t = float(getattr(element, "t_ratio", 0.0))
            t = max(0.0, min(1.0, t))
            return ax + t * (bx - ax), ay + t * (by - ay)
        return 0.0, 0.0

    def _neighbor_positions_model(self, index: int) -> Tuple[Optional[Tuple[float, float]], Optional[Tuple[float, float]]]:
        if self._path is None:
            return None, None
        prev_pos = None
        for i in range(index - 1, -1, -1):
            e = self._path.path_elements[i]
            if isinstance(e, TranslationTarget):
                prev_pos = (float(e.x_meters), float(e.y_meters))
                break
            if isinstance(e, Waypoint):
                prev_pos = (float(e.translation_target.x_meters), float(e.translation_target.y_meters))
                break
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
            except Exception:
                continue

    def _update_connecting_lines(self):
        if not self._items or not self._connect_lines:
            return
        for i in range(len(self._connect_lines)):
            if i >= len(self._items) - 1:
                break
            try:
                _, a, _ = self._items[i]
                _, b, _ = self._items[i + 1]
                if a is not None and b is not None:
                    self._connect_lines[i].setLine(a.pos().x(), a.pos().y(), b.pos().x(), b.pos().y())
            except Exception:
                continue

    # ---------- live interactions ----------
    def _on_item_live_moved(self, index: int, x_m: float, y_m: float):
        if index < 0 or index >= len(self._items):
            return
        self._update_connecting_lines()
        try:
            _, _, handle = self._items[index]
            if handle is not None:
                handle.sync_to_angle()
        except Exception:
            pass
        if index < len(self._handoff_visualizers) and self._handoff_visualizers[index] is not None:
            try:
                self._handoff_visualizers[index].set_center(QPointF(x_m, y_m))
            except Exception:
                pass
        self.elementMoved.emit(index, x_m, y_m)
        kind, _, _ = self._items[index]
        if kind in ('translation', 'waypoint'):
            self._reproject_rotation_items_in_scene()

    def _on_item_live_rotated(self, index: int, angle_radians: float):
        if index < 0 or index >= len(self._items):
            return
        try:
            kind, item, handle = self._items[index]
            if kind in ("rotation", "waypoint"):
                item.set_angle_radians(angle_radians)
                if handle is not None:
                    handle.set_angle(angle_radians)
        except Exception:
            return
        self.elementRotated.emit(index, angle_radians)
        for j, (k, it, _) in enumerate(self._items):
            if k == 'translation':
                try:
                    it.set_angle_radians(self._angle_for_translation_index(j))
                except Exception:
                    continue

    def _on_item_clicked(self, index: int):
        self.elementSelected.emit(index)

    def _on_rotation_handle_released(self, index: int):
        self.rotationDragFinished.emit(index)

    def _on_item_pressed(self, index: int):
        if index < 0 or index >= len(self._items):
            return
        kind, _, _ = self._items[index]
        if kind in ('translation', 'waypoint'):
            self._anchor_drag_in_progress = True
            self._rotation_t_cache = self._compute_rotation_t_cache()

    def _on_item_released(self, index: int):
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
        self.elementDragFinished.emit(index)
        self.request_simulation_rebuild()

    # ---------- selection/view ----------
    def select_index(self, index: int):
        if index is None or index < 0 or index >= len(self._items):
            return
        try:
            _, item, _ = self._items[index]
        except Exception:
            return
        if item is None:
            return
        try:
            if getattr(item, 'scene', None) is None:
                return
            if item.scene() is None:
                return
            self.graphics_scene.clearSelection()
            item.setSelected(True)
            QTimer.singleShot(0, lambda it=item: self._safe_center_on(it))
        except Exception:
            return

    def _safe_center_on(self, item: QGraphicsItem):
        try:
            if item is None:
                return
            if getattr(item, 'scene', None) is None:
                return
            if item.scene() is None:
                return
            self.centerOn(item)
        except Exception:
            return

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._fit_to_scene)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._fit_to_scene)

    def _fit_to_scene(self):
        try:
            rect = self.graphics_scene.sceneRect()
            if rect.width() > 0 and rect.height() > 0:
                self.fitInView(rect, Qt.KeepAspectRatio)
        except Exception:
            pass

    # ---------- coords/constraints ----------
    def _scene_from_model(self, x_m: float, y_m: float) -> QPointF:
        return QPointF(x_m, FIELD_WIDTH_METERS - y_m)

    def _model_from_scene(self, x_s: float, y_s: float) -> Tuple[float, float]:
        return float(x_s), float(FIELD_WIDTH_METERS - y_s)

    def _clamp_scene_coords(self, x_s: float, y_s: float) -> Tuple[float, float]:
        min_x, min_y = 0.0, 0.0
        max_x, max_y = FIELD_LENGTH_METERS, FIELD_WIDTH_METERS
        return max(min_x, min(x_s, max_x)), max(min_y, min(y_s, max_y))

    def _constrain_scene_coords_for_index(self, index: int, x_s: float, y_s: float) -> Tuple[float, float]:
        x_s, y_s = self._clamp_scene_coords(x_s, y_s)
        if index < 0 or index >= len(self._items):
            return x_s, y_s
        try:
            kind, _, _ = self._items[index]
        except Exception:
            return x_s, y_s
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
        t = max(0.0, min(1.0, t))
        proj_x = ax + t * dx
        proj_y = ay + t * dy
        return self._clamp_scene_coords(proj_x, proj_y)

    def _find_neighbor_item_positions(self, index: int) -> Tuple[Optional[Tuple[float, float]], Optional[Tuple[float, float]]]:
        prev_pos: Optional[Tuple[float, float]] = None
        for i in range(index - 1, -1, -1):
            try:
                kind, item, _ = self._items[i]
                if kind in ('translation', 'waypoint'):
                    prev_pos = (item.pos().x(), item.pos().y())
                    break
            except Exception:
                continue
        next_pos: Optional[Tuple[float, float]] = None
        for i in range(index + 1, len(self._items)):
            try:
                kind, item, _ = self._items[i]
                if kind in ('translation', 'waypoint'):
                    next_pos = (item.pos().x(), item.pos().y())
                    break
            except Exception:
                continue
        return prev_pos, next_pos

    def _reproject_rotation_items_in_scene(self):
        self._suppress_live_events = True
        try:
            for i, (kind, item, handle) in enumerate(self._items):
                if kind != 'rotation':
                    continue
                prev_pos, next_pos = self._find_neighbor_item_positions(i)
                if prev_pos is None or next_pos is None:
                    continue
                ax, ay = prev_pos
                bx, by = next_pos
                t = 0.0
                try:
                    if self._path is not None and i < len(self._path.path_elements):
                        rt = self._path.path_elements[i]
                        if isinstance(rt, RotationTarget):
                            t = float(getattr(rt, 't_ratio', 0.0))
                except Exception:
                    t = 0.0
                t = max(0.0, min(1.0, t))
                proj_x = ax + t * (bx - ax)
                proj_y = ay + t * (by - ay)
                try:
                    item.setPos(proj_x, proj_y)
                    if handle is not None:
                        handle.sync_to_angle()
                except Exception:
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
            t = max(0.0, min(1.0, t))
            t_by_index[i] = float(t)
        return t_by_index

