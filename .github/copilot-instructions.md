# AI Assistant Instructions for FRC-PTP-GUI

Concise domain + project knowledge so an AI agent can be productive quickly. Keep responses pragmatic and aligned with these patterns.

## 1. Purpose & Big Picture
Desktop Qt (PySide6) app for editing & simulating FRC robot motion paths. Core loop:
User edits path elements (translation / rotation / waypoint) on a scaled field canvas -> model (`models/path_model.py`) updates -> simulation (`models/simulation.py`) recomputes poses -> UI reflects robot playback & trail.

## 2. Key Modules & Roles
- `main.py`: App bootstrap; creates `MainWindow`.
- `ui/main_window.py`: Wires together Canvas + Sidebar + menus + undo/autosave.
- `ui/canvas/`: GraphicsView-based field editor.
  - `view.py` (`CanvasView`): Scene graph, scaling, zoom/pan, element items, simulation overlays.
  - `items/`: QGraphicsItem subclasses for path elements (`elements.py`) & robot sim (`sim.py`).
  - `components/transport.py`: Play/pause & timeline slider.
  - `constants.py`: Field & geometry dimensions (meters) used as logical coordinate system.
- `ui/sidebar/`: Element list, property editors, constraint tools.
  - `components/*`: Managers and property editors; emit signals consumed by `MainWindow`.
- `models/path_model.py`: Data classes: `Path`, `TranslationTarget`, `RotationTarget`, `Waypoint`; serialization-friendly attributes; units in meters & radians.
- `models/simulation.py`: `simulate_path(path, config)` returns kinematic timing, poses, optional trail points.
- `utils/project_manager.py`: Loads project `config.json`, path files, defaults (e.g., handoff radius); provides defaults to UI.
- `utils/undo_system.py`: Simple command pattern wrappers for path/config modifications.

## 3. Data & Coordinate Conventions
- Scene units == meters; `FIELD_LENGTH_METERS` x `FIELD_WIDTH_METERS` defines logical rectangle.
- Y axis in model: increasing upward; in scene: Qt's down-positive, so conversion flips y (`_scene_from_model` / `_model_from_scene`). Keep conversions localized; don't duplicate logic.
- Rotation angles stored in radians; some UI may show degrees (convert only at presentation layer).
- Waypoint combines translation + rotation; rotation-only nodes interpolate position along segment via `t_ratio`.

## 4. Element Rendering Logic (Canvas)
- Background field image is aspect-fit scaled; positioned bottom-aligned; maintain logical field size independent of image pixels.
- Each path element gets a shape (circle translation, dashed rectangle rotation, solid rectangle waypoint) plus optional rotation handle & handoff radius overlay.
- Rotation targets are constrained to their neighbor segment: dragging projects point onto segment line; `t_ratio` persisted.
- Connection lines & constraint overlays separate arrays for cheap rebuild.

## 5. Simulation Loop
- Debounced (`_sim_debounce` 200ms) after structural / positional changes.
- `simulate_path` returns time-sorted poses; stored in `_sim_poses_by_time` + `_sim_times_sorted`.
- Transport controls drive timer (20ms tick) -> `_seek_to_time` sets robot pose + reveals trail line segments incrementally.
- Trail is preallocated line items for performance; visibility toggled instead of reallocating.

## 6. Signals & Cross-Component Communication
- Canvas emits: `elementMoved`, `elementRotated`, `elementSelected`, `elementDragFinished`, `rotationDragFinished`, `deleteSelectedRequested`.
- Sidebar emits: `modelChanged`, `modelStructureChanged`, `elementSelected`, range preview signals.
- `MainWindow` bridges these; undo system snapshots on drag start/end & sidebar changes.

## 7. Project / Persistence Workflow
- Open project: directory with `config.json` + `paths/*.json`.
- Path JSON mirrors `path_model` attributes; omit `None` fields.
- Auto-save triggers after debounce on modifications (sidebar & canvas drags).
- Robot dimension changes propagate to canvas via `set_robot_dimensions`.

## 8. Undo / Redo Pattern
- Capture deep copies of `Path` or config before mutation; push `PathCommand` / `ConfigCommand` to `UndoRedoManager`.
- When adding new mutating actions, ensure they emit appropriate sidebar signals so autosave & simulation rebuild stay in sync.

## 9. Implementation Conventions
- Favor small helper methods on `CanvasView` rather than spreading geometry math elsewhere.
- Wrap potentially fragile UI operations in `try/except` to keep editor responsive (pattern already prevalent—match it when editing those regions; but for new pure logic code prefer explicit error handling instead of broad except).
- Use meters & radians consistently in models; convert only at boundaries (display, JSON if needed).
- Keep scene mutations batched (e.g., rebuild functions) to minimize QGraphicsScene churn.

## 10. Adding Features Safely
- New element visual? Place item subclass in `ui/canvas/items/` and integrate creation in `_rebuild_items` with clear `kind` string.
- New per-element property? Add attribute to model classes, load/save in JSON serializer(s), expose in sidebar property editor, reflect in canvas visuals if needed.
- New simulation parameter? Extend `config.json`, thread through `ProjectManager` into `simulate_path`.

## 11. Common Pitfalls
- Forgetting y-axis inversion -> elements appear mirrored vertically.
- Directly scaling view instead of using logical field constants -> inconsistent zoom baseline.
- Modifying element positions without calling `_update_connecting_lines` -> stale lines.
- Bypassing debounced simulation rebuild -> performance hiccups.

## 12. Quick Reference Snippets
- Convert scene -> model: `mx,my = self._model_from_scene(item.pos().x(), item.pos().y())`.
- Constrain rotation drag: `_constrain_scene_coords_for_index(idx, x, y)`.
- Request sim rebuild after structural change: `self.request_simulation_rebuild()`.

## 13. Environment & Running
- Python + PySide6 desktop app. A local virtual environment (`venv/`) is expected; most developer commands assume it is activated.
- Observed pycache tags (`cpython-313`) indicate current development with Python 3.13. Use the latest stable 3.12/3.13; earlier 3.10+ likely fine (no version‑specific features beyond `__future__` imports).
- There is no `requirements.txt`; only runtime dependency right now is `PySide6`.
- Create & activate venv, install deps, run:
  ```bash
  python3 -m venv venv
  source venv/bin/activate  # macOS / Linux
  pip install --upgrade pip
  pip install PySide6
  python main.py
  ```
- (Optional) Generate a `requirements.txt` snapshot for reproducibility: `pip freeze > requirements.txt`.
- If adding new third‑party libs, update instructions here and (optionally) create `requirements.txt` to help future automation.
- No formal test suite yet; manual validation flow:
  1. Launch app
  2. Open `example_project/` via Project > Open Project…
  3. Interact with paths; confirm simulation trail appears and background field scales (no right-edge clipping).
- Packaging (not yet configured): If bundling later, prefer `pyinstaller` or `briefcase`; ensure assets/ copied and field scaling logic preserved.

## 14. Style Guidance for AI Changes
- Do not introduce global state: thread through `MainWindow` or existing managers.
- Maintain existing broad try/except wrappers in UI-heavy code, but annotate new logic with comments if exceptions intentionally suppressed.
- Prefer incremental patches; avoid wholesale rewrites of large files unless requested.

## 15. When Unsure
- Search for similar pattern (e.g., how waypoint radii handled) before adding new logic.
- If adding config-driven defaults, consult `ProjectManager.get_default_optional_value` for consistent behavior.

---
Provide changes aligned with these conventions; ask user only when an architectural decision isn't inferable from existing patterns.
