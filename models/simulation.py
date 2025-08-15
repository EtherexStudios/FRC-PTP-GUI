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
    trail_points: List[Tuple[float, float]]  # List of (x, y) positions for the trail


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
class _RotationKeyframe:
    t_ratio: float
    theta_target: float
    profiled_rotation: bool = True

@dataclass
class _Segment:
    ax: float
    ay: float
    bx: float
    by: float
    length_m: float
    ux: float
    uy: float
    keyframes: List[_RotationKeyframe]  # list of rotation keyframes


@dataclass
class _GlobalRotationKeyframe:
    s_m: float
    theta_target: float
    profiled_rotation: bool = True


def _build_segments(path: Path) -> Tuple[List[_Segment], List[Tuple[float, float]], List[int]]:
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
        return segments, anchors, anchor_path_indices

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
            segments.append(_Segment(ax, ay, bx, by, 0.0, 1.0, 0.0, []))
        else:
            segments.append(_Segment(ax, ay, bx, by, L, dx / L, dy / L, []))

    # Assign rotation keyframes to segments
    for idx, elem in enumerate(path.path_elements):
        if isinstance(elem, RotationTarget):
            prev_anchor_ord: Optional[int] = None
            next_anchor_ord: Optional[int] = None
            for j in range(idx - 1, -1, -1):
                e = path.path_elements[j]
                if isinstance(e, (TranslationTarget, Waypoint)):
                    prev_anchor_ord = path_idx_to_anchor_ord.get(j)
                    break
            for j in range(idx + 1, len(path.path_elements)):
                e = path.path_elements[j]
                if isinstance(e, (TranslationTarget, Waypoint)):
                    next_anchor_ord = path_idx_to_anchor_ord.get(j)
                    break
            if prev_anchor_ord is None or next_anchor_ord is None:
                continue
            if next_anchor_ord != prev_anchor_ord + 1:
                continue
            t_ratio = float(getattr(elem, "t_ratio", 0.0))
            t_ratio = 0.0 if t_ratio < 0.0 else 1.0 if t_ratio > 1.0 else t_ratio
            theta = float(elem.rotation_radians)
            profiled = getattr(elem, "profiled_rotation", True)
            # DEBUG: Print rotation target properties
            print(f"DEBUG: RotationTarget at t_ratio={t_ratio:.2f}, theta={math.degrees(theta):.1f}°, profiled={profiled}")
            segments[prev_anchor_ord].keyframes.append(_RotationKeyframe(t_ratio, theta, profiled))
        elif isinstance(elem, Waypoint):
            rt = elem.rotation_target
            this_anchor_ord = path_idx_to_anchor_ord.get(idx)
            if this_anchor_ord is None:
                continue
            
            # For waypoints, the rotation should happen at the waypoint location
            # This means we need to add it to the segment that ENDS at this waypoint
            # (i.e., the previous segment with t_ratio = 1.0)
            # OR to the segment that STARTS at this waypoint with t_ratio = 0.0
            
            # Strategy: Add to the segment that starts at this waypoint with t_ratio = 0.0
            # This ensures the robot has the correct heading when leaving the waypoint
            if this_anchor_ord < len(segments):
                theta = float(rt.rotation_radians)
                profiled = getattr(rt, "profiled_rotation", True)
                # DEBUG: Print waypoint rotation properties
                print(f"DEBUG: Waypoint rotation at start: theta={math.degrees(theta):.1f}°, profiled={profiled}")
                segments[this_anchor_ord].keyframes.append(_RotationKeyframe(0.0, theta, profiled))
            
            # Also add to the previous segment with t_ratio = 1.0 if it exists
            # This ensures the robot rotates to the correct heading when arriving at the waypoint
            if this_anchor_ord > 0:
                theta = float(rt.rotation_radians)
                profiled = getattr(rt, "profiled_rotation", True)
                # DEBUG: Print waypoint rotation properties
                print(f"DEBUG: Waypoint rotation at end: theta={math.degrees(theta):.1f}°, profiled={profiled}")
                segments[this_anchor_ord - 1].keyframes.append(_RotationKeyframe(1.0, theta, profiled))

    for seg in segments:
        if not seg.keyframes:
            continue
        seg.keyframes.sort(key=lambda kf: kf.t_ratio)
        dedup: List[_RotationKeyframe] = []
        last_t: Optional[float] = None
        for kf in seg.keyframes:
            if last_t is not None and abs(kf.t_ratio - last_t) < 1e-9:
                dedup[-1] = kf  # Replace with latest
            else:
                dedup.append(kf)
                last_t = kf.t_ratio
        seg.keyframes = dedup

    return segments, anchors, anchor_path_indices


def _default_heading(ax: float, ay: float, bx: float, by: float) -> float:
    return math.atan2(by - ay, bx - ax)


def _build_global_rotation_keyframes(
    path: Path,
    anchor_path_indices: List[int],
    cumulative_lengths: List[float],
) -> List[_GlobalRotationKeyframe]:
    """Build a global rotation keyframe list along absolute path distance s (meters).

    RotationTarget elements between any two anchors (not necessarily adjacent)
    are mapped to a distance s by linearly interpolating between the cumulative
    distances of the surrounding anchors using the element's t_ratio.

    Waypoint rotations are mapped to the absolute distance at that waypoint.
    """
    path_idx_to_anchor_ord: Dict[int, int] = {pi: i for i, pi in enumerate(anchor_path_indices)}

    global_frames: List[_GlobalRotationKeyframe] = []

    for idx, elem in enumerate(path.path_elements):
        if isinstance(elem, RotationTarget):
            prev_anchor_ord: Optional[int] = None
            next_anchor_ord: Optional[int] = None
            for j in range(idx - 1, -1, -1):
                e = path.path_elements[j]
                if isinstance(e, (TranslationTarget, Waypoint)):
                    prev_anchor_ord = path_idx_to_anchor_ord.get(j)
                    break
            for j in range(idx + 1, len(path.path_elements)):
                e = path.path_elements[j]
                if isinstance(e, (TranslationTarget, Waypoint)):
                    next_anchor_ord = path_idx_to_anchor_ord.get(j)
                    break
            # Require valid surrounding anchors, but they do NOT need to be adjacent
            if prev_anchor_ord is None or next_anchor_ord is None:
                continue
            s0 = cumulative_lengths[prev_anchor_ord]
            s1 = cumulative_lengths[next_anchor_ord]
            seg_span = max(s1 - s0, 1e-9)
            t_ratio = float(getattr(elem, "t_ratio", 0.0))
            t_ratio = 0.0 if t_ratio < 0.0 else 1.0 if t_ratio > 1.0 else t_ratio
            theta = float(elem.rotation_radians)
            profiled = getattr(elem, "profiled_rotation", True)
            s_at = s0 + t_ratio * seg_span
            print(
                f"DEBUG: Global RotationTarget at s={s_at:.3f} m (prev={prev_anchor_ord}, next={next_anchor_ord}, t={t_ratio:.2f}), "
                f"theta={math.degrees(theta):.1f}°, profiled={profiled}"
            )
            global_frames.append(_GlobalRotationKeyframe(s_at, theta, profiled))
        elif isinstance(elem, Waypoint):
            this_anchor_ord = path_idx_to_anchor_ord.get(idx)
            if this_anchor_ord is None:
                continue
            rt = elem.rotation_target
            theta = float(rt.rotation_radians)
            profiled = getattr(rt, "profiled_rotation", True)
            s_at = cumulative_lengths[this_anchor_ord]
            print(
                f"DEBUG: Global Waypoint rotation at s={s_at:.3f} m (anchor={this_anchor_ord}), "
                f"theta={math.degrees(theta):.1f}°, profiled={profiled}"
            )
            global_frames.append(_GlobalRotationKeyframe(s_at, theta, profiled))

    if not global_frames:
        return []

    # Sort and de-duplicate by s; keep the last entry for identical s positions
    global_frames.sort(key=lambda kf: kf.s_m)
    dedup: List[_GlobalRotationKeyframe] = []
    last_s: Optional[float] = None
    for kf in global_frames:
        if last_s is not None and abs(kf.s_m - last_s) < 1e-9:
            dedup[-1] = kf
        else:
            dedup.append(kf)
            last_s = kf.s_m
    return dedup


def _desired_heading_for_global_s(
    global_frames: List[_GlobalRotationKeyframe],
    s_m: float,
    start_heading: float,
) -> Tuple[float, float, bool]:
    """Compute desired heading and dtheta/ds at absolute path distance s_m.

    Returns (desired_theta, dtheta_ds, profiled_rotation_for_interval).
    """
    if not global_frames:
        return start_heading, 0.0, True

    frames: List[Tuple[float, float, bool]] = []
    if global_frames[0].s_m > 0.0 + 1e-9:
        frames.append((0.0, start_heading, True))
    for kf in global_frames:
        frames.append((kf.s_m, kf.theta_target, kf.profiled_rotation))

    # Iterate across brackets
    for i in range(len(frames) - 1):
        s0, th0, profiled0 = frames[i]
        s1, th1, profiled1 = frames[i + 1]
        if s_m <= s0 + 1e-12:
            # If we're exactly at this keyframe, hold its heading.
            if abs(s_m - s0) <= 1e-12:
                delta = shortest_angular_distance(th1, th0)
                dtheta_ds = (delta / max((s1 - s0), 1e-9))
                return th0, dtheta_ds, profiled1
            # Only snap ahead to the next (non-profiled) keyframe if we're strictly
            # before the current keyframe. This avoids snapping at s == s0.
            if s_m < s0 - 1e-12 and not profiled1:
                return th1, 0.0, profiled1
            delta = shortest_angular_distance(th1, th0)
            dtheta_ds = (delta / max((s1 - s0), 1e-9))
            return th0, dtheta_ds, profiled1
        if s0 < s_m <= s1 + 1e-12:
            if not profiled1:
                return th1, 0.0, profiled1
            alpha = (s_m - s0) / max((s1 - s0), 1e-9)
            delta = shortest_angular_distance(th1, th0)
            desired_theta = wrap_angle_radians(th0 + delta * alpha)
            dtheta_ds = (delta / max((s1 - s0), 1e-9))
            return desired_theta, dtheta_ds, profiled1

    # After the last frame, hold
    _, th_last, profiled_last = frames[-1]
    if not profiled_last:
        return th_last, 0.0, profiled_last
    return th_last, 0.0, profiled_last


def _desired_heading_for_progress(
    seg: _Segment,
    progress_t: float,
    start_heading: float,
) -> Tuple[float, float, bool]:
    t = 0.0 if progress_t < 0.0 else 1.0 if progress_t > 1.0 else progress_t

    if not seg.keyframes:
        return start_heading, 0.0, True

    frames: List[Tuple[float, float, bool]] = []
    if seg.keyframes[0].t_ratio > 0.0 + 1e-9:
        frames.append((0.0, start_heading, True))
    for kf in seg.keyframes:
        frames.append((kf.t_ratio, kf.theta_target, kf.profiled_rotation))

    for i in range(len(frames) - 1):
        t0, th0, profiled0 = frames[i]
        t1, th1, profiled1 = frames[i + 1]
        if t <= t0 + 1e-12:
            # If we're exactly at this keyframe, hold its heading.
            if abs(t - t0) <= 1e-12:
                delta = shortest_angular_distance(th1, th0)
                dtheta_ds = (delta / max((t1 - t0) * max(seg.length_m, 1e-9), 1e-9))
                return th0, dtheta_ds, profiled1  # Interpolate away from th0
            # Only snap ahead if we're strictly before the current keyframe and the
            # upcoming keyframe is non-profiled.
            if t < t0 - 1e-12 and not profiled1:
                return th1, 0.0, profiled1
            delta = shortest_angular_distance(th1, th0)
            dtheta_ds = (delta / max((t1 - t0) * max(seg.length_m, 1e-9), 1e-9))
            return th0, dtheta_ds, profiled1  # Profiled: interpolate from th0
        if t0 < t <= t1 + 1e-12:
            # If this segment of heading is non-profiled, target the end keyframe directly
            if not profiled1:
                return th1, 0.0, profiled1
            alpha = (t - t0) / max((t1 - t0), 1e-9)
            delta = shortest_angular_distance(th1, th0)
            desired_theta = wrap_angle_radians(th0 + delta * alpha)
            dtheta_ds = (delta / max((t1 - t0) * max(seg.length_m, 1e-9), 1e-9))
            return desired_theta, dtheta_ds, profiled1  # Profiled: interpolate toward th1

    t_last, th_last, profiled_last = frames[-1]
    # If the final keyframe is non-profiled, just hold that target
    if not profiled_last:
        return th_last, 0.0, profiled_last
    return th_last, 0.0, profiled_last


def _trapezoidal_rotation_profile(
    current_theta: float,
    target_theta: float,
    current_omega: float,
    max_omega: float,
    max_alpha: float,
    dt: float
) -> float:
    """
    Time-optimal, discrete-time trapezoidal profile without heuristics.
    Chooses an angular velocity for this timestep that respects:
    - acceleration limit (|Δω| ≤ max_alpha * dt)
    - velocity limit (|ω| ≤ max_omega)
    - no-overshoot within this step plus future optimal deceleration:
      v*dt + v^2/(2*max_alpha) ≤ |angular_error|
    """
    angular_error = shortest_angular_distance(target_theta, current_theta)

    if dt <= 0.0 or max_alpha <= 0.0 or max_omega <= 0.0:
        return 0.0

    error_mag = abs(angular_error)
    if error_mag == 0.0:
        # No remaining error: decelerate toward zero as fast as possible
        if abs(current_omega) <= max_alpha * dt:
            return 0.0
        return current_omega - math.copysign(max_alpha * dt, current_omega)

    direction = math.copysign(1.0, angular_error)
    v_curr_aligned = direction * current_omega  # velocity along desired direction (can be negative)

    # Upper bound on velocity this step to avoid overshoot in discrete time:
    # Solve v*dt + v^2/(2*a) <= error_mag for v >= 0
    a_dt = max_alpha * dt
    v_step_bound = max(0.0, -a_dt + math.sqrt(a_dt * a_dt + 2.0 * max_alpha * error_mag))

    # Also respect classical distance and speed limits
    v_distance_bound = math.sqrt(2.0 * max_alpha * error_mag)
    v_allow = min(v_step_bound, v_distance_bound, max_omega)

    # Acceleration-limited change from current velocity toward the largest allowed value
    v_reachable_min = v_curr_aligned - a_dt
    v_reachable_max = v_curr_aligned + a_dt

    # Choose the maximum reachable velocity that does not exceed v_allow
    if v_reachable_max <= v_allow:
        v_next_aligned = v_reachable_max
    elif v_reachable_min <= v_allow <= v_reachable_max:
        v_next_aligned = v_allow
    else:
        # Can't reach within bound this step; decelerate as much as possible
        v_next_aligned = v_reachable_min

    # Convert back to signed angular velocity and enforce overall speed limit
    desired_omega = direction * v_next_aligned
    if abs(desired_omega) > max_omega:
        desired_omega = math.copysign(max_omega, desired_omega)

    return desired_omega


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


def _get_handoff_radius_for_segment(path: Path, seg_index: int, anchor_path_indices: List[int], default_radius: float) -> float:
    """Get the handoff radius for a specific segment. Uses the radius from the target element of that segment."""
    if seg_index < 0 or seg_index >= len(anchor_path_indices) - 1:
        return default_radius
    
    # The target element for this segment is at anchor_path_indices[seg_index + 1]
    target_element_index = anchor_path_indices[seg_index + 1]
    
    if target_element_index >= len(path.path_elements):
        return default_radius
    
    target_element = path.path_elements[target_element_index]
    
    # Get handoff radius from the target element
    radius = None
    if isinstance(target_element, TranslationTarget):
        radius = getattr(target_element, 'intermediate_handoff_radius_meters', None)
    elif isinstance(target_element, Waypoint):
        radius = getattr(target_element.translation_target, 'intermediate_handoff_radius_meters', None)
    
    # Use element radius if set and positive, otherwise use default
    if radius is not None and radius > 0:
        return float(radius)
    return default_radius


def simulate_path(
    path: Path,
    config: Optional[Dict] = None,
    dt_s: float = 0.02,
) -> SimResult:
    cfg = config or {}
    segments, anchors, anchor_path_indices = _build_segments(path)

    poses_by_time: Dict[float, Tuple[float, float, float]] = {}
    times_sorted: List[float] = []
    trail_points: List[Tuple[float, float]] = []

    if len(anchors) < 2 or len(segments) == 0:
        if anchors:
            x0, y0 = anchors[0]
            poses_by_time[0.0] = (x0, y0, 0.0)
            times_sorted = [0.0]
            trail_points = [(x0, y0)]
        return SimResult(poses_by_time=poses_by_time, times_sorted=times_sorted, total_time_s=0.0, trail_points=trail_points)

    c = getattr(path, "constraints", None)
    initial_v = _resolve_constraint(getattr(c, "initial_velocity_meters_per_sec", None), cfg.get("initial_velocity_meters_per_sec"), 0.0)
    final_v = _resolve_constraint(getattr(c, "final_velocity_meters_per_sec", None), cfg.get("final_velocity_meters_per_sec"), 0.0)
    max_v = _resolve_constraint(getattr(c, "max_velocity_meters_per_sec", None), cfg.get("max_velocity_meters_per_sec"), 3.0)
    max_a = _resolve_constraint(getattr(c, "max_acceleration_meters_per_sec2", None), cfg.get("max_acceleration_meters_per_sec2"), 2.5)

    max_omega = math.radians(_resolve_constraint(getattr(c, "max_velocity_deg_per_sec", None), cfg.get("max_velocity_deg_per_sec"), 180.0))
    max_alpha = math.radians(_resolve_constraint(getattr(c, "max_acceleration_deg_per_sec2", None), cfg.get("max_acceleration_deg_per_sec2"), 360.0))
    
    # DEBUG: Print angular constraints
    print(f"DEBUG: Angular constraints - max_omega={math.degrees(max_omega):.1f}°/s, max_alpha={math.degrees(max_alpha):.1f}°/s²")

    # Default handoff radius from config
    default_handoff_radius = _resolve_constraint(None, cfg.get("intermediate_handoff_radius_meters"), 0.05)

    total_path_len = 0.0
    cumulative_lengths: List[float] = [0.0]
    for seg in segments:
        L = max(seg.length_m, 0.0)
        total_path_len += L
        cumulative_lengths.append(total_path_len)

    first_seg = segments[0]
    start_heading_base = _default_heading(first_seg.ax, first_seg.ay, first_seg.bx, first_seg.by)

    # Build global rotation keyframes (across multiple segments) and compute initial heading at s=0
    global_keyframes = _build_global_rotation_keyframes(path, anchor_path_indices, cumulative_lengths)
    initial_heading, _, _ = _desired_heading_for_global_s(global_keyframes, 0.0, start_heading_base)

    x = first_seg.ax
    y = first_seg.ay
    theta = initial_heading

    dx = first_seg.bx - x
    dy = first_seg.by - y
    dist = hypot2(dx, dy)
    ux = dx / dist if dist > 1e-9 else 1.0
    uy = dy / dist if dist > 1e-9 else 0.0
    speeds = ChassisSpeeds(vx_mps=ux * initial_v, vy_mps=uy * initial_v, omega_radps=0.0)

    t_s = 0.0
    seg_idx = 0

    def remaining_distance_from(seg_index: int, current_x: float, current_y: float, proj_s: float) -> float:
        if seg_index >= len(segments):
            return 0.0
        seg = segments[seg_index]
        rem_in_seg = max(0.0, seg.length_m - proj_s)
        rem = rem_in_seg
        for k in range(seg_index + 1, len(segments)):
            rem += max(segments[k].length_m, 0.0)
        return rem

    guard_time = max(25.0, (total_path_len / max(0.5, max_v)) * 5.0)

    while t_s <= guard_time:
        if seg_idx >= len(segments):
            break

        seg = segments[seg_idx]

        dx = seg.bx - x
        dy = seg.by - y
        dist_to_target = hypot2(dx, dy)

        proj_dx = x - seg.ax
        proj_dy = y - seg.ay
        projected_s = dot(proj_dx, proj_dy, seg.ux, seg.uy)
        projected_s = max(0.0, min(projected_s, seg.length_m))

        # Get the current handoff radius for this segment
        current_handoff_radius = _get_handoff_radius_for_segment(path, seg_idx, anchor_path_indices, default_handoff_radius)

        while seg_idx < len(segments) and dist_to_target <= current_handoff_radius:
            seg_idx += 1
            if seg_idx >= len(segments):
                break
            seg = segments[seg_idx]
            dx = seg.bx - x
            dy = seg.by - y
            dist_to_target = hypot2(dx, dy)
            proj_dx = x - seg.ax
            proj_dy = y - seg.ay
            projected_s = dot(proj_dx, proj_dy, seg.ux, seg.uy)
            projected_s = max(0.0, min(projected_s, seg.length_m))
            # Update handoff radius for the new segment
            current_handoff_radius = _get_handoff_radius_for_segment(path, seg_idx, anchor_path_indices, default_handoff_radius)

        if seg_idx >= len(segments):
            break

        if dist_to_target > 1e-9:
            ux = dx / dist_to_target
            uy = dy / dist_to_target
        else:
            ux = 1.0
            uy = 0.0

        progress_t = projected_s / seg.length_m if seg.length_m > 1e-9 else 0.0

        # Compute desired heading using global keyframes at absolute distance along path
        global_s = cumulative_lengths[seg_idx] + projected_s
        desired_theta, dtheta_ds, profiled_rotation = _desired_heading_for_global_s(global_keyframes, global_s, start_heading_base)

        v_proj = dot(speeds.vx_mps, speeds.vy_mps, ux, uy)
        v_curr = max(v_proj, 0.0)

        remaining = remaining_distance_from(seg_idx, x, y, projected_s)

        abs_dtheta_ds = abs(dtheta_ds)
        if profiled_rotation:
            # Profiled: translation speed limited by heading change rate
            if abs_dtheta_ds > 1e-9:
                max_v_dyn = max_omega / abs_dtheta_ds
                max_a_dyn = max_alpha / abs_dtheta_ds
            else:
                max_v_dyn = max_v + 100.0
                max_a_dyn = max_a + 100.0
        else:
            # Non-profiled rotation should not bottleneck translation speed
            max_v_dyn = max_v
            max_a_dyn = max_a

        max_a_mag = min(max_a, max_a_dyn)

        v_allow_decel = math.sqrt(max(final_v * final_v, 0.0) + 2.0 * max_a_mag * remaining)
        v_max_accel = v_curr + max_a_mag * dt_s
        v_min_decel = max(0.0, v_curr - max_a_mag * dt_s)

        unconstrained_v_des = min(max_v, max_v_dyn, v_allow_decel)

        v_des_scalar = max(v_min_decel, min(v_max_accel, unconstrained_v_des))

        vx_des = v_des_scalar * ux
        vy_des = v_des_scalar * uy

        # ROTATION CONTROL: Choose between profiled and trapezoidal motion
        if profiled_rotation:
            # PROFILED ROTATION: Direct angular error calculation for smooth motion
            angular_error = shortest_angular_distance(desired_theta, theta)
            
            # Calculate the required angular velocity to reach target in one timestep
            required_omega = angular_error / dt_s
            
            # Limit to maximum angular velocity
            if abs(required_omega) > max_omega:
                omega_des = math.copysign(max_omega, required_omega)
            else:
                omega_des = required_omega
                
            # Apply normal acceleration limiting for profiled rotation
            limited = limit_acceleration(
                desired=ChassisSpeeds(vx_des, vy_des, omega_des),
                last=speeds,
                dt=dt_s,
                max_trans_accel_mps2=max_a,
                max_angular_accel_radps2=max_alpha,
            )
        else:
            # NON-PROFILED ROTATION: Use trapezoidal motion profile for fast rotation
            omega_des = _trapezoidal_rotation_profile(
                current_theta=theta,
                target_theta=desired_theta,
                current_omega=speeds.omega_radps,
                max_omega=max_omega,
                max_alpha=max_alpha,
                dt=dt_s
            )
            
            # For non-profiled rotation, use normal acceleration limiting
            # The trapezoidal profile now handles smooth acceleration internally
            limited = limit_acceleration(
                desired=ChassisSpeeds(vx_des, vy_des, omega_des),
                last=speeds,
                dt=dt_s,
                max_trans_accel_mps2=max_a,
                max_angular_accel_radps2=max_alpha,  # Use normal angular acceleration limits
            )

        v_mag = hypot2(limited.vx_mps, limited.vy_mps)
        if v_mag > max_v > 0.0:
            scale = max_v / v_mag
            limited = ChassisSpeeds(limited.vx_mps * scale, limited.vy_mps * scale, limited.omega_radps)
        if abs(limited.omega_radps) > max_omega > 0.0:
            limited = ChassisSpeeds(limited.vx_mps, limited.vy_mps, math.copysign(max_omega, limited.omega_radps))

        x += limited.vx_mps * dt_s
        y += limited.vy_mps * dt_s
        theta = wrap_angle_radians(theta + limited.omega_radps * dt_s)

        t_key = round(t_s, 3)
        poses_by_time[t_key] = (float(x), float(y), float(theta))
        times_sorted.append(t_key)
        
        # Add current position to trail
        trail_points.append((float(x), float(y)))

        at_end = seg_idx >= len(segments)
        if at_end:
            if v_mag <= max(0.05, final_v + 0.05) and abs(limited.omega_radps) <= math.radians(5.0):
                break

        t_s += dt_s
        speeds = limited

    last_time = round(t_s, 3)
    if last_time not in poses_by_time and times_sorted:
        poses_by_time[last_time] = poses_by_time[times_sorted[-1]]
        times_sorted.append(last_time)

    seen = set()
    uniq_times: List[float] = []
    for tk in times_sorted:
        if tk in seen:
            continue
        seen.add(tk)
        uniq_times.append(tk)

    total_time_s = uniq_times[-1] if uniq_times else 0.0
    return SimResult(poses_by_time=poses_by_time, times_sorted=uniq_times, total_time_s=total_time_s, trail_points=trail_points)