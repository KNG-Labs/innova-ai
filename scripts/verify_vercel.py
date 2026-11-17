"""Read-only release checks; vercel curl handles protected deployment access."""

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit


def _validate_origin(url: str) -> None:
    origin = urlsplit(url)
    if (
        origin.scheme != "https"
        or not (origin.hostname or "").endswith(".vercel.app")
        or origin.netloc != origin.hostname
        or origin.path not in {"", "/"}
        or origin.query
        or origin.fragment
    ):
        raise ValueError("Expected a Vercel HTTPS deployment origin")


def deployment_url(payload: dict) -> str:
    # Native CLI wraps the result; its JS fallback returns the deployment itself.
    deployment = payload.get("deployment", payload)
    if deployment["target"] != "production":
        raise ValueError("Expected a production deployment")
    value = deployment["url"]
    url = value if value.startswith("https://") else f"https://{value}"
    _validate_origin(url)
    return url


def verify_deployment(url: str) -> None:
    _validate_origin(url)
    with TemporaryDirectory() as temporary:
        body = Path(temporary) / "body"
        headers = Path(temporary) / "headers"

        def request(path: str, expected: int) -> bytes:
            result = subprocess.run(
                [
                    "vercel",
                    "curl",
                    path,
                    "--deployment",
                    url,
                    "--",
                    "--silent",
                    "--show-error",
                    "--retry",
                    "3",
                    "--retry-delay",
                    "2",
                    "--output",
                    str(body),
                    "--dump-header",
                    str(headers),
                    "--write-out",
                    "%{http_code}",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
            assert result.stdout.strip() == str(expected), (
                f"Unexpected HTTP status for {path}"
            )
            return body.read_bytes()

        assert json.loads(request("/health", 200)) == {"status": "ok"}
        request("/", 307)
        assert any(
            line.lower() == "location: /static/widget-demo.html"
            for line in headers.read_text().splitlines()
        ), "Unexpected chat redirect"
        assert b"demo.js" in request("/static/widget-demo.html", 200)
        for asset in (
            "demo.js",
            "demo-config.js",
            "demo.css",
            "fonts/MedeoSansVariable.woff2",
            "images/assistant.webp",
            "images/send.webp",
            "vendor/embla-carousel/embla-carousel-8.6.0.umd.js",
            "vendor/embla-carousel/embla-carousel-auto-scroll-8.6.0.umd.js",
        ):
            assert request(f"/static/{asset}", 200), f"Empty asset: {asset}"
        for path in (
            "/knowledge/documents",
            "/knowledge/reindex",
            "/leads",
            "/sessions/00000000-0000-0000-0000-000000000000/messages",
        ):
            request(path, 404)


if __name__ == "__main__":
    verify_deployment(sys.argv[1])
    print("Deployment checks passed")
