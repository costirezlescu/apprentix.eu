"""Small JSON-stat 2.0 helpers shared by the PxWeb-family national connectors
(SSB PxWebApi v2, CSO PX-Stat). Not a connector (name starts with "_")."""

from __future__ import annotations

import itertools


def categories(js: dict, dim: str) -> list[str]:
    """Category codes of a dimension, in dataset order."""
    idx = js["dimension"][dim]["category"].get("index")
    if idx is None:
        return list(js["dimension"][dim]["category"]["label"])
    return sorted(idx, key=idx.get) if isinstance(idx, dict) else list(idx)


def labels(js: dict, dim: str) -> dict:
    lab = js["dimension"][dim]["category"].get("label", {})
    return {c: (lab.get(c) or c).strip() for c in categories(js, dim)}


def cells(js: dict):
    """Yield ({dim: code}, value, status) for every cell, including empty ones."""
    ids = js["id"]
    cats = [categories(js, d) for d in ids]
    values = js.get("value", {})
    status = js.get("status") or {}
    if isinstance(values, list):
        get = lambda i: values[i] if i < len(values) else None
    else:
        get = lambda i: values.get(str(i))
    if isinstance(status, list):
        st = lambda i: status[i] if i < len(status) else None
    else:
        st = lambda i: status.get(str(i))
    for i, combo in enumerate(itertools.product(*cats)):
        yield dict(zip(ids, combo)), get(i), st(i)
