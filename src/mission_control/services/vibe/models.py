"""Vibe scene models.

Scene state is persisted across restarts (design decision confirmed with user).
"""

from __future__ import annotations

from pydantic import BaseModel

SCENE_NAMES: list[str] = [
    "CRIMSON VORTEX", "SOLAR APPROACH", "THE HIVE",    "DEEP TRANSIT",
    "HYPERSLEEP",     "ICHOR FLOW",     "THE NEST",    "DERELICT",
    "SINGULARITY",    "NEURAL MAP",     "MOTION TRACKER", "BLOOD ORBIT",
]


class SceneState(BaseModel):
    scene: int = 0

    @property
    def name(self) -> str:
        return SCENE_NAMES[self.scene] if 0 <= self.scene < len(SCENE_NAMES) else "UNKNOWN"

    def is_valid_scene(self, sid: int) -> bool:
        return 0 <= sid < len(SCENE_NAMES)
