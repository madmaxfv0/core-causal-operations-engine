"""Protections for running CORE on a public link.

CORE has no user accounts: it was built to run on one machine, so every
endpoint is open and several of them are destructive. On a public link that
means any visitor could wipe the evidence base (/api/demo/reset), start an
hours-long rebuild, ingest files, switch the whole data context for everyone,
or upload documents. Nothing here changes behaviour on a local run.

Two independent switches, both read from the environment:

CORE_PUBLIC_DEMO=1
    Refuses the endpoints that destroy, rebuild, ingest or re-point shared
    data. Everything a visitor needs to explore - maps, wells, scenarios,
    the portfolio optimiser, the copilot, notes - still works.

CORE_ACCESS_PASSWORD=<text>
    Puts the whole app, UI and API, behind one shared password (HTTP Basic;
    any user name). Leave unset for an open link.
"""
from __future__ import annotations

import base64
import hmac
import os
import re

from fastapi.responses import JSONResponse, Response

# method, path pattern. Matched against the full request path.
_BLOCKED = [
    ("POST", r"^/api/demo/reset$"),
    ("POST", r"^/api/evidence/rebuild$"),
    ("POST", r"^/api/alberta/sync/[^/]+$"),
    ("POST", r"^/api/data/mode$"),
    ("POST", r"^/api/data/activate/[^/]+$"),
    ("POST", r"^/api/data/connectors/[^/]+/[^/]+$"),
    ("POST", r"^/api/data/import/(preview|validate|ingest|interventions)$"),
    ("POST", r"^/api/archive/upload$"),
    ("POST", r"^/api/archive/documents/[^/]+/(extract|review)$"),
]
_BLOCKED = [(m, re.compile(p)) for m, p in _BLOCKED]

MESSAGE = ("This action changes the shared data set, so it is switched off on "
           "the public demo. Everything else in CORE is available.")


def install(app) -> None:
    demo = os.environ.get("CORE_PUBLIC_DEMO", "").lower() in {"1", "true", "yes", "on"}
    password = os.environ.get("CORE_ACCESS_PASSWORD", "")

    @app.middleware("http")
    async def _public_guard(request, call_next):
        # health checks must never need credentials
        if request.url.path == "/healthz":
            return JSONResponse({"ok": True})

        if password:
            sent = ""
            header = request.headers.get("authorization", "")
            if header.lower().startswith("basic "):
                try:
                    sent = base64.b64decode(header[6:]).decode("utf-8", "ignore").split(":", 1)[-1]
                except Exception:
                    sent = ""
            if not hmac.compare_digest(sent.encode(), password.encode()):
                return Response("Password required", status_code=401,
                                headers={"WWW-Authenticate": 'Basic realm="CORE"'})

        if demo:
            for method, rx in _BLOCKED:
                if request.method == method and rx.match(request.url.path):
                    return JSONResponse({"error": MESSAGE, "demo_mode": True}, status_code=403)

        return await call_next(request)
