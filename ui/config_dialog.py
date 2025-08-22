from __future__ import annotations

from typing import Callable, Dict, Optional

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QGroupBox,
    QWidget,
    QHBoxLayout,
    QSizePolicy,
)
from PySide6.QtCore import Qt
from ui.sidebar.widgets.no_wheel_spinbox import NoWheelDoubleSpinBox


class ConfigDialog(QDialog):
    """Dialog to edit config.json values.

    Shows robot dimensions and optional default values.
    """

    def __init__(self, parent=None, existing_config: Optional[Dict[str, float]] = None, on_change: Optional[Callable[[str, float], None]] = None):
        super().__init__(parent)
        self.setWindowTitle("Edit Config")
        self.setModal(True)
        self._spins: Dict[str, NoWheelDoubleSpinBox] = {}
        cfg = existing_config or {}
        self._on_change = on_change

        # Apply dark dialog background to match the app
        try:
            self.setObjectName("configDialog")
            self.setStyleSheet(
                """
                QDialog#configDialog { background-color: #151515; }
                QLabel { color: #f0f0f0; }
                """
            )
        except Exception:
            pass

        root = QVBoxLayout(self)
        try:
            root.setContentsMargins(8, 8, 8, 8)
            root.setSpacing(8)
        except Exception:
            pass

        # Title bar styled like other sections in the app
        self.title_bar = QWidget()
        self.title_bar.setObjectName("configTitleBar")
        try:
            self.title_bar.setStyleSheet(
                """
                QWidget#configTitleBar {
                    background-color: #2a2a2a;
                    border: 1px solid #5a5a5a;
                    border-radius: 6px;
                }
                """
            )
        except Exception:
            pass
        title_layout = QHBoxLayout(self.title_bar)
        try:
            title_layout.setContentsMargins(10, 0, 10, 0)
            title_layout.setSpacing(0)
        except Exception:
            pass
        title_label = QLabel("Configuration")
        try:
            title_label.setStyleSheet(
                """
                font-size: 14px;
                font-weight: bold;
                color: #eeeeee;
                background: transparent;
                border: none;
                padding: 6px 0;
                """
            )
        except Exception:
            pass
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        root.addWidget(self.title_bar)

        # Group box container matching sidebar look
        self.form_container = QGroupBox()
        try:
            self.form_container.setStyleSheet(
                """
                QGroupBox { background-color: #202020; border: 1px solid #444444; border-radius: 6px; }
                QLabel { color: #f0f0f0; }
                QWidget[constraintRow='true'] { background: #2d2d2d; border: 1px solid #454545; border-radius: 6px; margin: 4px 0; }
                """
            )
        except Exception:
            pass
        group_layout = QVBoxLayout(self.form_container)
        try:
            group_layout.setContentsMargins(8, 6, 8, 6)
            group_layout.setSpacing(4)
        except Exception:
            pass
        root.addWidget(self.form_container)

        def add_spin(key: str, label: str, default: float, rng: tuple[float, float], step: float = 0.01):
            # Row wrapper styled like constraint/property rows elsewhere
            row = QWidget()
            row.setProperty('constraintRow', 'true')
            row_layout = QHBoxLayout(row)
            try:
                row_layout.setContentsMargins(8, 6, 8, 6)
                row_layout.setSpacing(8)
            except Exception:
                pass

            lbl = QLabel(label)
            try:
                lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                lbl.setMinimumWidth(200)
            except Exception:
                pass

            spin = NoWheelDoubleSpinBox(self)
            spin.setDecimals(4)
            spin.setSingleStep(step)
            spin.setRange(rng[0], rng[1])
            spin.setValue(float(cfg.get(key, default)))
            try:
                spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                spin.setMinimumWidth(120)
            except Exception:
                pass

            row_layout.addWidget(lbl)
            row_layout.addStretch()
            row_layout.addWidget(spin)
            group_layout.addWidget(row)

            self._spins[key] = spin
            # Live autosave via callback
            spin.valueChanged.connect(lambda _v, k=key, w=spin: self._emit_change(k, float(w.value())))

        # Robot dimensions
        add_spin("robot_length_meters", "Robot Length (m)", cfg.get("robot_length_meters", 0.60) or 0.60, (0.05, 5.0), 0.01)
        add_spin("robot_width_meters", "Robot Width (m)", cfg.get("robot_width_meters", 0.60) or 0.60, (0.05, 5.0), 0.01)

        # Optional defaults
        add_spin("max_velocity_meters_per_sec", "Default Max Velocity (m/s)", float(cfg.get("max_velocity_meters_per_sec", 0.0) or 0.0), (0.0, 99999.0), 0.1)
        add_spin("max_acceleration_meters_per_sec2", "Default Max Accel (m/s²)", float(cfg.get("max_acceleration_meters_per_sec2", 0.0) or 0.0), (0.0, 99999.0), 0.1)
        add_spin("intermediate_handoff_radius_meters", "Default Handoff Radius (m)", float(cfg.get("intermediate_handoff_radius_meters", 0.0) or 0.0), (0.0, 99999.0), 0.05)
        add_spin("max_velocity_deg_per_sec", "Default Max Rot Vel (deg/s)", float(cfg.get("max_velocity_deg_per_sec", 0.0) or 0.0), (0.0, 99999.0), 1.0)
        add_spin("max_acceleration_deg_per_sec2", "Default Max Rot Accel (deg/s²)", float(cfg.get("max_acceleration_deg_per_sec2", 0.0) or 0.0), (0.0, 99999.0), 1.0)
        add_spin("end_translation_tolerance_meters", "End Translation Tolerance (m)", float(cfg.get("end_translation_tolerance_meters", 0.05) or 0.05), (0.0, 1.0), 0.01)
        add_spin("end_rotation_tolerance_deg", "End Rotation Tolerance (deg)", float(cfg.get("end_rotation_tolerance_deg", 2.0) or 2.0), (0.0, 180.0), 0.1)

        # Buttons styled to fit dark UI
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, orientation=Qt.Horizontal, parent=self)
        try:
            buttons.setStyleSheet(
                """
                QDialogButtonBox QPushButton {
                    background-color: #303030;
                    color: #eeeeee;
                    border: 1px solid #5a5a5a;
                    border-radius: 4px;
                    padding: 4px 10px;
                }
                QDialogButtonBox QPushButton:hover { background: #575757; }
                QDialogButtonBox QPushButton:pressed { background: #6a6a6a; }
                """
            )
        except Exception:
            pass
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


