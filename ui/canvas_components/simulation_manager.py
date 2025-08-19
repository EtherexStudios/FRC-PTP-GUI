"""Simulation management for canvas view."""

from typing import Dict, List, Tuple, Optional
from PySide6.QtCore import QTimer, QPointF, Signal, QObject
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QGraphicsLineItem

from models.simulation import simulate_path, SimResult
from models.path_model import Path
from .graphics_items import RobotSimItem


class SimulationManager(QObject):
    """Manages simulation state and playback for the canvas."""
    
    # Signals
    robot_pose_updated = Signal(float, float, float)  # x, y, theta
    time_updated = Signal(float)  # current time
    playback_state_changed = Signal(bool)  # is playing
    
    def __init__(self, canvas_view) -> None:
        """
        Initialize simulation manager.
        
        Args:
            canvas_view: Parent canvas view
        """
        super().__init__()
        self.canvas_view = canvas_view
        
        # Simulation state
        self._sim_result: Optional[SimResult] = None
        self._sim_poses_by_time: Dict[float, Tuple[float, float, float]] = {}
        self._sim_times_sorted: List[float] = []
        self._sim_total_time_s: float = 0.0
        self._sim_current_time_s: float = 0.0
        
        # Playback timer
        self._sim_timer = QTimer(self)
        self._sim_timer.setInterval(20)  # 50 FPS
        self._sim_timer.timeout.connect(self._on_sim_tick)
        
        # Debounce timer for rebuilds
        self._sim_debounce = QTimer(self)
        self._sim_debounce.setSingleShot(True)
        self._sim_debounce.setInterval(200)
        self._sim_debounce.timeout.connect(self._rebuild_simulation_now)
        
        # Robot visualization
        self._sim_robot_item: Optional[RobotSimItem] = None
        
        # Trail visualization
        self._trail_lines: List[QGraphicsLineItem] = []
        self._trail_points: List[Tuple[float, float]] = []
        
    def request_rebuild(self) -> None:
        """Request a debounced simulation rebuild."""
        self._sim_debounce.start()
        
    def set_robot_item(self, robot_item: RobotSimItem) -> None:
        """Set the robot visualization item."""
        self._sim_robot_item = robot_item
        
    def toggle_playback(self) -> None:
        """Toggle simulation playback."""
        if self._sim_timer.isActive():
            self.pause()
        else:
            self.play()
            
    def play(self) -> None:
        """Start simulation playback."""
        if not self._sim_times_sorted:
            return
            
        # Restart from beginning if at end
        if self._sim_current_time_s >= self._sim_total_time_s:
            self._sim_current_time_s = 0.0
            self.seek_to_time(0.0)
            self._update_trail_visibility(0)
            
        self._sim_timer.start()
        self.playback_state_changed.emit(True)
        self._update_robot_visibility()
        
    def pause(self) -> None:
        """Pause simulation playback."""
        self._sim_timer.stop()
        self.playback_state_changed.emit(False)
        self._update_robot_visibility()
        
    def seek_to_time(self, t_s: float) -> None:
        """
        Seek to specific time in simulation.
        
        Args:
            t_s: Time in seconds
        """
        if not self._sim_times_sorted or not self._sim_poses_by_time:
            return
            
        self._sim_current_time_s = t_s
        
        # Find nearest key
        key_index = 0
        key = 0.0
        for i, tk in enumerate(self._sim_times_sorted):
            if tk <= t_s:
                key = tk
                key_index = i
            else:
                break
                
        # Get pose at this time
        x, y, th = self._sim_poses_by_time.get(
            key, 
            self._sim_poses_by_time.get(self._sim_times_sorted[0], (0.0, 0.0, 0.0))
        )
        
        # Update robot pose
        self._set_robot_pose(x, y, th)
        
        # Update trail visibility
        self._update_trail_visibility(key_index)
        
        # Emit time update
        self.time_updated.emit(t_s)
        
        # Update robot visibility
        self._update_robot_visibility()
        
    def get_total_time(self) -> float:
        """Get total simulation time in seconds."""
        return self._sim_total_time_s
        
    def get_current_time(self) -> float:
        """Get current simulation time in seconds."""
        return self._sim_current_time_s
        
    def is_playing(self) -> bool:
        """Check if simulation is playing."""
        return self._sim_timer.isActive()
        
    def clear_trail(self) -> None:
        """Clear trail visualization."""
        for line in self._trail_lines:
            if line.scene() is not None:
                self.canvas_view.graphics_scene.removeItem(line)
        self._trail_lines.clear()
        self._trail_points.clear()
        
    def _rebuild_simulation_now(self) -> None:
        """Rebuild simulation from current path."""
        path = self.canvas_view._path
        if path is None:
            self._clear_simulation()
            return
            
        # Gather config
        cfg = {}
        if hasattr(self.canvas_view, "_project_manager") and self.canvas_view._project_manager is not None:
            cfg = dict(self.canvas_view._project_manager.config or {})
            
        # Run simulation
        result = simulate_path(path, cfg)
        self._sim_result = result
        self._sim_poses_by_time = result.poses_by_time
        self._sim_times_sorted = result.times_sorted
        self._sim_total_time_s = float(result.total_time_s)
        self._sim_current_time_s = 0.0
        
        # Place robot at start
        if self._sim_times_sorted:
            t0 = self._sim_times_sorted[0]
            x, y, th = self._sim_poses_by_time.get(t0, (0.0, 0.0, 0.0))
            self._set_robot_pose(x, y, th)
            
        # Set up trail
        if hasattr(result, 'trail_points') and result.trail_points:
            self._setup_trail(result.trail_points)
        else:
            self.clear_trail()
            
        # Update visibility
        self._update_robot_visibility()
        
        # Notify listeners
        self.time_updated.emit(0.0)
        
    def _clear_simulation(self) -> None:
        """Clear simulation state."""
        self._sim_result = None
        self._sim_poses_by_time = {}
        self._sim_times_sorted = []
        self._sim_total_time_s = 0.0
        self._sim_current_time_s = 0.0
        
        if self._sim_robot_item is not None:
            self._sim_robot_item.setVisible(False)
            
        self.clear_trail()
        self.time_updated.emit(0.0)
        
    def _on_sim_tick(self) -> None:
        """Handle simulation timer tick."""
        if not self._sim_times_sorted:
            self.pause()
            return
            
        # Advance time
        self._sim_current_time_s += 0.02
        
        # Check if finished
        if self._sim_current_time_s >= self._sim_total_time_s:
            self._sim_current_time_s = self._sim_total_time_s
            self.pause()
            
        # Seek to new time
        self.seek_to_time(self._sim_current_time_s)
        
    def _set_robot_pose(self, x_m: float, y_m: float, theta_rad: float) -> None:
        """Set robot visualization pose."""
        if self._sim_robot_item is None:
            return
            
        self._sim_robot_item.set_center(QPointF(x_m, y_m))
        self._sim_robot_item.set_angle_radians(theta_rad)
        self.robot_pose_updated.emit(x_m, y_m, theta_rad)
        
    def _update_robot_visibility(self) -> None:
        """Update robot visibility based on state."""
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
            
    def _setup_trail(self, trail_points: List[Tuple[float, float]]) -> None:
        """Set up trail visualization."""
        self.clear_trail()
        self._trail_points = trail_points.copy()
        
        # Create line items
        orange_pen = QPen(QColor(255, 165, 0), 0.05)
        orange_pen.setCapStyle(Qt.RoundCap)
        
        for i in range(len(self._trail_points) - 1):
            line = QGraphicsLineItem()
            line.setPen(orange_pen)
            line.setZValue(14)  # Above field, below robot
            line.setVisible(False)
            self.canvas_view.graphics_scene.addItem(line)
            self._trail_lines.append(line)
            
    def _update_trail_visibility(self, current_index: int) -> None:
        """Update which trail segments are visible."""
        if not self._trail_points or not self._trail_lines:
            return
            
        # Show trail segments up to current position
        for i in range(len(self._trail_lines)):
            line = self._trail_lines[i]
            if i < current_index and i < len(self._trail_points) - 1:
                # Set line coordinates and make visible
                x1, y1 = self._trail_points[i]
                x2, y2 = self._trail_points[i + 1]
                scene_p1 = self.canvas_view._scene_from_model(x1, y1)
                scene_p2 = self.canvas_view._scene_from_model(x2, y2)
                line.setLine(scene_p1.x(), scene_p1.y(), scene_p2.x(), scene_p2.y())
                line.setVisible(True)
            else:
                # Hide this segment
                line.setVisible(False)