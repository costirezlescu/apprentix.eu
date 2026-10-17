"""Cedefop Daily: a morning paper on what Cedefop works on, built from public sources.

  python -m pipeline.daily.fetch 2026-10-19     fetch and tag sources → daily/pool/<date>.json
  python -m pipeline.daily.check 2026-10-19     check an edition against its pool
  python -m pipeline.daily.render 2026-10-19    edition JSON → daily/<date>/index.html (+ daily/index.html)

Editorial rules, sources and decisions: cedefop-daily/ (BLUEPRINT.md, DECISIONS.md).
"""
