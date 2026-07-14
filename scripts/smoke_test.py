#!/usr/bin/env python3
"""Run body-free HTTP smoke checks and emit machine-readable evidence."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url")
    parser.add_argument(
        "--check",
        action="append",
        default=["/=200"],
        help="PATH=STATUS, repeatable",
    )
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--bearer-env", help="Read bearer token from this environment variable")
    parser.add_argument("--out")
    return parser.parse_args()


def main() -> int:
    import os

    args = parse_args()
    token = os.environ.get(args.bearer_env, "") if args.bearer_env else ""
    results = []
    failed = False
    for raw in args.check:
        path, expected_raw = raw.rsplit("=", 1)
        expected = int(expected_raw)
        url = urljoin(args.base_url.rstrip("/") + "/", path.lstrip("/"))
        headers = {"user-agent": "Port-Lovable-Smoke/1.0"}
        if token:
            headers["authorization"] = f"Bearer {token}"
        request = Request(url, method="GET", headers=headers)
        started = time.monotonic()
        status = 0
        content_type = None
        error = None
        try:
            with urlopen(request, timeout=args.timeout) as response:
                status = response.status
                content_type = response.headers.get("content-type")
        except HTTPError as exc:
            status = exc.code
            content_type = exc.headers.get("content-type") if exc.headers else None
        except URLError as exc:
            error = str(exc.reason)
        ok = status == expected and error is None
        failed = failed or not ok
        results.append(
            {
                "path": path,
                "expected_status": expected,
                "actual_status": status,
                "content_type": content_type,
                "duration_ms": round((time.monotonic() - started) * 1000),
                "ok": ok,
                "error": error,
            }
        )
    evidence = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "results": results,
        "status": "failed" if failed else "passed",
    }
    payload = json.dumps(evidence, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        out = Path(args.out).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload, encoding="utf-8")
        print(f"Wrote smoke evidence: {out}")
    else:
        print(payload, end="")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
