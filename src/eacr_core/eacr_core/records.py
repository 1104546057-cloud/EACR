"""Uniform JSON event and episode records for reproducible experiments."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


@dataclass
class EpisodeRecorder:
    episode_id: str
    seed: int
    result_dir: Path
    events: list[dict[str, Any]] = field(default_factory=list)

    def record(self, event_type: str, **payload: Any) -> dict[str, Any]:
        event = {
            "episode_id": self.episode_id,
            "seed": self.seed,
            "event_index": len(self.events),
            "time_unix": time.time(),
            "event_type": event_type,
            "payload": payload,
        }
        self.events.append(event)
        return event

    def write(self, summary: Mapping[str, Any] | None = None) -> tuple[Path, Path]:
        self.result_dir.mkdir(parents=True, exist_ok=True)
        event_path = self.result_dir / f"{self.episode_id}.events.jsonl"
        summary_path = self.result_dir / f"{self.episode_id}.summary.json"
        event_path.write_text(
            "".join(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n" for event in self.events)
        )
        summary_path.write_text(
            json.dumps(
                {
                    "episode_id": self.episode_id,
                    "seed": self.seed,
                    "event_count": len(self.events),
                    "summary": dict(summary or {}),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
        return event_path, summary_path
