"""Map GM state model.

Erebos-only for now (confirmed with user). The model is shaped so multi-map
support is a small later addition rather than a rewrite.
"""

from __future__ import annotations

from pydantic import BaseModel


class MapState(BaseModel):
    title_hidden: bool = False
    menu_hidden: bool = False
