#!/usr/bin/env python3
"""Read-only consistency audit for the supplementary transfer map/world/route."""
from __future__ import annotations

import hashlib
import heapq
import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
MAP_YAML = ROOT / 'src/eacr_sim/maps/transfer_courtyard.yaml'
MAP_IMAGE = ROOT / 'src/eacr_sim/maps/transfer_courtyard.pgm'
WORLD = ROOT / 'src/eacr_sim/worlds/transfer_courtyard.sdf.xacro'
EPISODE = ROOT / 'src/eacr_sim/config/episode_transfer_courtyard.yaml'
GENERATOR = ROOT / 'scripts/generate_supplementary_transfer_world.py'
OUT = ROOT / 'results/supplementary_transfer_geometry_audit.json'


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def yaml_values(path: Path) -> tuple[float, float, float, float, float]:
    content = path.read_text()
    resolution = float(re.search(r'^resolution:\s*([\d.]+)', content, re.M).group(1))
    origin = [float(x.strip()) for x in re.search(r'^origin:\s*\[([^]]+)\]', content, re.M).group(1).split(',')]
    return resolution, origin[0], origin[1], float(re.search(r'^occupied_thresh:\s*([\d.]+)', content, re.M).group(1)), float(re.search(r'^free_thresh:\s*([\d.]+)', content, re.M).group(1))


def pose_values(text: str) -> tuple[float, float, float]:
    vals = [float(x) for x in text.split()]
    return vals[0], vals[1], vals[5] if len(vals) >= 6 else 0.0


def xy_to_pixel(x: float, y: float, resolution: float, ox: float, oy: float, width: int, height: int) -> tuple[int, int]:
    return int((x - ox) / resolution), height - 1 - int((y - oy) / resolution)


def find_path(image: Image.Image, start: tuple[int, int], goal: tuple[int, int], *, allow_unknown: bool) -> list[tuple[int, int]] | None:
    pixels = image.load()
    width, height = image.size

    def traversable(x: int, y: int) -> bool:
        if not (0 <= x < width and 0 <= y < height):
            return False
        value = pixels[x, y]
        return value != 0 and (allow_unknown or value not in (205,))

    if not traversable(*start) or not traversable(*goal):
        return None
    queue = [(0, start)]
    came_from = {start: None}
    costs = {start: 0}
    while queue:
        _, current = heapq.heappop(queue)
        if current == goal:
            path = []
            while current is not None:
                path.append(current)
                current = came_from[current]
            return list(reversed(path))
        x, y = current
        for nxt in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if not traversable(*nxt):
                continue
            new_cost = costs[current] + 1
            if new_cost >= costs.get(nxt, math.inf):
                continue
            costs[nxt] = new_cost
            came_from[nxt] = current
            heuristic = abs(goal[0] - nxt[0]) + abs(goal[1] - nxt[1])
            heapq.heappush(queue, (new_cost + heuristic, nxt))
    return None


def main() -> None:
    resolution, ox, oy, occupied_thresh, free_thresh = yaml_values(MAP_YAML)
    image = Image.open(MAP_IMAGE).convert('L')
    width, height = image.size
    episode_text = EPISODE.read_text()
    initial = tuple(float(re.search(rf'^    initial_pose_{axis}:\s*([-\d.]+)', episode_text, re.M).group(1)) for axis in ('x', 'y'))
    goal = tuple(float(re.search(rf'^    goal_pose_{axis}:\s*([-\d.]+)', episode_text, re.M).group(1)) for axis in ('x', 'y'))
    start_pixel = xy_to_pixel(*initial, resolution, ox, oy, width, height)
    goal_pixel = xy_to_pixel(*goal, resolution, ox, oy, width, height)
    start_value = image.getpixel(start_pixel)
    goal_value = image.getpixel(goal_pixel)
    free_path = find_path(image, start_pixel, goal_pixel, allow_unknown=True)
    strict_path = find_path(image, start_pixel, goal_pixel, allow_unknown=False)

    root = ET.parse(WORLD).getroot()
    world = root.find('world')
    obstacles = []
    for model in world.findall('model'):
        pose = model.findtext('pose')
        size_text = model.findtext('./link/collision/geometry/box/size')
        if pose and size_text:
            x, y, yaw = pose_values(pose)
            sx, sy, sz = [float(v) for v in size_text.split()]
            obstacles.append({'name': model.get('name'), 'x': x, 'y': y, 'size_x': sx, 'size_y': sy, 'size_z': sz, 'yaw': yaw})

    expected_occupied = Image.new('L', (width, height), 254)
    expected_draw = ImageDraw.Draw(expected_occupied)
    for box in obstacles:
        x0 = int((box['x'] - box['size_x'] / 2 - ox) / resolution)
        x1 = int((box['x'] + box['size_x'] / 2 - ox) / resolution)
        y0 = height - 1 - int((box['y'] + box['size_y'] / 2 - oy) / resolution)
        y1 = height - 1 - int((box['y'] - box['size_y'] / 2 - oy) / resolution)
        expected_draw.rectangle((x0, y0, x1, y1), fill=0)
    occupied_pixel_mismatches = sum(
        (image.getpixel((x, y)) == 0) != (expected_occupied.getpixel((x, y)) == 0)
        for y in range(height) for x in range(width)
    )

    def clearance(point: tuple[float, float], box: dict) -> float:
        dx = max(abs(point[0] - box['x']) - box['size_x'] / 2, 0.0)
        dy = max(abs(point[1] - box['y']) - box['size_y'] / 2, 0.0)
        return math.hypot(dx, dy)

    closest_start = min((clearance(initial, b), b['name']) for b in obstacles)
    closest_goal = min((clearance(goal, b), b['name']) for b in obstacles)
    obstacle_raster_checks = []
    for box in obstacles:
        center_pixel = xy_to_pixel(box['x'], box['y'], resolution, ox, oy, width, height)
        center_value = image.getpixel(center_pixel)
        obstacle_raster_checks.append({
            'model': box['name'], 'center_pixel_xy': center_pixel,
            'center_pixel_value': center_value, 'center_is_occupied': center_value == 0,
        })
    unique_values = sorted(set(image.getdata()))
    unknown_pixels = [(x, y) for y in range(height) for x in range(width) if image.getpixel((x, y)) == 205]
    unknown_bounds_pixels = {
        'min_x': min(x for x, _ in unknown_pixels), 'max_x': max(x for x, _ in unknown_pixels),
        'min_y': min(y for _, y in unknown_pixels), 'max_y': max(y for _, y in unknown_pixels),
    } if unknown_pixels else None
    audit = {
        'audit_id': 'eacr_supplementary_transfer_geometry_v1',
        'inputs_sha256': {str(p.relative_to(ROOT)): sha256(p) for p in (MAP_YAML, MAP_IMAGE, WORLD, EPISODE, GENERATOR)},
        'map': {'size_pixels': [width, height], 'resolution_m': resolution, 'origin_xy_m': [ox, oy],
                'occupied_threshold': occupied_thresh, 'free_threshold': free_thresh,
                'pixel_values': unique_values, 'unknown_pixel_count': len(unknown_pixels),
                'unknown_bounds_pixel_inclusive': unknown_bounds_pixels},
        'route': {'initial_pose_xy_m': initial, 'goal_xy_m': goal,
                  'start_pixel_xy': start_pixel, 'goal_pixel_xy': goal_pixel,
                  'start_pixel_value': start_value, 'goal_pixel_value': goal_value,
                  'start_is_free_white': start_value >= 250, 'goal_is_unknown_gray': goal_value == 205,
                  'grid_path_allow_unknown_true_exists': free_path is not None,
                  'grid_path_allow_unknown_false_exists': strict_path is not None,
                  'allow_unknown_true_path_length_m': (len(free_path) - 1) * resolution if free_path else None},
        'world': {'box_obstacle_count': len(obstacles), 'box_obstacles': obstacles,
                  'obstacle_center_raster_checks': obstacle_raster_checks,
                  'all_obstacle_centers_match_occupied_raster': all(item['center_is_occupied'] for item in obstacle_raster_checks),
                  'occupied_pixel_mismatch_count_vs_box_geometry': occupied_pixel_mismatches,
                  'nearest_obstacle_clearance_from_start_m': closest_start[0], 'nearest_start_obstacle': closest_start[1],
                  'nearest_obstacle_clearance_from_goal_m': closest_goal[0], 'nearest_goal_obstacle': closest_goal[1]},
        'static_checks_pass': bool(start_value >= 250 and goal_value == 205 and free_path and strict_path is None
                                   and all(item['center_is_occupied'] for item in obstacle_raster_checks)
                                   and occupied_pixel_mismatches == 0
                                   and closest_start[0] > 0.25 and closest_goal[0] > 0.25),
        'scope_limit': 'This proves raster/world geometry and grid connectivity only. It does not prove Nav2 normal navigation, runtime fault behavior, rollback, or recovery; the separate Gazebo/ROS engineering pilot remains mandatory before freezing B.',
    }
    OUT.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + '\n')
    print(OUT)
    print('static_checks_pass=', audit['static_checks_pass'], 'start=', start_value, 'goal=', goal_value,
          'path_allow_unknown=', audit['route']['grid_path_allow_unknown_true_exists'],
          'path_disallow_unknown=', audit['route']['grid_path_allow_unknown_false_exists'])


if __name__ == '__main__':
    main()
