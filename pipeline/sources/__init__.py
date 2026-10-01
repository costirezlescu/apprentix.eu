"""Connector registry.

Each module in this package is one upstream source. A connector module defines:

  SOURCE = {
      "id": "eurostat",                 # unique, used for data/raw/<id>/
      "name": "Eurostat",               # shown on the Data & sources page
      "publisher": "...",
      "homepage": "https://...",
      "description": "What it provides for apprentix.eu.",
      "access": "api" | "file" | "manual",
      "browser_cors": True | False | None,  # can a visitor's browser call it directly?
      "licence": "CC-BY-4.0",           # key in common.LICENCES, or free text
      "cadence": "annual (Aug–Sep)",
      "secret": None | "ENV_VAR_NAME",  # connector is skipped when this env var is unset
      "outputs": ["indicators/eurostat-tps00215", ...],  # what it writes (informative)
  }

  def run() -> list[str]:  # returns repo-relative paths written

Modules whose name starts with "_" are not connectors. `_catalogue.py` lists
sources that are tracked but cannot be fetched automatically.

Connectors are discovered automatically: adding a file here is enough.
"""

from __future__ import annotations

import importlib
import pkgutil


def discover() -> dict:
    mods = {}
    for info in pkgutil.iter_modules(__path__):
        if info.name.startswith("_"):
            continue
        m = importlib.import_module(f"{__name__}.{info.name}")
        if hasattr(m, "SOURCE") and hasattr(m, "run"):
            mods[m.SOURCE["id"]] = m
    return dict(sorted(mods.items()))
