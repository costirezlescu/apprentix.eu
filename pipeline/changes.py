"""What changed in the published data since the previous build.

  python -m pipeline.changes     compare with the stored snapshot, log what changed

  data/published/changes/snapshot.json   compact fingerprint of everything published
  data/published/changes/log.json        newest-first human-readable change log (last 26 entries)

The snapshot holds, per indicator, the default-breakdown value of every
geo/period plus a hash of the full series; per record dataset, the record
count, a hash, and the record ids (with a short content hash per record for
small datasets; per-country counts for very large ones); for the VET policy
timeline also each policy's latest stage and year.

On each build the current state is compared with the snapshot. When anything
differs, one dated entry (date from common.today()) is added to the log and the
snapshot replaced. When nothing differs, neither file is touched, so reruns are
byte-identical. The first run only records a baseline entry; it does not claim
that everything is new.

Run after the connectors (it reads what they published) and before page rendering.
"""

from __future__ import annotations

import hashlib
import json
import sys

from .common import DATA, INDICATORS, PUBLISHED, ROOT, countries, read_json, today, write_json

OUT = PUBLISHED / "changes"
SNAPSHOT = OUT / "snapshot.json"
LOG = OUT / "log.json"

LOG_KEEP = 26          # entries (about six months of weekly refreshes)
TEXT_MAX = 200
TITLE_MAX = 110
RECORD_HASH_MAX = 2500     # datasets up to this size keep a content hash per record
RECORD_IDS_MAX = 5000      # ... up to this size keep their ids; larger keep per-country counts
POLICY_DATASET = "vet-policy-timeline"

# Per kind: how many individual items an entry keeps before the rest are summarised.
KIND_LIMIT = {"new-period": 8, "new-data": 4, "revision": 4, "new-records": 6,
              "updated-records": 4, "removed-records": 4, "policy-stage": 4}

SNAPSHOT_VERSION = 1


# ---------------------------------------------------------------- helpers --

def _h(obj, n: int = 16) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:n]


def clip(s: str, n: int = TEXT_MAX) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1].rstrip(" ,;:") + "…"


def _geo_name(code: str) -> str:
    c = countries()["by_code"].get(code)
    if not c:
        return code
    return "EU-27" if code == "EU27" else c["name"]


def _is_country(code: str) -> bool:
    c = countries()["by_code"].get(code)
    return bool(c) and c.get("group") != "aggregate"


def _fmt(v, unit) -> str:
    from .render_pages import fmt_value
    return fmt_value(float(v), unit)


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _period(t: str) -> str:
    t = str(t)
    if len(t) == 7 and t[4] == "-" and t[5:].isdigit() and 1 <= int(t[5:]) <= 12:
        return f"{MONTHS[int(t[5:]) - 1]} {t[:4]}"
    return t


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n:,} {one if n == 1 else (many or one + 's')}"


def _list(names: list[str], total: int | None = None, k: int = 3) -> str:
    total = len(names) if total is None else total
    shown = [str(x) for x in names[:k]]
    rest = total - len(shown)
    s = ", ".join(shown)
    return s + (f" and {rest:,} more" if rest > 0 else "")


# ---------------------------------------------------------------- load -----

def load_state() -> dict:
    """Everything the snapshot is computed from: indicators and record datasets."""
    inds = {}
    for p in sorted(INDICATORS.glob("*.json")):
        if p.name == "index.json":
            continue
        ind = read_json(p)
        inds[ind["id"]] = ind
    dss = {}
    manifest = read_json(DATA / "datasets.json")
    for d in manifest.get("datasets", []):
        base = ROOT / d.get("path", f"data/published/{d['id']}")
        if not (base / "records.json").exists():
            continue
        records = read_json(base / "records.json")
        if not isinstance(records, list):
            continue
        meta = read_json(base / "meta.json") if (base / "meta.json").exists() else {}
        dss[d["id"]] = {"entry": d, "meta": meta, "records": records}
    return {"indicators": inds, "datasets": dss}


# ---------------------------------------------------------------- fingerprint

def _defaults(ind: dict) -> dict:
    out = {}
    for d in ind.get("dims") or []:
        dflt = d.get("default")
        if dflt is None and d.get("values"):
            dflt = next(iter(d["values"]))
        out[d["key"]] = dflt
    return out


def default_values(ind: dict) -> dict:
    """{geo: {time: value}} for the default breakdown (what the site headlines)."""
    dflt = _defaults(ind)
    out: dict[str, dict[str, float]] = {}
    for o in ind.get("series", []):
        dims = o.get("dims") or {}
        if any(dims.get(k, v) != v for k, v in dflt.items()):
            continue
        out.setdefault(o["geo"], {})[str(o["time"])] = o["value"]
    return out


def indicator_fp(ind: dict) -> dict:
    vals = default_values(ind)
    times = sorted({t for g in vals.values() for t in g})
    tix = {t: i for i, t in enumerate(times)}
    grid = {}
    for g in sorted(vals):
        row = [None] * len(times)
        for t, v in vals[g].items():
            row[tix[t]] = v
        grid[g] = row
    all_times = [str(o["time"]) for o in ind.get("series", [])]
    return {
        "title": ind.get("title"),
        "max": max(all_times) if all_times else None,
        "obs": len(ind.get("series", [])),
        "hash": _h([ind.get("series", []), ind.get("missing")]),
        "times": times,
        "values": grid,
    }


def _rid(r: dict) -> str:
    """Short, stable key for a record id (keeps the snapshot small; ids can be long)."""
    return _h(str(r.get("id")), 8)


def _record_country(r: dict):
    for k in ("country_code", "coordinator_country_code"):
        v = r.get(k)
        if isinstance(v, str) and v:
            return v
    return None


def dataset_fp(did: str, ds: dict) -> dict:
    records = ds["records"]
    ids = [_rid(r) for r in records if isinstance(r, dict)]
    fp = {"title": ds["entry"].get("title") or ds["meta"].get("title") or did,
          "count": len(records), "hash": _h(records)}
    if len(records) <= RECORD_HASH_MAX:
        fp["records"] = dict(sorted((_rid(r), _h(r, 8)) for r in records if isinstance(r, dict)))
    elif len(records) <= RECORD_IDS_MAX:
        fp["ids"] = sorted(ids)
    else:
        fp["ids_hash"] = _h(sorted(ids))
        by = {}
        for r in records:
            c = _record_country(r) or "-"
            by[c] = by.get(c, 0) + 1
        fp["by_country"] = dict(sorted(by.items()))
    if did == POLICY_DATASET:
        fp["stages"] = dict(sorted((_rid(r), [r.get("latest_stage"), r.get("latest_year")])
                                   for r in records if isinstance(r, dict)))
    return fp


def fingerprint(state: dict) -> dict:
    return {
        "version": SNAPSHOT_VERSION,
        "indicators": {i: indicator_fp(ind) for i, ind in sorted(state["indicators"].items())},
        "datasets": {d: dataset_fp(d, ds) for d, ds in sorted(state["datasets"].items())},
    }


def dump_snapshot(snap: dict) -> str:
    """JSON with one line per indicator / dataset: compact, yet git diffs stay readable."""
    def one(x):
        return json.dumps(x, ensure_ascii=False, separators=(",", ":"))
    parts = ['{', f' "version": {snap["version"]},',
             ' "description": "Fingerprint of the published data at the last change (pipeline/changes.py). Not for display.",']
    for key in ("indicators", "datasets"):
        items = list(snap[key].items())
        parts.append(f' "{key}": {{')
        for k, (i, v) in enumerate(items):
            parts.append(f'  {one(i)}: {one(v)}' + ("," if k < len(items) - 1 else ""))
        parts.append(" }" + ("," if key == "indicators" else ""))
    parts.append("}")
    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------- diff -----

def _grid_to_values(fp: dict) -> dict:
    out = {}
    for g, row in (fp.get("values") or {}).items():
        out[g] = {t: v for t, v in zip(fp.get("times") or [], row) if v is not None}
    return out


def _headline_geo(ind: dict, vals: dict):
    tg = (ind.get("target") or {}).get("geo")
    if tg and tg in vals:
        return tg
    if "EU27" in vals:
        return "EU27"
    if len(vals) == 1:
        return next(iter(vals))
    return None


def _is_headline(ind: dict) -> bool:
    pos = str((ind.get("kivet") or {}).get("position") or "").lower()
    return "key indicators" in pos


def _ind_link(iid: str) -> str:
    return f"pages/indicators/{iid}.html"


def _countries(codes) -> list[str]:
    return sorted({c for c in codes if c and _is_country(c)})


def diff_indicator(iid: str, old: dict, new: dict, ind: dict) -> list[dict]:
    items = []
    title = ind.get("title") or iid
    unit = ind.get("unit")
    ov, nv = _grid_to_values(old), _grid_to_values(new)
    target = bool(ind.get("target"))
    headline = _is_headline(ind)

    # New period: the indicator's latest period advanced.
    omax, nmax = old.get("max"), new.get("max")
    new_period = bool(nmax and omax and nmax > omax)
    adv = [g for g in nv if nv[g] and (not ov.get(g) or max(nv[g]) > max(ov[g]))]
    hg = _headline_geo(ind, nv)
    if new_period:
        newer = [g for g in nv if nmax in nv[g] and nmax not in (ov.get(g) or {})]
        text = ""
        if hg and nmax in nv.get(hg, {}):
            prev_t = max((t for t in nv[hg] if t < nmax), default=None)
            if prev_t is not None:
                prev_v = (ov.get(hg) or {}).get(prev_t, nv[hg][prev_t])
                text = (f"{_geo_name(hg)}: {_fmt(prev_v, unit)} in {_period(prev_t)} → "
                        f"{_fmt(nv[hg][nmax], unit)} in {_period(nmax)}. ")
            else:
                text = f"{_geo_name(hg)}: {_fmt(nv[hg][nmax], unit)} in {_period(nmax)}. "
        elif hg:
            text = f"{_geo_name(hg)} not yet available for {_period(nmax)}. "
        nc = _countries(newer)
        if nc and not (len(nc) == 1 and nc[0] == hg):
            text += f"{_period(nmax)} figures for {_plural(len(nc), 'country', 'countries')}."
        if not text:
            text = f"Data now runs to {_period(nmax)} (previously {_period(omax)})."
        items.append({"kind": "new-period", "title": f"New {_period(nmax)} data: {title}",
                      "text": text, "link": _ind_link(iid), "countries": _countries(newer),
                      "score": 100 if target else 85 if headline else 70 if ind.get("national") else 75,
                      "key": iid})
    else:
        # Same latest period, but some geographies caught up (or appeared).
        caught = [g for g in adv if nv[g]]
        if caught:
            latest = max(max(nv[g]) for g in caught)
            gained = [g for g in caught if not ov.get(g)]
            names = [_geo_name(g) for g in sorted(caught)]
            text = f"Newer figures for {_list(names, k=4)}"
            text += f" (up to {_period(latest)})."
            if gained:
                text += f" Now covers {_list([_geo_name(g) for g in sorted(gained)], k=3)}."
            items.append({"kind": "new-data", "title": f"More countries reported: {title}",
                          "text": text, "link": _ind_link(iid), "countries": _countries(caught),
                          "score": 55 if (target or headline) else 45, "key": iid})

    # Revisions: values that changed for periods present before and after.
    revs, withdrawn = [], 0
    for g, ot in ov.items():
        nt = nv.get(g) or {}
        for t, a in ot.items():
            if t not in nt:
                withdrawn += 1
                continue
            b = nt[t]
            if a != b:
                rel = abs(b - a) / max(abs(a), 1e-9)
                revs.append((rel, abs(b - a), g, t, a, b))
    if revs or withdrawn:
        revs.sort(key=lambda x: (-x[0], -x[1], x[2], x[3]))
        parts = []
        if revs:
            parts.append(f"{_plural(len(revs), 'earlier value')} revised")
        if withdrawn:
            parts.append(f"{_plural(withdrawn, 'value')} withdrawn")
        text = " and ".join(parts) + "."
        if revs:
            big = "; ".join(f"{_geo_name(g)} {_period(t)} {_fmt(a, unit)} → {_fmt(b, unit)}"
                            for _, _, g, t, a, b in revs[:3])
            text += f" Largest: {big}."
        items.append({"kind": "revision", "title": f"Revised figures: {title}", "text": text,
                      "link": _ind_link(iid), "countries": _countries(g for _, _, g, *_ in revs),
                      "score": 50 if target else 40, "key": iid, "n": len(revs)})
    elif not items and old.get("hash") != new.get("hash"):
        # Only other breakdowns (or flags, notes) changed.
        items.append({"kind": "revision", "title": f"Revised figures: {title}",
                      "text": "Values or flags changed in breakdowns other than the headline view.",
                      "link": _ind_link(iid), "score": 30, "key": iid, "n": 0})
    return items


def _record_name(ds: dict, r: dict) -> str:
    f = (ds["meta"].get("display") or {}).get("title")
    for k in ([f] if f else []) + ["title", "name", "name_en", "acronym", "system", "country"]:
        v = r.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return str(r.get("id"))


def _labels(ds: dict) -> tuple[str, str]:
    rl = ds["meta"].get("recordLabel") or {}
    return rl.get("one", "record"), rl.get("many", "records")


def _by_country_text(recs: list[dict]) -> str:
    by = {}
    for r in recs:
        c = _record_country(r)
        if c:
            by[c] = by.get(c, 0) + 1
    if not by:
        return ""
    top = sorted(by.items(), key=lambda x: (-x[1], x[0]))
    return ", ".join(f"{c} {n}" for c, n in top[:6]) + (", …" if len(top) > 6 else "")


def _explore(did: str, rid: str | None = None) -> str:
    from urllib.parse import quote
    return f"pages/explore.html?dataset={quote(did)}" + (f"&open={quote(rid)}" if rid else "")


def diff_dataset(did: str, old: dict, new: dict, ds: dict) -> list[dict]:
    items = []
    if old.get("hash") == new.get("hash"):
        return items
    one, many = _labels(ds)
    title = new.get("title") or did
    by_id = {_rid(r): r for r in ds["records"] if isinstance(r, dict)}
    link = f"pages/datasets/{did}.html"

    def id_set(fp):
        if "records" in fp:
            return set(fp["records"])
        if "ids" in fp:
            return set(fp["ids"])
        return None

    o_ids, n_ids = id_set(old), set(by_id)
    if o_ids is not None:
        added = [k for k in by_id if k not in o_ids]          # dataset order
        removed = sorted(o_ids - n_ids)
        changed = []
        if "records" in old and "records" in new:
            changed = [i for i in by_id if i in o_ids and old["records"][i] != new["records"].get(i)]
    else:
        # Very large dataset: only per-country counts are known.
        added, removed, changed = [], [], []
        ob, nb = old.get("by_country") or {}, new.get("by_country") or {}
        delta = {c: nb.get(c, 0) - ob.get(c, 0) for c in set(ob) | set(nb)}
        up = sorted(((c, d) for c, d in delta.items() if d > 0), key=lambda x: (-x[1], x[0]))
        down = sorted(((c, d) for c, d in delta.items() if d < 0), key=lambda x: (x[1], x[0]))
        nadd, nrem = sum(d for _, d in up), -sum(d for _, d in down)
        if nadd:
            items.append({"kind": "new-records", "title": f"{_plural(nadd, one, many).capitalize()} added: {title}",
                          "text": f"Now {new['count']:,} in total (was {old['count']:,}). Net change by country: "
                                  + ", ".join(f"{c} +{d}" for c, d in up[:8]) + ".",
                          "link": link, "countries": _countries(c for c, _ in up), "score": 55,
                          "key": did, "n": nadd})
        if nrem:
            items.append({"kind": "removed-records", "title": f"{_plural(nrem, one, many).capitalize()} removed: {title}",
                          "text": f"Now {new['count']:,} in total (was {old['count']:,}). Net change by country: "
                                  + ", ".join(f"{c} {d}" for c, d in down[:8]) + ".",
                          "link": link, "countries": _countries(c for c, _ in down), "score": 30,
                          "key": did, "n": nrem})
        if not nadd and not nrem:
            items.append({"kind": "updated-records", "title": f"Records updated: {title}",
                          "text": f"Details of existing {many} changed; the count is unchanged at {new['count']:,}.",
                          "link": link, "score": 30, "key": did, "n": 0})
        return items

    if added:
        recs = [by_id[i] for i in added]
        names = [_record_name(ds, r) for r in recs]
        text = ""
        if len(added) > 3 and _by_country_text(recs):
            text += f"By country: {_by_country_text(recs)}. "
        text += f"Including {_list(names, k=3)}. " if len(added) > 3 else f"{_list(names, k=3)}. "
        text += f"Now {new['count']:,} in total (was {old['count']:,})."
        items.append({"kind": "new-records",
                      "title": f"{_plural(len(added), one, many).capitalize()} added: {title}",
                      "text": text, "link": _explore(did, str(recs[0].get("id"))) if len(added) == 1 else link,
                      "countries": _countries(_record_country(r) for r in recs),
                      "score": 60 if did == POLICY_DATASET else 55, "key": did, "n": len(added)})
    if removed:
        items.append({"kind": "removed-records",
                      "title": f"{_plural(len(removed), one, many).capitalize()} removed: {title}",
                      "text": f"{new['count']:,} in total (was {old['count']:,}). No longer in the source, or merged with another record.",
                      "link": link, "score": 30, "key": did, "n": len(removed)})

    # Policy stage changes (VET policy timeline).
    staged = []
    if did == POLICY_DATASET:
        os_, ns = old.get("stages") or {}, new.get("stages") or {}
        for i in sorted(set(os_) & set(ns)):
            if (os_[i][0] or "") != (ns[i][0] or ""):
                staged.append(i)
        staged.sort(key=lambda i: (-(int(ns[i][1]) if str(ns[i][1] or "").isdigit() else 0), i))
        for i in staged:
            r = by_id[i]
            yr = ns[i][1]
            items.append({"kind": "policy-stage",
                          "title": clip(f"{r.get('country') or ''}: {_record_name(ds, r)}".strip(": "), TITLE_MAX),
                          "text": f"Stage: {os_[i][0] or 'unknown'} → {ns[i][0] or 'unknown'}"
                                  + (f" ({yr})." if yr else "."),
                          "link": _explore(did, str(r.get("id"))), "countries": _countries([_record_country(r)]),
                          "score": 50, "key": f"{did}:{i}", "stage": [os_[i][0], ns[i][0]]})

    changed = [i for i in changed if i not in set(staged)]
    if changed:
        recs = [by_id[i] for i in changed]
        names = [_record_name(ds, r) for r in recs]
        items.append({"kind": "updated-records",
                      "title": f"{_plural(len(changed), one, many).capitalize()} updated: {title}",
                      "text": f"Including {_list(names, k=3)}." if len(names) > 1 else f"{names[0]}.",
                      "link": _explore(did, str(recs[0].get("id"))) if len(changed) == 1 else link,
                      "countries": _countries(_record_country(r) for r in recs),
                      "score": 35, "key": did, "n": len(changed)})
    elif not (added or removed or staged) and "records" not in new:
        items.append({"kind": "updated-records", "title": f"Records updated: {title}",
                      "text": f"Details of existing {many} changed; the count is unchanged at {new['count']:,}.",
                      "link": link, "score": 30, "key": did, "n": 0})
    return items


def _summarise(kind: str, rest: list[dict]) -> dict:
    """One item standing for many of the same kind."""
    n = len(rest)
    names = [it["title"].split(": ", 1)[-1] for it in rest]
    if kind == "policy-stage":
        trans = {}
        for it in rest:
            k = f"{it['stage'][0] or 'unknown'} → {it['stage'][1] or 'unknown'}"
            trans[k] = trans.get(k, 0) + 1
        text = "; ".join(f"{v} {k}" for k, v in sorted(trans.items(), key=lambda x: (-x[1], x[0])))
        return {"kind": kind, "title": f"{n:,} more policies changed stage", "text": text + ".",
                "link": "pages/explore.html?dataset=" + POLICY_DATASET,
                "countries": sorted({c for it in rest for c in it.get("countries", [])}), "score": 0}
    label = {"new-period": "New data in", "new-data": "More countries reported in",
             "revision": "Revised figures in", "new-records": "Records added in",
             "updated-records": "Records updated in", "removed-records": "Records removed from"}.get(kind, "Changes in")
    noun = "indicator" if kind in ("new-period", "new-data", "revision") else "dataset"
    link = "pages/indicators/index.html" if noun == "indicator" else "pages/data.html"
    return {"kind": kind, "title": f"{label} {_plural(n, 'more ' + noun)}",
            "text": f"Including {_list(names, k=4)}.", "link": link,
            "countries": sorted({c for it in rest for c in it.get("countries", [])}), "score": 0}


def diff(old: dict, new: dict, state: dict) -> tuple[list[dict], dict]:
    """(change items, most interesting first; counts per kind). `old`/`new` are fingerprints."""
    items = []
    oi, ni = old.get("indicators", {}), new.get("indicators", {})
    for iid in sorted(set(ni) - set(oi)):
        ind = state["indicators"][iid]
        cov = new["indicators"][iid]
        times = cov["times"] or [cov.get("max")]
        geos = _countries(cov["values"])
        span = f"{_period(times[0])}–{_period(times[-1])}" if len(times) > 1 else _period(times[0] or "")
        items.append({"kind": "new-indicator", "title": f"New indicator: {ind.get('title') or iid}",
                      "text": clip(f"{(ind.get('provenance') or {}).get('publisher', '')} data, {span}, "
                                   f"{_plural(len(geos), 'country', 'countries')}.".lstrip(" ,")),
                      "link": _ind_link(iid), "countries": geos,
                      "score": 90 if ind.get("target") else 80, "key": iid})
    for iid in sorted(set(oi) - set(ni)):
        items.append({"kind": "removed-indicator", "title": f"Indicator withdrawn: {oi[iid].get('title') or iid}",
                      "text": "No longer published by Apprentix; the source stopped providing it or it was merged into another indicator.",
                      "link": "pages/indicators/index.html", "score": 20, "key": iid})
    for iid in sorted(set(oi) & set(ni)):
        if oi[iid] != ni[iid]:
            items += diff_indicator(iid, oi[iid], ni[iid], state["indicators"][iid])

    od, nd = old.get("datasets", {}), new.get("datasets", {})
    for did in sorted(set(nd) - set(od)):
        ds = state["datasets"][did]
        one, many = _labels(ds)
        items.append({"kind": "new-dataset", "title": f"New dataset: {nd[did]['title']}",
                      "text": clip(f"{_plural(nd[did]['count'], one, many)}. {ds['entry'].get('tagline') or ''}"),
                      "link": f"pages/datasets/{did}.html", "score": 80, "key": did})
    for did in sorted(set(od) - set(nd)):
        items.append({"kind": "removed-dataset", "title": f"Dataset withdrawn: {od[did].get('title') or did}",
                      "text": "No longer published by Apprentix.", "link": "pages/data.html", "score": 20, "key": did})
    for did in sorted(set(od) & set(nd)):
        items += diff_dataset(did, od[did], nd[did], state["datasets"][did])

    items.sort(key=lambda it: (-it["score"], it["kind"], -len(it.get("countries") or []), it["title"]))
    # Keep the top few of each kind; summarise the rest in one item per kind.
    kept, overflow = [], {}
    seen: dict[str, int] = {}
    for it in items:
        k = it["kind"]
        seen[k] = seen.get(k, 0) + 1
        if seen[k] > KIND_LIMIT.get(k, 10 ** 6):
            overflow.setdefault(k, []).append(it)
        else:
            kept.append(it)
    for k, rest in overflow.items():
        s = _summarise(k, rest)
        s["score"] = min(it["score"] for it in kept if it["kind"] == k) - 0.5
        kept.append(s)
    kept.sort(key=lambda it: (-it["score"], it["kind"], it["title"]))
    return kept, _counts(items)


def _counts(items: list[dict]) -> dict:
    c: dict[str, int] = {}
    for it in items:
        c[it["kind"]] = c.get(it["kind"], 0) + 1
    out = dict(sorted(c.items()))
    rec_added = sum(it.get("n", 0) for it in items if it["kind"] == "new-records")
    revised = sum(it.get("n", 0) for it in items if it["kind"] == "revision")
    if rec_added:
        out["records_added"] = rec_added
    if revised:
        out["values_revised"] = revised
    return out


def public(item: dict) -> dict:
    out = {"kind": item["kind"], "title": clip(item["title"], TITLE_MAX), "text": clip(item["text"]),
           "link": item["link"]}
    if item.get("countries"):
        out["countries"] = item["countries"]
    return out


def baseline_entry(snap: dict, state: dict) -> dict:
    n_ind = len(snap["indicators"])
    n_obs = sum(v["obs"] for v in snap["indicators"].values())
    n_ds = len(snap["datasets"])
    n_rec = sum(v["count"] for v in snap["datasets"].values())
    text = (f"Tracking {n_ind:,} indicators ({n_obs:,} values) and {n_ds:,} record datasets "
            f"({n_rec:,} records). Each weekly refresh is compared with this baseline.")
    return {"date": today(), "baseline": True,
            "items": [{"kind": "baseline", "title": "Apprentix began tracking changes",
                       "text": clip(text), "link": "pages/data.html"}],
            "counts": {"indicators": n_ind, "values": n_obs, "datasets": n_ds, "records": n_rec}}


# ---------------------------------------------------------------- build ----

def build(state: dict | None = None) -> dict | None:
    """Compare published data with the snapshot; log and re-snapshot if anything changed.
    Returns the new log entry, or None when nothing changed."""
    state = state or load_state()
    snap = fingerprint(state)
    log = read_json(LOG) if LOG.exists() else {"entries": []}
    entries = log.get("entries", [])

    if not SNAPSHOT.exists():
        entry = baseline_entry(snap, state)
    else:
        old = read_json(SNAPSHOT)
        if old.get("version") != SNAPSHOT_VERSION:
            # Format changed: re-baseline silently rather than report spurious changes.
            (OUT / "snapshot.json").write_text(dump_snapshot(snap), encoding="utf-8")
            print("Changes: snapshot format updated; no comparison this run")
            return None
        old = {"indicators": old.get("indicators", {}), "datasets": old.get("datasets", {})}
        if old == {"indicators": snap["indicators"], "datasets": snap["datasets"]}:
            print("Changes: none since the last snapshot")
            return None
        items, counts = diff(old, snap, state)
        if not items:
            SNAPSHOT.write_text(dump_snapshot(snap), encoding="utf-8")
            print("Changes: snapshot updated (nothing reportable)")
            return None
        entry = {"date": today(), "items": [public(it) for it in items], "counts": counts}

    # Two builds on one day: merge into that day's entry (the newer item wins per title).
    if entries and entries[0].get("date") == entry["date"] and not entry.get("baseline") \
            and not entries[0].get("baseline"):
        prev = entries.pop(0)
        titles = {it["title"] for it in entry["items"]}
        entry["items"] += [it for it in prev["items"] if it["title"] not in titles]
        for k, v in prev.get("counts", {}).items():
            entry["counts"][k] = entry["counts"].get(k, 0) + v
    entries = [entry] + entries
    OUT.mkdir(parents=True, exist_ok=True)
    write_json(LOG, {
        "description": "What changed in Apprentix's published data, newest first. One entry per refresh that changed something. Written by pipeline/changes.py.",
        "feed": "data/feed.xml",
        "entries": entries[:LOG_KEEP],
    })
    SNAPSHOT.write_text(dump_snapshot(snap), encoding="utf-8")
    print(f"Changes: {len(entry['items'])} item(s) logged for {entry['date']}")
    return entry


if __name__ == "__main__":
    e = build()
    if e and "--print" in sys.argv:
        print(json.dumps(e, ensure_ascii=False, indent=2))
