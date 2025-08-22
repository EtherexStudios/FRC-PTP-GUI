from PySide6.QtWidgets import QMainWindow, QHBoxLayout, QWidget, QFileDialog, QMenuBar, QMenu, QDialog, QToolBar, QToolButton, QApplication, QFrame, QSizePolicy
from PySide6.QtGui import QAction, QKeySequence, QIcon, QPixmap, QPainter, QPolygon, QPen, QBrush, QColor
from PySide6.QtCore import QPoint, QSize
import math
import os
import copy
import platform
from .sidebar import Sidebar
from .sidebar.utils import clamp_from_metadata
from models.path_model import TranslationTarget, RotationTarget, Waypoint, Path
from .canvas import CanvasView, FIELD_LENGTH_METERS, FIELD_WIDTH_METERS
from typing import Tuple
from PySide6.QtCore import Qt, QTimer, QEvent
from utils.project_manager import ProjectManager
from utils.undo_system import UndoRedoManager, PathCommand, ConfigCommand
from .config_dialog import ConfigDialog

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()  # Call parent init
        self.setWindowTitle("FRC Path Editor")
        self.resize(1000, 600)
        self.project_manager = ProjectManager()
        self.path = Path()  # start empty; will be replaced on project load
        
        # Initialize undo/redo system
        self.undo_manager = UndoRedoManager()
        self.undo_manager.add_callback(self._update_undo_redo_actions)

        # Build menubar FIRST before setting up the layout
        self._build_menu_bar()

        central = QWidget()  # Blank container for content
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)  # Horizontal split
        try:
            # Eliminate outer margins so both canvas and sidebar bottoms align to window bottom
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
        except Exception:
            pass

        # Canvas (left)
        # Initialize canvas with default robot dims; will update after config load
        self.canvas = CanvasView()
        layout.addWidget(self.canvas, stretch=3)  # Wider

        # Thin vertical divider between canvas and sidebar
        try:
            divider = QFrame()
            divider.setObjectName("sidebarDivider")
            divider.setFrameShape(QFrame.NoFrame)
            divider.setFixedWidth(1)
            divider.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
            divider.setStyleSheet("QFrame#sidebarDivider { background-color: #3b3b3b; }")
            layout.addWidget(divider)
        except Exception:
            pass

        # Placeholder for sidebar (right)
        self.sidebar = Sidebar()
        # Provide project manager to sidebar for config defaults
        self.sidebar.project_manager = self.project_manager
        # Provide project manager to canvas for config defaults
        self.canvas.set_project_manager(self.project_manager)
        # Connect canvas to undo manager (no longer needed for toolbar, but keep for other features)
        # self.canvas.set_undo_redo_manager(self.undo_manager)
        self.sidebar.set_path(self.path)
        layout.addWidget(self.sidebar, stretch=1)  # Narrower

        # Initialize canvas with path
        self.canvas.set_path(self.path)
        # Build initial simulation
        self.canvas.request_simulation_rebuild()

        # Wire up interactions: sidebar <-> canvas
        self.sidebar.elementSelected.connect(self.canvas.select_index, Qt.QueuedConnection)
        self.canvas.elementSelected.connect(self.sidebar.select_index, Qt.QueuedConnection)
        # Ranged constraints preview from sidebar -> canvas overlay
        try:
            self.sidebar.constraintRangePreviewRequested.connect(lambda key, s, e: self.canvas.show_constraint_range_overlay(key, s, e))
            self.sidebar.constraintRangePreviewCleared.connect(lambda: self.canvas.clear_constraint_range_overlay())
        except Exception:
            pass

        # Sidebar changes -> canvas refresh
        self.sidebar.modelChanged.connect(self.canvas.refresh_from_model)
        self.sidebar.modelChanged.connect(self.canvas.update_handoff_radius_visualizers)
        self.sidebar.modelChanged.connect(self.canvas.request_simulation_rebuild)
        self.sidebar.modelStructureChanged.connect(lambda: self.canvas.set_path(self.path))
        self.sidebar.modelStructureChanged.connect(self.canvas.request_simulation_rebuild)
        # Global UI clicks: clear ranged overlay unless the click target is a range-related control
        try:
            app = QApplication.instance()
            if app is not None:
                app.installEventFilter(self)
            # Also filter events on the window itself as a fallback
            self.installEventFilter(self)
        except Exception:
            pass
        # Sidebar -> undo management
        self.sidebar.aboutToChange.connect(self._on_sidebar_about_to_change)
        self.sidebar.userActionOccurred.connect(self._on_sidebar_action_committed)

        # Canvas interactions -> update model and sidebar
        self.canvas.elementMoved.connect(self._on_canvas_element_moved, Qt.QueuedConnection)
        self.canvas.elementRotated.connect(self._on_canvas_element_rotated, Qt.QueuedConnection)
        # Handle start and end of drags for undo/redo
        self.canvas.elementSelected.connect(self._on_canvas_element_pressed, Qt.QueuedConnection)
        self.canvas.elementDragFinished.connect(self._on_canvas_drag_finished, Qt.QueuedConnection)
        self.canvas.rotationDragFinished.connect(self._on_canvas_rotation_finished, Qt.QueuedConnection)
        # Canvas delete key -> sidebar delete current element
        self.canvas.deleteSelectedRequested.connect(self._delete_selected_element)
        # Sidebar delete key -> same handler
        self.sidebar.deleteSelectedRequested.connect(self._delete_selected_element)

        # Auto-save debounce timer
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(300)
        self._autosave_timer.timeout.connect(self._do_autosave)

        # Hook autosave on model changes
        self.sidebar.modelChanged.connect(self._schedule_autosave)
        self.sidebar.modelStructureChanged.connect(self._schedule_autosave)
        self.canvas.elementDragFinished.connect(self._schedule_autosave)
        
        # Hook undo/redo for sidebar changes - simple approach to capture state before changes
        self.sidebar.elementSelected.connect(self._on_element_selected_for_undo)

        # Menu bar already built earlier
        
        # Create status bar for current path display
        self.statusBar = self.statusBar()
        self.statusBar.showMessage("No path loaded")

        # Startup: load last project or prompt
        QTimer.singleShot(0, self._startup_load)

        # Stabilization flag for fullscreen/window state transitions
        self._layout_stabilizing: bool = False
        # Track config-edit undo session state
        self._config_undo_recorded: bool = False
        self._config_edit_old_config: dict | None = None
        # Mark sidebar ready after initial layout
        QTimer.singleShot(0, self.sidebar.mark_ready)

    def _delete_selected_element(self):
        idx = self.sidebar.get_selected_index()
        if idx is None:
            return
        # Record undo snapshot before deletion
        old_state = copy.deepcopy(self.path)
        self.sidebar._on_remove_element(idx)
        self._record_path_change("Delete element", old_state)

    def changeEvent(self, event):
        # Detect window state changes (e.g., entering/exiting fullscreen) and
        # enable a brief stabilization window to avoid re-entrant UI churn.
        if event.type() == QEvent.WindowStateChange:
            self._layout_stabilizing = True
            try:
                self.sidebar.set_suspended(True)
            except Exception:
                pass
            # Clear after a short delay once layout settles
            def _clear():
                setattr(self, '_layout_stabilizing', False)
                try:
                    self.sidebar.set_suspended(False)
                except Exception:
                    pass
            QTimer.singleShot(1000, _clear)
        super().changeEvent(event)

    def eventFilter(self, obj, event):
        try:
            if event.type() == QEvent.MouseButtonPress:
                # If click is not within a range-related control in the sidebar, clear overlay
                target_widget = obj if isinstance(obj, QWidget) else None
                # Walk up parent chain to see if any ancestor is range-related
                def _belongs_to_range_controls(widget: QWidget) -> bool:
                    try:
                        if widget is None:
                            return False
                        # If click lands inside the sidebar's elements list, this is unrelated
                        try:
                            if hasattr(self.sidebar, 'points_list') and self.sidebar.points_list is not None:
                                pl = self.sidebar.points_list
                                curr = widget
                                steps = 0
                                while curr is not None and steps < 12:
                                    if curr is pl:
                                        return False
                                    curr = curr.parent() if hasattr(curr, 'parent') else None
                                    steps += 1
                        except Exception:
                            pass
                        if hasattr(self.sidebar, 'is_widget_range_related') and callable(self.sidebar.is_widget_range_related):
                            curr = widget
                            steps = 0
                            while curr is not None and steps < 12:
                                if self.sidebar.is_widget_range_related(curr):
                                    return True
                                curr = curr.parent() if hasattr(curr, 'parent') else None
                                steps += 1
                    except Exception:
                        return False
                    return False
                if not _belongs_to_range_controls(target_widget):
                    try:
                        self.sidebar.clear_active_preview()
                    except Exception:
                        pass
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def showEvent(self, event):
        super().showEvent(event)
        # Mark sidebar ready after the window is shown
        QTimer.singleShot(0, self.sidebar.mark_ready)

    # ---------------- Menu Bar ----------------
    def _build_menu_bar(self):
        bar: QMenuBar = self.menuBar()
        # Ensure menu bar is visible
        bar.setVisible(True)
        bar.setNativeMenuBar(False)  # Force Qt menu bar instead of native macOS menu
        # Style to visually align with the app's dark UI
        try:
            bar.setStyleSheet(
                """
                QMenuBar {
                    background-color: #2f2f2f;
                    border: none;
                    border-bottom: 1px solid #4a4a4a;
                    padding: 1px 6px;
                    color: #eeeeee;
                    font-size: 13px;
                }
                QMenuBar::item {
                    background: transparent;
                    padding: 3px 6px;
                    margin: 0px 2px;
                    border-radius: 4px;
                    border-left: 1px solid #3b3b3b; /* slim vertical separator */
                }
                QMenuBar::item:selected {
                    background: #555555;
                }
                QMenuBar::item:pressed {
                    background: #666666;
                }

                QMenu {
                    background-color: #242424;
                    border: 1px solid #3f3f3f;
                    color: #f0f0f0;
                    padding: 3px 0;
                }
                QMenu::item {
                    padding: 3px 10px;
                    margin: 1px 3px;
                    border-radius: 3px;
                }
                QMenu::item:selected {
                    background: #555555;
                }
                QMenu::separator {
                    height: 1px;
                    margin: 2px 6px; /* slim horizontal spacers */
                    background: #3b3b3b;
                }
                QMenu::indicator {
                    background: transparent;
                }
                """
            )
        except Exception:
            pass
        
        # Project menu - for opening and managing projects
        project_menu: QMenu = bar.addMenu("Project")
        self.action_open_project = QAction("Open Project…", self)
        self.action_open_project.triggered.connect(self._action_open_project)
        project_menu.addAction(self.action_open_project)
        project_menu.addSeparator()
        
        # Recent Projects submenu
        self.menu_recent_projects: QMenu = project_menu.addMenu("Recent Projects")
        self.menu_recent_projects.aboutToShow.connect(self._populate_recent_projects)
        
        # Path menu - for managing paths
        path_menu: QMenu = bar.addMenu("Path")
        
        # Current Path display (read-only)
        self.action_current_path = QAction("Current: (No Path)", self)
        self.action_current_path.setEnabled(False)  # Make it read-only
        path_menu.addAction(self.action_current_path)
        
        path_menu.addSeparator()  # Add a separator line
        
        # Load Path submenu (dynamic)
        self.menu_load_path: QMenu = path_menu.addMenu("Load Path")
        self.menu_load_path.aboutToShow.connect(self._populate_load_path_menu)
        path_menu.addSeparator()

        # Create New Path action
        self.action_new_path = QAction("Create New Path", self)
        self.action_new_path.triggered.connect(self._action_create_new_path)
        path_menu.addAction(self.action_new_path)
        path_menu.addSeparator()

        # Save As…
        self.action_save_as = QAction("Save Path As…", self)
        self.action_save_as.triggered.connect(self._action_save_as)
        path_menu.addAction(self.action_save_as)
        path_menu.addSeparator()
        
        # Rename Path action
        self.action_rename_path = QAction("Rename Path…", self)
        self.action_rename_path.triggered.connect(self._action_rename_path)
        path_menu.addAction(self.action_rename_path)
        path_menu.addSeparator()
        
        # Delete Path action (opens dialog)
        self.action_delete_path = QAction("Delete Paths...", self)
        self.action_delete_path.triggered.connect(self._show_delete_path_dialog)
        path_menu.addAction(self.action_delete_path)
        
        # Edit menu - for undo/redo (placed after Path, before Settings)
        edit_menu: QMenu = bar.addMenu("Edit")
        
        # Create undo/redo actions with shortcuts and small icons
        self.action_undo = QAction(self._create_arrow_icon("undo", 12), "Undo", self)
        self.action_undo.setShortcut(QKeySequence.Undo)  # Use standard undo shortcut
        self.action_undo.triggered.connect(self._action_undo)
        self.action_undo.setEnabled(False)  # Will be enabled when undo is available
        edit_menu.addAction(self.action_undo)
        edit_menu.addSeparator()
        
        self.action_redo = QAction(self._create_arrow_icon("redo", 12), "Redo", self)
        self.action_redo.setShortcut(QKeySequence.Redo)  # Use standard redo shortcut
        self.action_redo.triggered.connect(self._action_redo)
        self.action_redo.setEnabled(False)  # Will be enabled when redo is available
        edit_menu.addAction(self.action_redo)
        
        # Settings menu - for configuration
        settings_menu: QMenu = bar.addMenu("Settings")
        self.action_edit_config = QAction("Edit Config…", self)
        self.action_edit_config.triggered.connect(self._action_edit_config)
        settings_menu.addAction(self.action_edit_config)
        
        # Also add actions to main window to ensure shortcuts work
        self.addAction(self.action_undo)
        self.addAction(self.action_redo)
        
        # Force menu bar to be visible and sized properly
        menu_bar = self.menuBar()
        menu_bar.setVisible(True)
        menu_bar.show()
        menu_bar.setMinimumHeight(30)
        menu_bar.setMaximumHeight(40)
        
        # Try different approaches to force visibility
        self.setMenuBar(menu_bar)  # Explicitly set the menu bar
        menu_bar.raise_()  # Bring to front
        
        # Debug: Try to force a repaint
        menu_bar.update()
        self.update()

    def _create_arrow_icon(self, direction: str, size: int = 16) -> QIcon:
        """Create a small arrow icon for undo/redo buttons."""
        try:
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            
            # Set up pen and brush - smaller line width for delicate arrows
            pen = QPen(QColor("#333333"), 1)
            brush = QBrush(QColor("#333333"))
            painter.setPen(pen)
            painter.setBrush(brush)
            
            # Create simple arrow shape based on direction
            center_x, center_y = size // 2, size // 2
            arrow_size = size // 4  # Much smaller arrows
            
            if direction == "undo":  # Left arrow
                arrow = QPolygon([
                    QPoint(center_x - arrow_size, center_y),
                    QPoint(center_x + arrow_size//2, center_y - arrow_size//2),
                    QPoint(center_x + arrow_size//2, center_y - arrow_size//4),
                    QPoint(center_x, center_y),
                    QPoint(center_x + arrow_size//2, center_y + arrow_size//4),
                    QPoint(center_x + arrow_size//2, center_y + arrow_size//2)
                ])
            else:  # "redo" - Right arrow
                arrow = QPolygon([
                    QPoint(center_x + arrow_size, center_y),
                    QPoint(center_x - arrow_size//2, center_y - arrow_size//2),
                    QPoint(center_x - arrow_size//2, center_y - arrow_size//4),
                    QPoint(center_x, center_y),
                    QPoint(center_x - arrow_size//2, center_y + arrow_size//4),
                    QPoint(center_x - arrow_size//2, center_y + arrow_size//2)
                ])
            
            painter.drawPolygon(arrow)
            painter.end()
            
            return QIcon(pixmap)
        except Exception:
            # Return empty icon on error
            return QIcon()



    def _populate_load_path_menu(self):
        self.menu_load_path.clear()
        files = self.project_manager.list_paths()
        if not files:
            a = QAction("(No paths)", self)
            a.setEnabled(False)
            self.menu_load_path.addAction(a)
            return
        for fname in files:
            # Skip the currently opened path
            if fname == self.project_manager.current_path_file:
                continue
            act = QAction(fname, self)
            act.triggered.connect(lambda checked=False, f=fname: self._load_path_file(f))
            self.menu_load_path.addAction(act)

    def _populate_recent_projects(self):
        self.menu_recent_projects.clear()
        recents = self.project_manager.recent_projects()
        if not recents:
            a = QAction("(No recent projects)", self)
            a.setEnabled(False)
            self.menu_recent_projects.addAction(a)
            return
        for d in recents:
            label = d
            act = QAction(label, self)
            act.triggered.connect(lambda checked=False, dirpath=d: self._open_recent_project(dirpath))
            self.menu_recent_projects.addAction(act)

    def _show_delete_path_dialog(self):
        """Show a dialog for selecting and deleting paths"""
        if not self.project_manager.has_valid_project():
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "No Project", "Please open a project first.")
            return
            
        files = self.project_manager.list_paths()
        if not files:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "No Paths", "No paths found to delete.")
            return
        
        # Create a custom dialog
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QCheckBox, QPushButton, QLabel, QScrollArea, QWidget
        from PySide6.QtCore import Qt
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Delete Paths")
        dialog.setModal(True)
        dialog.resize(400, 300)
        
        layout = QVBoxLayout(dialog)
        
        # Header
        header_label = QLabel("Select paths to delete:")
        header_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(header_label)
        
        # Scrollable area for checkboxes
        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        
        # Create checkboxes for each path
        checkboxes = {}
        for fname in files:
            cb = QCheckBox(fname)
            # Mark current path with an indicator
            if fname == self.project_manager.current_path_file:
                cb.setText(f"✓ {fname} (Current)")
                cb.setStyleSheet("color: #d32f2f; font-weight: bold;")
            checkboxes[fname] = cb
            scroll_layout.addWidget(cb)
        
        scroll_widget.setLayout(scroll_layout)
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)
        
        # Button layout
        button_layout = QHBoxLayout()
        
        # Select All/None buttons
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(lambda: [cb.setChecked(True) for cb in checkboxes.values()])
        
        select_none_btn = QPushButton("Select None")
        select_none_btn.clicked.connect(lambda: [cb.setChecked(False) for cb in checkboxes.values()])
        
        button_layout.addWidget(select_all_btn)
        button_layout.addWidget(select_none_btn)
        button_layout.addStretch()
        
        # Delete and Cancel buttons
        delete_btn = QPushButton("Delete Selected")
        delete_btn.setStyleSheet("background-color: #d32f2f; color: white; font-weight: bold;")
        delete_btn.clicked.connect(lambda: self._delete_paths_from_dialog(checkboxes, dialog))
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        
        button_layout.addWidget(delete_btn)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        
        # Show dialog
        dialog.exec()

    # ---------------- Startup and Actions ----------------
    def _startup_load(self):
        if self.project_manager.load_last_project() and self.project_manager.has_valid_project():
            # Load config and apply canvas dims
            cfg = self.project_manager.load_config()
            self._apply_robot_dims_from_config(cfg)
            # Config impacts constraints; rebuild sim
            self.canvas.request_simulation_rebuild()
            # Load last or first or create
            path, filename = self.project_manager.load_last_or_first_or_create()
            self._set_path_model(path)
            # Update the current path display after startup
            self._update_current_path_display()
        else:
            # No valid project – show file dialog
            self._action_open_project(force_dialog=True)

    def _apply_robot_dims_from_config(self, cfg):
        try:
            length_m = float(cfg.get("robot_length_meters", 0.60) or 0.60)
            width_m = float(cfg.get("robot_width_meters", 0.60) or 0.60)
        except Exception:
            length_m, width_m = 0.60, 0.60
        self.canvas.set_robot_dimensions(length_m, width_m)

    def _action_open_project(self, force_dialog: bool = False):
        # Always prompt the user to select a project directory. Initialize to current project or home.
        start_dir = self.project_manager.project_dir or os.path.expanduser("~")
        directory = QFileDialog.getExistingDirectory(self, "Open Project Directory", start_dir)
        if not directory:
            # User canceled; leave current project/path unchanged
            return
        self.project_manager.set_project_dir(directory)
        cfg = self.project_manager.load_config()
        self._apply_robot_dims_from_config(cfg)
        path, filename = self.project_manager.load_last_or_first_or_create()
        self._set_path_model(path)
        # Update the current path display after opening project
        self._update_current_path_display()
        self.canvas.request_simulation_rebuild()

    def _open_recent_project(self, directory: str):
        if not directory:
            return
        self.project_manager.set_project_dir(directory)
        cfg = self.project_manager.load_config()
        self._apply_robot_dims_from_config(cfg)
        path, filename = self.project_manager.load_last_or_first_or_create()
        self._set_path_model(path)
        # Update the current path display after opening recent project
        self._update_current_path_display()
        self.canvas.request_simulation_rebuild()

    def _action_undo(self):
        """Perform undo operation."""
        command = self.undo_manager.undo()
        if command:
            # Refresh all UI components
            self._refresh_after_undo_redo()
    
    def _action_redo(self):
        """Perform redo operation."""
        command = self.undo_manager.redo()
        if command:
            # Refresh all UI components
            self._refresh_after_undo_redo()
    
    def _update_undo_redo_actions(self):
        """Update the enabled state and text of undo/redo actions."""
        # Update undo action
        if self.undo_manager.can_undo():
            desc = self.undo_manager.get_undo_description()
            self.action_undo.setText(f"Undo {desc}" if desc else "Undo")
            self.action_undo.setEnabled(True)
        else:
            self.action_undo.setText("Undo")
            self.action_undo.setEnabled(False)
        
        # Update redo action
        if self.undo_manager.can_redo():
            desc = self.undo_manager.get_redo_description()
            self.action_redo.setText(f"Redo {desc}" if desc else "Redo")
            self.action_redo.setEnabled(True)
        else:
            self.action_redo.setText("Redo")
            self.action_redo.setEnabled(False)
    
    def _refresh_after_undo_redo(self):
        """Refresh all UI components after an undo/redo operation."""
        # Refresh canvas from model
        self.canvas.set_path(self.path)
        self.canvas.refresh_from_model()
        self.canvas.update_handoff_radius_visualizers()
        self.canvas.request_simulation_rebuild()
        
        # Refresh sidebar
        self.sidebar.set_path(self.path)
        self.sidebar.refresh_current_selection()
        
        # Apply config changes to canvas
        self._apply_robot_dims_from_config(self.project_manager.config)
        
        # Update path display
        self._update_current_path_display()
    
    def _record_path_change(self, description: str, old_path: Path = None):
        """Record a path change in the undo system."""
        if old_path is None:
            # Create a snapshot of the current path before change
            old_path = copy.deepcopy(self.path)
        
        # The new path state will be captured after the change is made
        def create_command():
            new_path = copy.deepcopy(self.path)
            command = PathCommand(
                path_ref=self.path,
                old_state=old_path,
                new_state=new_path,
                description=description,
                on_change_callback=self._refresh_after_undo_redo
            )
            self.undo_manager.execute_command(command)
        
        # Defer command creation to next event loop iteration
        # so the change is applied first
        QTimer.singleShot(0, create_command)

    def _on_sidebar_about_to_change(self, description: str):
        """Capture pre-change snapshot for undo before a sidebar-driven edit."""
        self._sidebar_old_state = copy.deepcopy(self.path)
        self._sidebar_action_desc = description

    def _on_sidebar_action_committed(self, description: str):
        """Commit undo command after sidebar-driven edit completes with a clear description."""
        try:
            old_state = getattr(self, '_sidebar_old_state', None)
            desc = description or getattr(self, '_sidebar_action_desc', "Edit")
            if old_state is not None:
                self._record_path_change(desc, old_state)
        finally:
            if hasattr(self, '_sidebar_old_state'):
                delattr(self, '_sidebar_old_state')
            if hasattr(self, '_sidebar_action_desc'):
                delattr(self, '_sidebar_action_desc')
    
    def _record_config_change(self, description: str, old_config: dict = None):
        """Record a config change in the undo system."""
        if old_config is None:
            old_config = copy.deepcopy(self.project_manager.config)
        
        def create_command():
            new_config = copy.deepcopy(self.project_manager.config)
            command = ConfigCommand(
                project_manager=self.project_manager,
                old_config=old_config,
                new_config=new_config,
                description=description,
                on_change_callback=self._refresh_after_undo_redo
            )
            self.undo_manager.execute_command(command)
        
        QTimer.singleShot(0, create_command)

    def _action_edit_config(self):
        old_config = copy.deepcopy(self.project_manager.config)
        # Begin a config-edit session: capture original for undo on first live change
        self._config_edit_old_config = copy.deepcopy(old_config)
        self._config_undo_recorded = False
        cfg = self.project_manager.load_config()
        dlg = ConfigDialog(self, cfg, on_change=self._on_config_live_change)
        if dlg.exec() == QDialog.Accepted:
            new_cfg = dlg.get_values()
            self.project_manager.save_config(new_cfg)
            # Apply to canvas if robot dims changed
            self._apply_robot_dims_from_config(self.project_manager.config)
            # Constraints/gains may change; rebuild sim
            self.canvas.request_simulation_rebuild()
            # Sidebar will use defaults from project_manager when adding optionals

            # Refresh sidebar for current selection so defaults/UI reflect changes
            self.sidebar.refresh_current_selection()
            
            # Record the config change for undo/redo if not already recorded via live-change
            if not self._config_undo_recorded:
                self._record_config_change("Edit Config", old_config)
        # Clear session flags after dialog closes
        self._config_edit_old_config = None
        self._config_undo_recorded = False

    def _on_config_live_change(self, key: str, value: float):
        # Record each individual config change for granular undo/redo
        old_config = copy.deepcopy(self.project_manager.config)
        # Persist to config immediately
        self.project_manager.save_config({key: value})
        # Create undo command with specific description
        key_label = self._get_config_key_label(key)
        desc = f"Edit Config: {key_label}"
        self._record_config_change(desc, old_config)
        
        if key in ("robot_length_meters", "robot_width_meters"):
            self._apply_robot_dims_from_config(self.project_manager.config)
        # Config changes affect simulation constraints/gains; rebuild sim
        self.canvas.request_simulation_rebuild()
        # For optional defaults, no immediate changes unless fields are being added later.
        # Still refresh visible sidebar to reflect any fields that might show defaults.
        self.sidebar.refresh_current_selection()
        # If the config dialog is open, keep its spinners in sync with potential external config changes
        try:
            active = self.activeWindow()
            if isinstance(active, ConfigDialog):
                active.sync_from_config(self.project_manager.config)
        except Exception:
            pass

    def _get_config_key_label(self, key: str) -> str:
        """Get a human-readable label for a config key."""
        labels = {
            'robot_length_meters': 'Robot Length',
            'robot_width_meters': 'Robot Width',
            'final_velocity_meters_per_sec': 'Default Final Velocity',
            'max_velocity_meters_per_sec': 'Default Max Velocity',
            'max_acceleration_meters_per_sec2': 'Default Max Accel',
            'intermediate_handoff_radius_meters': 'Default Handoff Radius',
            'max_velocity_deg_per_sec': 'Default Max Rot Vel',
            'max_acceleration_deg_per_sec2': 'Default Max Rot Accel',
        }
        return labels.get(key, key)

    def _load_path_file(self, filename: str):
        p = self.project_manager.load_path(filename)
        if p is None:
            return
        self._set_path_model(p)
        # Update the current path display after loading a path
        self._update_current_path_display()
        self.canvas.request_simulation_rebuild()

    def _action_save_as(self):
        if not self.project_manager.get_paths_dir():
            # Need project first
            self._action_open_project(force_dialog=True)
            if not self.project_manager.get_paths_dir():
                return
        base_dir = self.project_manager.get_paths_dir()
        suggested = self.project_manager.current_path_file or "untitled.json"
        # Use global os for initial join to avoid unbound local
        file_tuple = QFileDialog.getSaveFileName(self, "Save Path As", os.path.join(base_dir, suggested), "JSON Files (*.json)")
        filepath = file_tuple[0]
        if not filepath:
            return
        # Normalize to project paths folder
        try:
            import os as _os
            folder, name = _os.path.split(filepath)
            if _os.path.abspath(folder) != _os.path.abspath(base_dir):
                # Force save into paths dir
                name = name or suggested
                filepath = _os.path.join(base_dir, name)
        except Exception:
            pass
        # Save
        try:
            import os as _os
            filename = _os.path.basename(filepath)
            self.project_manager.save_path(self.path, filename)
            # Auto-open the newly saved path
            self._load_path_file(filename)
        except Exception:
            pass

    def _action_create_new_path(self):
        """Create a new blank path and clear the current model"""
        # Create a new empty path
        new_path = Path()
        self._set_path_model(new_path)
        
        # If we have a valid project, save it as a new file
        if self.project_manager.has_valid_project():
            # Prompt user for filename
            from PySide6.QtWidgets import QInputDialog
            filename, ok = QInputDialog.getText(
                self, "Create New Path", 
                "Enter path name:", 
                text="new_path"
            )
            
            if ok and filename:
                # Add .json extension if not present
                if not filename.endswith('.json'):
                    filename += '.json'
                
                # Check if file already exists
                if os.path.exists(os.path.join(self.project_manager.project_dir, "paths", filename)):
                    from PySide6.QtWidgets import QMessageBox
                    QMessageBox.warning(self, "File Exists", f"A path named '{filename}' already exists. Please choose a different name.")
                    return
                
                # Save the new path
                self.project_manager.save_path(new_path, filename)
                # Refresh the load path menu
                self._populate_load_path_menu()
            else:
                # User cancelled, just show the empty path without saving
                print("User cancelled path creation")
        else:
            # No project open, just show the empty path
            print("No project open - showing empty path")

    def _action_rename_path(self):
        """Rename the currently open path file"""
        if not self.project_manager.has_valid_project():
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "No Project", "Please open a project first.")
            return
            
        if not self.project_manager.current_path_file:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "No Path", "No path is currently open to rename.")
            return
        
        # Get current filename without extension
        current_name = self.project_manager.current_path_file
        if current_name.endswith('.json'):
            current_name = current_name[:-5]
        
        # Prompt user for new filename
        from PySide6.QtWidgets import QInputDialog
        new_filename, ok = QInputDialog.getText(
            self, "Rename Path", 
            f"Enter new name for '{current_name}':", 
            text=current_name
        )
        
        if ok and new_filename:
            # Add .json extension if not present
            if not new_filename.endswith('.json'):
                new_filename += '.json'
            
            # Check if new filename already exists
            if new_filename != self.project_manager.current_path_file:
                if os.path.exists(os.path.join(self.project_manager.project_dir, "paths", new_filename)):
                    from PySide6.QtWidgets import QMessageBox
                    QMessageBox.warning(self, "File Exists", f"A path named '{new_filename}' already exists. Please choose a different name.")
                    return
                
                # Rename the file
                try:
                    old_path = os.path.join(self.project_manager.project_dir, "paths", self.project_manager.current_path_file)
                    new_path = os.path.join(self.project_manager.project_dir, "paths", new_filename)
                    os.rename(old_path, new_path)
                    
                    # Update the project manager's current path file
                    self.project_manager.current_path_file = new_filename
                    self.project_manager.settings.setValue(self.project_manager.KEY_LAST_PATH_FILE, new_filename)
                    
                    # Update the UI
                    self._update_current_path_display()
                    self._populate_load_path_menu()
                    
                    from PySide6.QtWidgets import QMessageBox
                    QMessageBox.information(self, "Path Renamed", f"Successfully renamed to '{new_filename}'")
                    
                except Exception as e:
                    from PySide6.QtWidgets import QMessageBox
                    QMessageBox.critical(self, "Rename Failed", f"Failed to rename path: {str(e)}")

    def _delete_paths_from_dialog(self, checkboxes: dict, dialog: QDialog):
        """Delete the selected paths from the dialog after confirmation"""
        # Get selected paths from checkboxes
        selected_paths = [fname for fname, cb in checkboxes.items() if cb.isChecked()]
        
        if not selected_paths:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "No Selection", "Please select at least one path to delete.")
            return
        
        # Check if current path is being deleted
        current_path_deleted = False
        if self.project_manager.current_path_file in selected_paths:
            current_path_deleted = True
        
        # Show confirmation dialog
        from PySide6.QtWidgets import QMessageBox
        if len(selected_paths) == 1:
            msg = f"Are you sure you want to delete '{selected_paths[0]}'?"
            if current_path_deleted:
                msg += "\n\n⚠️  This will close the currently open path."
        else:
            msg = f"Are you sure you want to delete {len(selected_paths)} paths?\n\n" + "\n".join(f"• {path}" for path in selected_paths)
            if current_path_deleted:
                msg += "\n\n⚠️  This will close the currently open path."
        
        reply = QMessageBox.question(
            self, "Confirm Deletion", msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No  # Default to No for safety
        )
        
        if reply == QMessageBox.Yes:
            # Delete the selected paths
            deleted_count = 0
            
            for path_name in selected_paths:
                if self.project_manager.delete_path(path_name):
                    deleted_count += 1
            
            # Show result
            if deleted_count == 1:
                QMessageBox.information(self, "Path Deleted", f"Successfully deleted '{selected_paths[0]}'")
            else:
                QMessageBox.information(self, "Paths Deleted", f"Successfully deleted {deleted_count} paths")
            
            # Close the dialog
            dialog.accept()
            
            # Handle current path deletion
            if current_path_deleted:
                self._handle_current_path_deleted()
            
            # Refresh the load path menu since we no longer have a delete menu
            self._populate_load_path_menu()

    def _handle_current_path_deleted(self):
        """Handle the case where the currently open path was deleted"""
        # Clear the current path
        self._set_path_model(Path())
        self._update_current_path_display()
        
        # Check if there are other paths available
        available_paths = self.project_manager.list_paths()
        
        if not available_paths:
            # No paths left - just inform the user
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, 
                "No Paths Available", 
                "The current path was deleted and no other paths are available.\n\n"
                "You can create a new path or open a different project."
            )
            return
        
        # Ask user if they want to load another path
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self,
            "Current Path Deleted",
            f"The current path was deleted.\n\n"
            f"There are {len(available_paths)} other paths available.\n\n"
            "Would you like to load one of them?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes  # Default to Yes for convenience
        )
        
        if reply == QMessageBox.Yes:
            # Show path selection dialog
            self._show_path_selection_dialog()
        else:
            # User chose to continue without a path
            QMessageBox.information(
                self,
                "No Path Loaded",
                "You can create a new path or load an existing one from the Path menu."
            )

    def _show_path_selection_dialog(self):
        """Show a dialog for selecting which path to load"""
        available_paths = self.project_manager.list_paths()
        if not available_paths:
            return
        
        # Create a simple selection dialog
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QListWidget, QListWidgetItem
        from PySide6.QtCore import Qt
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Select Path to Load")
        dialog.setModal(True)
        dialog.resize(350, 250)
        
        layout = QVBoxLayout(dialog)
        
        # Header
        header_label = QLabel("Select a path to load:")
        header_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(header_label)
        
        # List of available paths
        path_list = QListWidget()
        for path_name in available_paths:
            item = QListWidgetItem(path_name)
            path_list.addItem(item)
        
        # Select the first item by default
        if path_list.count() > 0:
            path_list.setCurrentRow(0)
        
        layout.addWidget(path_list)
        
        # Button layout
        button_layout = QHBoxLayout()
        
        # Load and Cancel buttons
        load_btn = QPushButton("Load Selected")
        load_btn.setStyleSheet("background-color: #4caf50; color: white; font-weight: bold;")
        load_btn.clicked.connect(lambda: self._load_selected_path_from_dialog(path_list, dialog))
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(load_btn)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        
        # Show dialog
        dialog.exec()

    def _load_selected_path_from_dialog(self, path_list, dialog):
        """Load the selected path from the path selection dialog"""
        current_item = path_list.currentItem()
        if not current_item:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "No Selection", "Please select a path to load.")
            return
        
        selected_path = current_item.text()
        
        # Load the selected path
        path = self.project_manager.load_path(selected_path)
        if path is not None:
            self._set_path_model(path)
            self._update_current_path_display()
            dialog.accept()
        else:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", f"Failed to load path '{selected_path}'.")

    def _set_path_model(self, path: Path):
        self.path = path
        self.sidebar.set_path(self.path)
        self.canvas.set_path(self.path)
        # Update the current path display
        self._update_current_path_display()
        # Save immediately to ensure file exists
        self._schedule_autosave()
        # New path -> rebuild simulation
        self.canvas.request_simulation_rebuild()

    def _update_current_path_display(self):
        """Update the current path display in the menu, window title, and status bar"""
        if hasattr(self, 'action_current_path'):
            if self.project_manager.has_valid_project() and self.project_manager.current_path_file:
                # Show the current path filename
                path_name = self.project_manager.current_path_file
                if path_name.endswith('.json'):
                    path_name = path_name[:-5]  # Remove .json extension for display
                self.action_current_path.setText(f"Current: {path_name}")
                
                # Update window title to show current project and path
                project_name = os.path.basename(self.project_manager.project_dir)
                self.setWindowTitle(f"FRC Path Planning - {project_name} - {path_name}")
                
                # Update status bar
                if hasattr(self, 'statusBar'):
                    self.statusBar.showMessage(f"Current Path: {path_name} | Project: {project_name}")
            else:
                # No project or no current path
                self.action_current_path.setText("Current: (No Path)")
                self.setWindowTitle("FRC Path Planning")
                
                # Update status bar
                if hasattr(self, 'statusBar'):
                    self.statusBar.showMessage("No path loaded")

    def _on_canvas_element_pressed(self, index: int):
        """Called when an element is first pressed for drag/rotate. Snapshot for undo grouping."""
        self._drag_start_state = copy.deepcopy(self.path)
        self._rotate_start_state = copy.deepcopy(self.path)
    
    def _on_element_selected_for_undo(self, index: int):
        """Selection changes should not create undo entries; do nothing here."""
        return

    def _on_canvas_element_moved(self, index: int, x_m: float, y_m: float):
        # Suppress during window state transitions to avoid re-entrant churn
        if getattr(self, '_layout_stabilizing', False):
            return
        if index < 0 or index >= len(self.path.path_elements):
            return
        
        # Clamp via sidebar metadata to keep UI and model consistent
        x_m = clamp_from_metadata('x_meters', float(x_m))
        y_m = clamp_from_metadata('y_meters', float(y_m))
        elem = self.path.path_elements[index]
        if isinstance(elem, TranslationTarget):
            elem.x_meters = x_m
            elem.y_meters = y_m
        elif isinstance(elem, RotationTarget):
            # Compute t_ratio from drag position and neighbor anchors
            prev_pos = None
            for i in range(index - 1, -1, -1):
                e = self.path.path_elements[i]
                if isinstance(e, TranslationTarget):
                    prev_pos = (e.x_meters, e.y_meters)
                    break
                if isinstance(e, Waypoint):
                    prev_pos = (e.translation_target.x_meters, e.translation_target.y_meters)
                    break
            next_pos = None
            for i in range(index + 1, len(self.path.path_elements)):
                e = self.path.path_elements[i]
                if isinstance(e, TranslationTarget):
                    next_pos = (e.x_meters, e.y_meters)
                    break
                if isinstance(e, Waypoint):
                    next_pos = (e.translation_target.x_meters, e.translation_target.y_meters)
                    break
            if prev_pos is not None and next_pos is not None:
                ax, ay = prev_pos
                bx, by = next_pos
                dx = bx - ax
                dy = by - ay
                denom = dx * dx + dy * dy
                if denom > 0.0:
                    t = ((x_m - ax) * dx + (y_m - ay) * dy) / denom
                    if t < 0.0:
                        t = 0.0
                    elif t > 1.0:
                        t = 1.0
                    elem.t_ratio = float(t)
        elif isinstance(elem, Waypoint):
            elem.translation_target.x_meters = x_m
            elem.translation_target.y_meters = y_m
            # Waypoint rotation position is ratio-based; do not force x/y here

        self.sidebar.update_current_values_only()
        # defer autosave until drag finished; handled by elementDragFinished

    def _on_canvas_element_rotated(self, index: int, radians: float):
        # Suppress during window state transitions to avoid re-entrant churn
        if getattr(self, '_layout_stabilizing', False):
            return
        if index < 0 or index >= len(self.path.path_elements):
            return
        
        elem = self.path.path_elements[index]
        # Clamp using sidebar metadata (degrees domain), then convert back to radians
        degrees = math.degrees(radians)
        degrees = clamp_from_metadata('rotation_degrees', float(degrees))
        clamped_radians = math.radians(degrees)
        if isinstance(elem, RotationTarget):
            elem.rotation_radians = clamped_radians
        elif isinstance(elem, Waypoint):
            elem.rotation_target.rotation_radians = clamped_radians
        # Name the in-progress action for UI clarity
        try:
            if isinstance(elem, RotationTarget):
                self.action_undo.setText("Undo Rotate RotationTarget")
            elif isinstance(elem, Waypoint):
                self.action_undo.setText("Undo Rotate Waypoint")
        except Exception:
            pass
        # Update sidebar fields
        self.sidebar.update_current_values_only()
        # Debounced autosave on rotation changes
        self._schedule_autosave()

        # Debounce: capture the state at start of rotation (via _on_canvas_element_pressed) and
        # commit the undo entry when rotation drag finishes (see _on_canvas_rotation_finished).
        if not hasattr(self, '_rotate_start_state'):
            # First rotation change – snapshot pre-rotation state
            self._rotate_start_state = copy.deepcopy(self.path)

    def _reproject_all_rotation_positions(self):
        # No-op under ratio-based rotation positioning. Canvas derives positions from t_ratio.
        return

    def _project_point_between_neighbors(self, index: int, x_m: float, y_m: float) -> Tuple[float, float]:
        # Find previous and next translation/waypoint elements
        prev_pos = None
        for i in range(index - 1, -1, -1):
            e = self.path.path_elements[i]
            if isinstance(e, (TranslationTarget, Waypoint)):
                prev_pos = (e.x_meters, e.y_meters) if isinstance(e, TranslationTarget) else (
                    e.translation_target.x_meters, e.translation_target.y_meters)
                break
        next_pos = None
        for i in range(index + 1, len(self.path.path_elements)):
            e = self.path.path_elements[i]
            if isinstance(e, (TranslationTarget, Waypoint)):
                next_pos = (e.x_meters, e.y_meters) if isinstance(e, TranslationTarget) else (
                    e.translation_target.x_meters, e.translation_target.y_meters)
                break
        if prev_pos is None or next_pos is None:
            return x_m, y_m
        ax, ay = prev_pos
        bx, by = next_pos
        dx = bx - ax
        dy = by - ay
        denom = dx * dx + dy * dy
        if denom <= 0.0:
            return x_m, y_m
        t = ((x_m - ax) * dx + (y_m - ay) * dy) / denom
        if t < 0.0:
            t = 0.0
        elif t > 1.0:
            t = 1.0
        proj_x = ax + t * dx
        proj_y = ay + t * dy
        # Final clamp to field limits
        proj_x = clamp_from_metadata('x_meters', proj_x)
        proj_y = clamp_from_metadata('y_meters', proj_y)
        return proj_x, proj_y

    def _on_canvas_drag_finished(self, index: int):
        """Called once per item when the user releases the mouse after dragging."""
        if getattr(self, '_layout_stabilizing', False):
            return
        if index < 0 or index >= len(self.path.path_elements):
            return
        
        # Record the drag operation for undo/redo
        if hasattr(self, '_drag_start_state'):
            element_type = type(self.path.path_elements[index]).__name__
            self._record_path_change(f"Move {element_type}", self._drag_start_state)
            delattr(self, '_drag_start_state')
        
        # Remember which element was dragged so we can re-select it after any reordering
        dragged_elem = self.path.path_elements[index]

        # Re-evaluate rotation order now that the drag is complete
        self.sidebar._check_and_swap_rotation_targets()

        # Attempt to restore selection for the dragged element
        try:
            new_index = self.path.path_elements.index(dragged_elem)
        except ValueError:
            new_index = -1
        if new_index >= 0:
            self.sidebar.select_index(new_index)

    def _on_canvas_rotation_finished(self, index: int):
        """Record rotation change undo when the user releases the rotation handle."""
        if getattr(self, '_layout_stabilizing', False):
            return
        if not hasattr(self, '_rotate_start_state'):
            return
        try:
            elem = self.path.path_elements[index]
            if isinstance(elem, RotationTarget):
                self._record_path_change("Rotate RotationTarget", self._rotate_start_state)
            elif isinstance(elem, Waypoint):
                self._record_path_change("Rotate Waypoint", self._rotate_start_state)
        finally:
            if hasattr(self, '_rotate_start_state'):
                delattr(self, '_rotate_start_state')

    # ---------------- Autosave ----------------
    def _schedule_autosave(self):
        # Coalesce frequent updates
        self._autosave_timer.start()

    def _do_autosave(self):
        # Ensure project dir exists before saving
        if not self.project_manager.has_valid_project():
            return
        self.project_manager.save_path(self.path)