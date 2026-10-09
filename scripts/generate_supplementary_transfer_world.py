#!/usr/bin/env python3
"""Deterministically generate the matched Gazebo world and occupancy map for pilot B."""
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[1] / 'src/eacr_sim'
world_path = root / 'worlds' / 'transfer_courtyard.sdf.xacro'
map_path = root / 'maps' / 'transfer_courtyard.pgm'
yaml_path = root / 'maps' / 'transfer_courtyard.yaml'
# Axis-aligned Gazebo boxes; the same geometry is rasterized into Nav2's map.
boxes = [
    ('south_wall', 0, -4, 8.4, .2), ('north_wall', 0, 4, 8.4, .2),
    ('west_wall', -4, 0, .2, 8.4), ('east_wall', 4, 0, .2, 8.4),
    ('center_barrier', .1, .1, .6, 1.6),
    ('southeast_column', 1.8, -1.35, .8, .8),
    ('northwest_column', -1.55, 1.7, .75, .65),
]
parts = ['''<?xml version="1.0"?>
<sdf version="1.6" xmlns:xacro="http://www.ros.org/wiki/xacro">
<xacro:arg name="headless" default="true"/>
<world name="default">
<plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
<plugin filename="gz-sim-user-commands-system" name="gz::sim::systems::UserCommands"/>
<xacro:unless value="$(arg headless)"><plugin filename="gz-sim-scene-broadcaster-system" name="gz::sim::systems::SceneBroadcaster"/></xacro:unless>
<plugin filename="gz-sim-sensors-system" name="gz::sim::systems::Sensors"><render_engine>ogre2</render_engine></plugin>
<plugin filename="gz-sim-imu-system" name="gz::sim::systems::Imu"/>
<light name="sun" type="directional"><pose>0 0 10 0 0 0</pose><diffuse>0.8 0.8 0.8 1</diffuse><specular>0.8 0.8 0.8 1</specular><direction>-0.5 0.1 -0.9</direction></light>
<model name="ground_plane"><static>true</static><link name="link"><collision name="collision"><geometry><plane><normal>0 0 1</normal><size>100 100</size></plane></geometry></collision><visual name="visual"><geometry><plane><normal>0 0 1</normal><size>100 100</size></plane></geometry><material><ambient>.8 .8 .8 1</ambient><diffuse>.8 .8 .8 1</diffuse></material></visual></link></model>
''']
for name, x, y, sx, sy in boxes:
    parts.append(f'<model name="{name}"><static>true</static><pose>{x} {y} 0.4 0 0 0</pose><link name="link"><collision name="collision"><geometry><box><size>{sx} {sy} 0.8</size></box></geometry></collision><visual name="visual"><geometry><box><size>{sx} {sy} 0.8</size></box></geometry><material><ambient>0.35 0.45 0.6 1</ambient><diffuse>0.35 0.45 0.6 1</diffuse></material></visual></link></model>')
parts.append('</world></sdf>\n')
world_path.write_text('\n'.join(parts))
resolution = .05
size = 200
origin = -5.0
im = Image.new('L', (size, size), 254)
draw = ImageDraw.Draw(im)
# The physically free but unmapped goal patch makes the NavFn
# GridBased.allow_unknown parameter a behaviorally testable planner fault.
unknown = (1.65, 1.65, 3.35, 3.35)
x0 = int((unknown[0] - origin) / resolution)
x1 = int((unknown[2] - origin) / resolution)
y0 = size - 1 - int((unknown[3] - origin) / resolution)
y1 = size - 1 - int((unknown[1] - origin) / resolution)
draw.rectangle((x0, y0, x1, y1), fill=205)
for _, x, y, sx, sy in boxes:
    x0 = int((x - sx / 2 - origin) / resolution)
    x1 = int((x + sx / 2 - origin) / resolution)
    y0 = size - 1 - int((y + sy / 2 - origin) / resolution)
    y1 = size - 1 - int((y - sy / 2 - origin) / resolution)
    draw.rectangle((x0, y0, x1, y1), fill=0)
im.save(map_path)
yaml_path.write_text('image: transfer_courtyard.pgm\nresolution: 0.05\norigin: [-5.0, -5.0, 0.0]\nnegate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.196\n')
print(world_path)
print(yaml_path)
