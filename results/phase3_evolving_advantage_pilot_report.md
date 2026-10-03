# EACR-Evolving advantage pilot report

Protocol: `eacr_evolving_advantage_v1`; all included records use `weak_shared_m0`, the same belief action scope, four repeated episodes per cell, and valid Gazebo lifecycle evidence.

## Included paired cells

- Nominal planner, seed `20410001`: Static M0 vs online Evolving M0.
- Nominal control, seed `20410002`: Static M0 vs online Evolving M0.
- Nominal costmap, seed `20410003`: Static M0 vs online Evolving M0.
- Shifted planner, seed `20410004`, `fault_scale=1.5`: Static M0 vs online Evolving M0.

The invalid first costmap attempt is excluded; the retry is the newest protocol-compliant record. No record from the frozen original phase-three aggregate is overwritten.

## Pilot aggregate

| metric | Static M0 | Evolving online M0 | paired delta (Evolving − Static) |
|---|---:|---:|---:|
| intervention recovery rate | 0.250 | 0.563 | +0.313 |
| sustained recovery rate | 0.250 | 0.500 | +0.250 |
| useless probe rate | 0.750 | 0.438 | −0.313 |
| mean intervention cost | 0.240 | 0.363 | +0.123 |

The intervention recovery gain is positive in all four paired cells; the deterministic bootstrap 95% CI is `[0.125, 0.500]`. The sustained recovery CI is `[0.000, 0.500]`, so this pilot is evidence of adaptation and a preregistered check, not the final claim of statistical superiority. The higher intervention cost reflects Evolving taking a real recovery action instead of stopping at a diagnostic probe.

Source: `phase3_evolving_advantage_pilot_aggregate.json`.
