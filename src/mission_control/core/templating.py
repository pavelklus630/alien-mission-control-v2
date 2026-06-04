"""Jinja2 templating helper.

Each service keeps its templates next to its code (``<service>/templates``).
Migrating v1's baked-in HTML strings into real templates lets us inject config
(API base, feature flags) and, later, host editor UIs — without touching v1's
markup behavior (the v1 pages contain no Jinja tokens, verified).
"""

from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates


def service_templates(service_module_file: str) -> Jinja2Templates:
    """Build a Jinja2Templates rooted at ``<service dir>/templates``."""
    template_dir = Path(service_module_file).resolve().parent / "templates"
    return Jinja2Templates(directory=str(template_dir))
