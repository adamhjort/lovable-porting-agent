#!/usr/bin/env python3
"""Dry-run or provision one empty Supabase project without logging credentials."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_URL = "https://api.supabase.com/v1/projects"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--organization-slug", required=True)
    parser.add_argument("--size", default="micro")
    parser.add_argument("--region", help="Optional current Supabase region identifier")
    parser.add_argument("--out", required=True, help="Write non-secret target metadata JSON")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm")
    return parser.parse_args()


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")[:63] or "lovable-app"


def main() -> int:
    args = parse_args()
    name = slugify(args.name)
    confirmation = f"CREATE-SUPABASE:{args.organization_slug}:{name}"
    safe_request = {
        "endpoint": API_URL,
        "name": name,
        "organization_slug": args.organization_slug,
        "desired_instance_size": args.size,
        "region": args.region,
        "credential_sources": ["SUPABASE_ACCESS_TOKEN", "SUPABASE_DB_PASSWORD"],
        "data": "empty",
        "confirmation_token": confirmation,
    }
    if not args.apply:
        print(json.dumps(safe_request, indent=2, ensure_ascii=False))
        print("Dry-run only. No project was created.")
        return 0
    if args.confirm != confirmation:
        print("Confirmation token mismatch.", file=sys.stderr)
        return 2

    access_token = os.environ.get("SUPABASE_ACCESS_TOKEN", "")
    db_password = os.environ.get("SUPABASE_DB_PASSWORD", "")
    if not access_token or not db_password:
        print("SUPABASE_ACCESS_TOKEN and SUPABASE_DB_PASSWORD are required in the environment.", file=sys.stderr)
        return 2

    payload = {
        "name": name,
        "organization_slug": args.organization_slug,
        "db_pass": db_password,
        "desired_instance_size": args.size,
    }
    if args.region:
        payload["region"] = args.region
    request = Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "authorization": f"Bearer {access_token}",
            "content-type": "application/json",
            "user-agent": "Port-Lovable-App/1.0",
        },
    )
    try:
        with urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        print(f"Supabase project creation failed with HTTP {exc.code}.", file=sys.stderr)
        return 1
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"Supabase project creation failed: {type(exc).__name__}", file=sys.stderr)
        return 1

    result = {
        "schema_version": 1,
        "provider": "supabase",
        "name": data.get("name") or name,
        "project_ref": data.get("ref") or data.get("id"),
        "organization_id": data.get("organization_id"),
        "organization_slug": data.get("organization_slug") or args.organization_slug,
        "status": data.get("status"),
        "source_data_copied": False,
    }
    if not result["project_ref"]:
        print("Supabase response did not contain a project ref.", file=sys.stderr)
        return 1
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Created empty Supabase project {result['project_ref']} and wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
