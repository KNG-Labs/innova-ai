"""Promote the verified build without CLI user-account discovery."""

import json
import os
import re
import subprocess
import sys
import time
from urllib.parse import urlsplit

from scripts.verify_vercel import _validate_origin


def promote_deployment(url: str) -> None:
    _validate_origin(url)
    team = os.environ["VERCEL_ORG_ID"]
    project = os.environ["VERCEL_PROJECT_ID"]
    assert re.fullmatch(r"team_[A-Za-z0-9]+", team), "Invalid Vercel team ID"
    assert re.fullmatch(r"prj_[A-Za-z0-9]+", project), "Invalid Vercel project ID"

    def api(path: str, method: str = "GET") -> dict:
        separator = "&" if "?" in path else "?"
        result = subprocess.run(
            ["vercel", "api", f"{path}{separator}teamId={team}", "--method", method],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return json.loads(result.stdout.strip() or "{}")

    deployment = api(f"/v13/deployments/{urlsplit(url).hostname}")
    assert deployment["projectId"] == project, "Deployment belongs to another project"
    assert deployment["ownerId"] == team, "Deployment belongs to another team"
    assert deployment["target"] == "production", "Expected a production deployment"
    assert deployment["readyState"] == "READY", "Deployment is not ready"
    deployment_id = deployment["id"]
    assert re.fullmatch(r"dpl_[A-Za-z0-9]+", deployment_id), "Invalid deployment ID"
    api(f"/v10/projects/{project}/promote/{deployment_id}", "POST")

    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        current = api(f"/v9/projects/{project}?rollbackInfo=true")
        request = current.get("lastAliasRequest") or {}
        if request.get("toDeploymentId") == deployment_id:
            if request.get("jobStatus") == "failed":
                raise RuntimeError("Vercel could not assign production domains")
            if request.get("jobStatus") == "succeeded":
                return
        time.sleep(2)
    raise TimeoutError("Vercel promotion did not finish within 180 seconds")


if __name__ == "__main__":
    promote_deployment(sys.argv[1])
    print("Verified deployment promoted to production")
