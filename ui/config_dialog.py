from __future__ import annotations

from typing import Callable, Dict, Optional

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QDoubleSpinBox,
)
from PySide6.QtCore import Qt


class ConfigDialog(QDialog):
    """Dialog to edit config.json values.

    Shows robot dimensions and optional default values.
    """

    def __init__(self, parent=None, existing_config: Optional[Dict[str, float]] = None, on_change: Optional[Callable[[str, float], None]] = None):
        super().__init__(parent)
        self.setWindowTitle("Edit Config")
        self.setModal(True)
        self._spins: Dict[str, QDoubleSpinBox] = {}
        cfg = existing_config or {}
        self._on_change = on_change

        root = QVBoxLayout(self)
        form = QFormLayout()
        root.addLayout(form)

        def add_spin(key: str, label: str, default: float, rng: tuple[float, float], step: float = 0.01):
            spin = QDoubleSpinBox(self)
            spin.setDecimals(4)
            spin.setSingleStep(step)
            spin.setRange(rng[0], rng[1])
            spin.setValue(float(cfg.get(key, default)))
            form.addRow(QLabel(label), spin)
            self._spins[key] = spin
            # Live autosave via callback
            spin.valueChanged.connect(lambda _v, k=key, w=spin: self._emit_change(k, float(w.value())))

        # Robot dimensions
        add_spin("robot_length_meters", "Robot Length (m)", cfg.get("robot_length_meters", 0.60) or 0.60, (0.05, 5.0), 0.01)
        add_spin("robot_width_meters", "Robot Width (m)", cfg.get("robot_width_meters", 0.60) or 0.60, (0.05, 5.0), 0.01)

        # Optional defaults
        add_spin("final_velocity_meters_per_sec", "Default Final Velocity (m/s)", float(cfg.get("final_velocity_meters_per_sec", 0.0) or 0.0), (0.0, 99999.0), 0.1)
        add_spin("max_velocity_meters_per_sec", "Default Max Velocity (m/s)", float(cfg.get("max_velocity_meters_per_sec", 0.0) or 0.0), (0.0, 99999.0), 0.1)
        add_spin("max_acceleration_meters_per_sec2", "Default Max Accel (m/s²)", float(cfg.get("max_acceleration_meters_per_sec2", 0.0) or 0.0), (0.0, 99999.0), 0.1)
        add_spin("intermediate_handoff_radius_meters", "Default Handoff Radius (m)", float(cfg.get("intermediate_handoff_radius_meters", 0.0) or 0.0), (0.0, 99999.0), 0.05)
        add_spin("max_velocity_deg_per_sec", "Default Max Rot Vel (deg/s)", float(cfg.get("max_velocity_deg_per_sec", 0.0) or 0.0), (0.0, 99999.0), 1.0)
        add_spin("max_acceleration_deg_per_sec2", "Default Max Rot Accel (deg/s²)", float(cfg.get("max_acceleration_deg_per_sec2", 0.0) or 0.0), (0.0, 99999.0), 1.0)
        add_spin("end_translation_tolerance_meters", "End Translation Tolerance (m)", float(cfg.get("end_translation_tolerance_meters", 0.05) or 0.05), (0.0, 1.0), 0.01)
        add_spin("end_rotation_tolerance_deg", "End Rotation Tolerance (deg)", float(cfg.get("end_rotation_tolerance_deg", 2.0) or 2.0), (0.0, 180.0), 0.1)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, orientation=Qt.Horizontal, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def get_values(self) -> Dict[str, float]:
        result: Dict[str, float] = {}
        for k, spin in self._spins.items():
            result[k] = float(spin.value())
        return result

    def _emit_change(self, key: str, value: float):
        if self._on_change is not None:
            try:
                self._on_change(key, float(value))
            except Exception:
                pass

    def sync_from_config(self, cfg: Dict[str, float]) -> None:
        """Update spinner values from the provided config without emitting signals."""
        for key, spin in self._spins.items():
            try:
                spin.blockSignals(True)
                if key in cfg and cfg[key] is not None:
                    spin.setValue(float(cfg[key]))
            except Exception:
                pass
            finally:
                spin.blockSignals(False)


