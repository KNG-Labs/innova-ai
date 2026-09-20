#!/usr/bin/env python3
"""Send one typed judgment request to TypeSafe System One."""

import json
import os
import sys
import urllib.error
import urllib.request

from dotenv import load_dotenv


API_URL = "https://api.typesafe.ai/v1/systemone"


def _prepare(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError("request must be a JSON object")
    if "state" not in payload or "questions" not in payload:
        raise ValueError("request requires state and questions")
    payload.setdefault("model", "jev-latest")
    return payload


def main() -> None:
    if sys.argv[1:] == ["--self-test"]:
        assert _prepare({"state": "x", "questions": {}})["model"] == "jev-latest"
        print("ok")
        return
    if len(sys.argv) != 1:
        raise SystemExit("usage: jev.py [--self-test] < request.json")

    load_dotenv(override=True)
    api_key = os.getenv("TYPESAFE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("TYPESAFE_API_KEY is not set")

    try:
        payload = _prepare(json.load(sys.stdin))
        request = urllib.request.Request(
            API_URL,
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
    except (ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"invalid request: {error}") from error
    except urllib.error.HTTPError as error:
        body = error.read().decode(errors="replace").strip()
        raise SystemExit(f"TypeSafe HTTP {error.code}: {body}") from error
    except urllib.error.URLError as error:
        raise SystemExit(f"TypeSafe request failed: {error.reason}") from error

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
