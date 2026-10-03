# Phase 4 checkpoint-load pilot

- Protocol: `eacr_evolving_advantage_v1`
- Scope: one held-out final evaluation seed (`544047076`), planner family, four repeated episodes.
- Fault scale: `1.5`.
- Prior: `weak_shared_m0`.
- Belief action scope: enabled.
- Training source: 13 training seeds, 52 valid planner feedback episodes.
- Checkpoint: `results/phase4_experience_evolving_M_50.json`.
- Snapshot SHA-256: `1f1765a45e2ce3ddd27f392d1b94adafc950b52d96eba4af5c5d3cd9723703de`.

## Paired result

| Method | Intervention recovery | Sustained recovery | Useless probe | Mean intervention cost |
|---|---:|---:|---:|---:|
| EACR-Static M0 | 0.00 | 0.00 | 1.00 | 0.18 |
| EACR-Evolving M50 | 1.00 | 0.75 | 0.00 | 0.55 |

The Evolving M50 record is protocol-compliant, records the snapshot path and SHA, and has `online_experience_update=false` for all four episodes. This is a checkpoint-load and mechanism validation only. It is not the final four-family statistical claim because the current training source covers planner feedback only; the full protocol requires all four fault families for every training seed.
