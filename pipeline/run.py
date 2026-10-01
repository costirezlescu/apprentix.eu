"""Run the Apprentix data pipeline.

  python -m pipeline.run                 run every connector, then build
  python -m pipeline.run eurostat        run selected connectors, then build
  python -m pipeline.run --list          list connectors
  python -m pipeline.run --build-only    only rebuild indexes, catalogue and datapackage

Connectors whose SOURCE has "permission_needed" are skipped: their publisher's
terms do not allow republishing without consent. Once consent is given, remove
that key (or set APPRENTIX_ALLOW_<ID>=1 for a local test run).

A connector that fails does not stop the others; the run exits non-zero at the
end so CI notices, and the failure is recorded in data/sources.json.
"""

from __future__ import annotations

import os
import sys
import traceback

from . import build
from .common import now_iso
from .sources import discover


def main(argv: list[str]) -> int:
    connectors = discover()
    if "--list" in argv:
        for sid, m in connectors.items():
            s = m.SOURCE
            secret = f"  [needs {s['secret']}]" if s.get("secret") else ""
            print(f"{sid:24} {s['access']:6} {s['name']}{secret}")
        return 0

    status = {}
    if "--build-only" not in argv:
        wanted = [a for a in argv if not a.startswith("-")] or list(connectors)
        unknown = [w for w in wanted if w not in connectors]
        if unknown:
            print(f"Unknown connector(s): {', '.join(unknown)}. Try --list.")
            return 2
        for sid in wanted:
            m = connectors[sid]
            blocked = m.SOURCE.get("permission_needed")
            allow = os.environ.get("APPRENTIX_ALLOW_" + sid.upper().replace("-", "_"))
            if blocked and not allow:
                print(f"- {sid}: skipped (awaiting permission from the publisher)")
                status[sid] = {"last_run": now_iso(), "result": "awaiting-permission", "detail": blocked}
                continue
            secret = m.SOURCE.get("secret")
            if secret and not os.environ.get(secret):
                print(f"- {sid}: skipped (set {secret} to enable)")
                status[sid] = {"last_run": now_iso(), "result": "skipped", "detail": f"needs {secret}"}
                continue
            print(f"- {sid}: running")
            try:
                written = m.run() or []
                print(f"  wrote {len(written)} file(s)")
                status[sid] = {"last_run": now_iso(), "result": "ok", "outputs": sorted(written)}
            except Exception as e:  # keep going; report at the end
                traceback.print_exc()
                status[sid] = {"last_run": now_iso(), "result": "error", "detail": str(e)[:300]}

    build.all(connectors, status)
    failed = [k for k, v in status.items() if v["result"] == "error"]
    if failed:
        print(f"\nFailed: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
