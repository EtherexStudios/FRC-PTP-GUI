from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from models.path_model import Path, PathElement, RotationTarget, TranslationTarget, Waypoint


@dataclass
class Pose:
    x_m: float
    y_m: float
    theta_rad: float


@dataclass
class ChassisSpeeds:
    vx_mps: float
    vy_mps: float
    omega_radps: float


@dataclass
class SimResult:
    poses_by_time: Dict[float, Tuple[float, float, float]]
    times_sorted: List[float]
    total_time_s: float


def wrap_angle_radians(theta: float) -> float:
    while theta > math.pi:
        theta -= 2.0 * math.pi
    while theta < -math.pi:
        theta += 2.0 * math.pi
    return theta


def shortest_angular_distance(target: float, current: float) -> float:
    delta = wrap_angle_radians(target - current)
    return delta


def dot(ax: float, ay: float, bx: float, by: float) -> float:
    return ax * bx + ay * by


def hypot2(x: float, y: float) -> float:
    return math.hypot(x, y)


def limit_acceleration(
    desired: ChassisSpeeds,
    last: ChassisSpeeds,
    dt: float,
    max_trans_accel_mps2: float,
    max_angular_accel_radps2: float,
) -> ChassisSpeeds:
    if dt <= 0.0:
        return last

    dvx = desired.vx_mps - last.vx_mps
    dvy = desired.vy_mps - last.vy_mps
    desired_acc = hypot2(dvx, dvy) / dt

    obtainable_acc = max(0.0, min(desired_acc, float(max_trans_accel_mps2)))
    theta = math.atan2(dvy, dvx) if (abs(dvx) + abs(dvy)) > 0.0 else 0.0

    desired_alpha = (desired.omega_radps - last.omega_radps) / dt
    obtainable_alpha = max(-float(max_angular_accel_radps2), min(desired_alpha, float(max_angular_accel_radps2)))

    return ChassisSpeeds(
        vx_mps=last.vx_mps + math.cos(theta) * obtainable_acc * dt,
        vy_mps=last.vy_mps + math.sin(theta) * obtainable_acc * dt,
        omega_radps=last.omega_radps + obtainable_alpha * dt,
    )


@dataclass
class _Segment:
    ax: float
    ay: float
    bx: float
    by: float
    length_m: float
    ux: float
    uy: float
    keyframes: List[Tuple[float, float]]  # list of (t_ratio, theta_target)


def _build_segments(path: Path) -> Tuple[List[_Segment], List[Tuple[float, float]]]:
    anchors: List[Tuple[float, float]] = []
    anchor_path_indices: List[int] = []

    for idx, elem in enumerate(path.path_elements):
        if isinstance(elem, TranslationTarget):
            anchors.append((float(elem.x_meters), float(elem.y_meters)))
            anchor_path_indices.append(idx)
        elif isinstance(elem, Waypoint):
            anchors.append((float(elem.translation_target.x_meters), float(elem.translation_target.y_meters)))
            anchor_path_indices.append(idx)

    segments: List[_Segment] = []
    if len(anchors) < 2:
        return segments, anchors

    # Map path index to anchor ordinal
    path_idx_to_anchor_ord: Dict[int, int] = {pi: i for i, pi in enumerate(anchor_path_indices)}

    # Initialize segments between consecutive anchors
    for i in range(len(anchors) - 1):
        ax, ay = anchors[i]
        bx, by = anchors[i + 1]
        dx = bx - ax
        dy = by - ay
        L = math.hypot(dx, dy)
        if L <= 1e-9:
            # Skip zero-length; caller will handle if all are zero
            segments.append(_Segment(ax, ay, bx, by, 0.0, 0.0, 0.0, []))
        else:
            segments.append(_Segment(ax, ay, bx, by, L, dx / L, dy / L, []))

    # Assign rotation keyframes to segments
    for idx, elem in enumerate(path.path_elements):
        if isinstance(elem, RotationTarget):
            # Find neighboring anchors in model order
            prev_anchor_ord: Optional[int] = None
            next_anchor_ord: Optional[int] = None
            # previous
            for j in range(idx - 1, -1, -1):
                e = path.path_elements[j]
                if isinstance(e, (TranslationTarget, Waypoint)):
                    prev_anchor_ord = path_idx_to_anchor_ord.get(j)
                    break
            # next
            for j in range(idx + 1, len(path.path_elements)):
                e = path.path_elements[j]
                if isinstance(e, (TranslationTarget, Waypoint)):
                    next_anchor_ord = path_idx_to_anchor_ord.get(j)
                    break
            if prev_anchor_ord is None or next_anchor_ord is None:
                continue
            if next_anchor_ord != prev_anchor_ord + 1:
                # Should not happen if the path is well-formed, but guard anyway
                continue
            t_ratio = float(getattr(elem, "t_ratio", 0.0))
            t_ratio = 0.0 if t_ratio < 0.0 else 1.0 if t_ratio > 1.0 else t_ratio
            theta = float(elem.rotation_radians)
            segments[prev_anchor_ord].keyframes.append((t_ratio, theta))
        elif isinstance(elem, Waypoint):
            rt = elem.rotation_target
            # Waypoint's rotation keyframe is associated with its neighbor segment
            # previous anchor is the waypoint itself, so the segment is from this to the next anchor
            # unless t_ratio belongs to a prior segment when there is a preceding anchor and t<0 (we clamp)
            this_anchor_ord = path_idx_to_anchor_ord.get(idx)
            if this_anchor_ord is None:
                continue
            # Waypoint rotation belongs to segment [this_anchor_ord .. this_anchor_ord+1]
            if this_anchor_ord < len(segments):
                t_ratio = float(getattr(rt, "t_ratio", 0.0))
                t_ratio = 0.0 if t_ratio < 0.0 else 1.0 if t_ratio > 1.0 else t_ratio
                theta = float(rt.rotation_radians)
                segments[this_anchor_ord].keyframes.append((t_ratio, theta))

    # Sort keyframes by t in each segment and deduplicate identical t by keeping the last
    for seg in segments:
        if not seg.keyframes:
            continue
        seg.keyframes.sort(key=lambda kv: kv[0])
        dedup: List[Tuple[float, float]] = []
        last_t: Optional[float] = None
        for t, th in seg.keyframes:
            if last_t is not None and abs(t - last_t) < 1e-9:
                dedup[-1] = (t, th)  # replace with latest
            else:
                dedup.append((t, th))
                last_t = t
        seg.keyframes = dedup

    return segments, anchors


def _default_heading(ax: float, ay: float, bx: float, by: float) -> float:
    return math.atan2(by - ay, bx - ax)


def _desired_heading_for_progress(
    seg: _Segment,
    progress_t: float,
    start_heading: float,
) -> Tuple[float, float]:
    # Returns (desired_theta, dtheta_dt_over_distance)
    t = 0.0 if progress_t < 0.0 else 1.0 if progress_t > 1.0 else progress_t

    # If no keyframes, heading is constant at start_heading
    if not seg.keyframes:
        return start_heading, 0.0

    # Ensure there is a start keyframe at t=0; if not, virtual start at current start_heading
    frames: List[Tuple[float, float]] = []
    if seg.keyframes[0][0] > 0.0 + 1e-9:
        frames.append((0.0, start_heading))
    frames.extend(seg.keyframes)

    # If t is before first, interpolate from virtual start to first
    for i in range(len(frames) - 1):
        t0, th0 = frames[i]
        t1, th1 = frames[i + 1]
        if t <= t0 + 1e-12:
            # before or at this keyframe; when at/before t0, desired is th0
            delta = shortest_angular_distance(th1, th0)
            dtheta_ds = (delta / max((t1 - t0) * max(seg.length_m, 1e-9), 1e-9))
            return th0, dtheta_ds
        if t0 < t <= t1 + 1e-12:
            alpha = (t - t0) / max((t1 - t0), 1e-9)
            delta = shortest_angular_distance(th1, th0)
            desired_theta = wrap_angle_radians(th0 + delta * alpha)
            dtheta_ds = (delta / max((t1 - t0) * max(seg.length_m, 1e-9), 1e-9))
            return desired_theta, dtheta_ds

    # After last keyframe
    t_last, th_last = frames[-1]
    return th_last, 0.0


def _resolve_constraint(value: Optional[float], fallback: Optional[float], default: float) -> float:
    try:
        if value is not None and float(value) > 0.0:
            return float(value)
    except Exception:
        pass
    try:
        if fallback is not None and float(fallback) > 0.0:
            return float(fallback)
    except Exception:
        pass
    return float(default)


def simulate_path(
    path: Path,
    config: Optional[Dict] = None,
    dt_s: float = 0.02,
    rot_kp: float = 1.0,
    rot_kd: float = 0.8,
    heading_error_threshold_rad: float = 0.2,
    heading_error_min_scalar: float = 0.3,
) -> SimResult:
    cfg = config or {}
    segments, anchors = _build_segments(path)

    poses_by_time: Dict[float, Tuple[float, float, float]] = {}
    times_sorted: List[float] = []

    if len(anchors) < 2 or len(segments) == 0:
        # Single point or empty path – just output the anchor pose at t=0
        if anchors:
            x0, y0 = anchors[0]
            poses_by_time[0.0] = (x0, y0, 0.0)
            times_sorted = [0.0]
        return SimResult(poses_by_time=poses_by_time, times_sorted=times_sorted, total_time_s=0.0)

    # Constraints from Path first, then config defaults, then hardcoded fallback
    c = getattr(path, "constraints", None)
    initial_v = _resolve_constraint(getattr(c, "initial_velocity_meters_per_sec", None), cfg.get("initial_velocity_meters_per_sec"), 0.0)
    final_v = _resolve_constraint(getattr(c, "final_velocity_meters_per_sec", None), cfg.get("final_velocity_meters_per_sec"), 0.0)
    max_v = _resolve_constraint(getattr(c, "max_velocity_meters_per_sec", None), cfg.get("max_velocity_meters_per_sec"), 3.0)
    max_a = _resolve_constraint(getattr(c, "max_acceleration_meters_per_sec2", None), cfg.get("max_acceleration_meters_per_sec2"), 2.5)

    max_omega_deg = _resolve_constraint(getattr(c, "max_velocity_deg_per_sec", None), cfg.get("max_velocity_deg_per_sec"), 180.0)
    max_alpha_deg = _resolve_constraint(getattr(c, "max_acceleration_deg_per_sec2", None), cfg.get("max_acceleration_deg_per_sec2"), 360.0)
    max_omega = math.radians(max_omega_deg)
    max_alpha = math.radians(max_alpha_deg)

    # Precompute cumulative segment lengths
    total_path_len = 0.0
    cumulative_lengths: List[float] = [0.0]
    for seg in segments:
        L = max(seg.length_m, 0.0)
        total_path_len += L
        cumulative_lengths.append(total_path_len)

    # Starting state
    first_seg = segments[0]
    start_heading = _default_heading(first_seg.ax, first_seg.ay, first_seg.bx, first_seg.by)
    # If there is a keyframe at t=0 in first segment, use that
    if first_seg.keyframes:
        for t, th in sorted(first_seg.keyframes, key=lambda kv: kv[0]):
            if t <= 1e-6:
                start_heading = th
                break

    x = first_seg.ax
    y = first_seg.ay
    theta = start_heading

    # Initialize speeds along the first segment direction
    ux, uy = first_seg.ux, first_seg.uy
    speeds = ChassisSpeeds(vx_mps=ux * initial_v, vy_mps=uy * initial_v, omega_radps=0.0)

    t_s = 0.0
    seg_idx = 0
    s_in_seg = 0.0

    # Helper to compute remaining length from current segment and position
    def remaining_distance_from(seg_index: int, s_local: float) -> float:
        if seg_index >= len(segments):
            return 0.0
        rem = max(segments[seg_index].length_m - s_local, 0.0)
        for k in range(seg_index + 1, len(segments)):
            rem += max(segments[k].length_m, 0.0)
        return rem

    # PD rotation error previous
    prev_rot_error = 0.0

    # Guard max time to avoid runaway
    guard_time = max(10.0, (total_path_len / max(0.5, max_v)) * 5.0)

    # Simulation loop
    while t_s <= guard_time:
        # Current segment and unit vector
        seg = segments[seg_idx]
        ux, uy = (seg.ux, seg.uy) if seg.length_m > 1e-9 else (1.0, 0.0)

        # Segment progress [0,1]
        progress_t = 0.0 if seg.length_m <= 1e-9 else (s_in_seg / seg.length_m)

        # Determine start heading for this segment if just entered
        if abs(s_in_seg) < 1e-9 and t_s > 0.0:
            # carry previous desired heading at t=1 of previous segment, or default
            prev_seg = segments[seg_idx - 1] if seg_idx > 0 else None
            if prev_seg is not None and prev_seg.keyframes:
                start_heading = prev_seg.keyframes[-1][1]
            else:
                start_heading = _default_heading(seg.ax, seg.ay, seg.bx, seg.by)

        # Desired heading and dtheta/ds
        desired_theta, dtheta_ds = _desired_heading_for_progress(seg, progress_t, start_heading)

        # Rotational feedforward and PD
        v_proj = dot(speeds.vx_mps, speeds.vy_mps, ux, uy)
        omega_ff = dtheta_ds * v_proj

        rot_error = shortest_angular_distance(desired_theta, theta)
        rot_error_rate = (rot_error - prev_rot_error) / max(dt_s, 1e-9)
        omega_pid = rot_kp * rot_error + rot_kd * rot_error_rate
        prev_rot_error = rot_error

        omega_des = omega_ff + omega_pid
        # Clamp desired omega to max velocity (pre-accel-limit)
        if abs(omega_des) > max_omega:
            omega_des = math.copysign(max_omega, omega_des)

        # Translational desired speed using simple trapezoid along remaining distance
        v_curr = hypot2(speeds.vx_mps, speeds.vy_mps)
        v_allow_decel = math.sqrt(max(final_v * final_v, 0.0) + 2.0 * max(0.0, max_a) * remaining_distance_from(seg_idx, s_in_seg))
        v_next_by_accel = v_curr + max_a * dt_s
        v_des_scalar = min(max_v, v_allow_decel, v_next_by_accel)

        # Heading error slowdown when error large
        err = abs(rot_error)
        if err > heading_error_threshold_rad:
            # linearly scale from threshold..pi
            if err >= math.pi:
                scale = heading_error_min_scalar
            else:
                scale = 1.0 - (err - heading_error_threshold_rad) / (math.pi - heading_error_threshold_rad)
                scale = max(heading_error_min_scalar, min(1.0, scale))
            v_des_scalar *= scale

        vx_des = v_des_scalar * ux
        vy_des = v_des_scalar * uy

        # Apply acceleration limits (both translational and angular)
        limited = limit_acceleration(
            desired=ChassisSpeeds(vx_des, vy_des, omega_des),
            last=speeds,
            dt=dt_s,
            max_trans_accel_mps2=max_a,
            max_angular_accel_radps2=max_alpha,
        )

        # Clamp to max velocity after limiting
        v_mag = hypot2(limited.vx_mps, limited.vy_mps)
        if v_mag > max_v > 0.0:
            scale = max_v / v_mag
            limited = ChassisSpeeds(limited.vx_mps * scale, limited.vy_mps * scale, limited.omega_radps)
        if abs(limited.omega_radps) > max_omega > 0.0:
            limited = ChassisSpeeds(limited.vx_mps, limited.vy_mps, math.copysign(max_omega, limited.omega_radps))

        # Integrate
        x += limited.vx_mps * dt_s
        y += limited.vy_mps * dt_s
        theta = wrap_angle_radians(theta + limited.omega_radps * dt_s)

        # Advance arc length along segment by projected component
        ds = dot(limited.vx_mps, limited.vy_mps, ux, uy) * dt_s
        s_in_seg += max(0.0, ds)

        # Segment transition
        while seg_idx < len(segments) and s_in_seg >= max(seg.length_m, 0.0) - 1e-9:
            s_in_seg -= max(seg.length_m, 0.0)
            seg_idx += 1
            if seg_idx >= len(segments):
                s_in_seg = 0.0
                break
            seg = segments[seg_idx]
            ux, uy = (seg.ux, seg.uy) if seg.length_m > 1e-9 else (1.0, 0.0)

        # Record pose at this timestamp (rounded to milliseconds)
        t_key = round(t_s, 3)
        poses_by_time[t_key] = (float(x), float(y), float(theta))
        times_sorted.append(t_key)

        # Termination: reached final anchor and nearly stopped according to final velocity
        at_end = seg_idx >= len(segments)
        if at_end:
            if v_mag <= max(0.05, final_v + 0.05) and abs(limited.omega_radps) <= math.radians(5.0):
                break

        # Advance time
        t_s += dt_s
        speeds = limited

    # Ensure final sample at last time
    last_time = round(t_s, 3)
    if last_time not in poses_by_time and times_sorted:
        poses_by_time[last_time] = poses_by_time[times_sorted[-1]]
        times_sorted.append(last_time)

    # De-duplicate sorted times list, keeping order
    seen = set()
    uniq_times: List[float] = []
    for tk in times_sorted:
        if tk in seen:
            continue
        seen.add(tk)
        uniq_times.append(tk)

    total_time_s = uniq_times[-1] if uniq_times else 0.0
    return SimResult(poses_by_time=poses_by_time, times_sorted=uniq_times, total_time_s=total_time_s)