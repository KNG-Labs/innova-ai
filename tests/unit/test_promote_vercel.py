import json
import subprocess

import pytest

from scripts import promote_vercel


@pytest.fixture
def promotion(monkeypatch):
    monkeypatch.setenv("VERCEL_ORG_ID", "team_test")
    monkeypatch.setenv("VERCEL_PROJECT_ID", "prj_test")
    monkeypatch.setattr(promote_vercel.time, "sleep", lambda _: None)
    return {
        "id": "dpl_test",
        "projectId": "prj_test",
        "ownerId": "team_test",
        "target": "production",
        "readyState": "READY",
    }


def fake_api(monkeypatch, responses):
    calls = []
    replies = iter(responses)

    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(
            command, 0, stdout=json.dumps(next(replies)), stderr=""
        )

    monkeypatch.setattr(subprocess, "run", run)
    return calls


def test_promotes_exact_verified_build_and_waits_for_domains(monkeypatch, promotion):
    calls = fake_api(
        monkeypatch,
        [
            promotion,
            {},
            {
                "lastAliasRequest": {
                    "toDeploymentId": "dpl_other",
                    "jobStatus": "succeeded",
                }
            },
            {
                "lastAliasRequest": {
                    "toDeploymentId": "dpl_test",
                    "jobStatus": "succeeded",
                }
            },
        ],
    )
    promote_vercel.promote_deployment("https://innova.vercel.app")
    assert calls[1] == [
        "vercel",
        "api",
        "/v10/projects/prj_test/promote/dpl_test?teamId=team_test",
        "--method",
        "POST",
    ]
    assert len(calls) == 4
    assert calls[2][2] == "/v9/projects/prj_test?rollbackInfo=true&teamId=team_test"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("projectId", "prj_other"),
        ("ownerId", "team_other"),
        ("target", "preview"),
        ("readyState", "BUILDING"),
        ("id", "dpl_bad/path"),
    ],
)
def test_refuses_wrong_or_unready_deployment(monkeypatch, promotion, field, value):
    promotion[field] = value
    calls = fake_api(monkeypatch, [promotion])
    with pytest.raises(AssertionError):
        promote_vercel.promote_deployment("https://innova.vercel.app")
    assert len(calls) == 1
    assert calls[0][-1] == "GET"


def test_failed_domain_assignment_fails_release(monkeypatch, promotion):
    fake_api(
        monkeypatch,
        [
            promotion,
            {},
            {"lastAliasRequest": {"toDeploymentId": "dpl_test", "jobStatus": "failed"}},
        ],
    )
    with pytest.raises(RuntimeError, match="production domains"):
        promote_vercel.promote_deployment("https://innova.vercel.app")


def test_promotion_timeout_fails_release(monkeypatch, promotion):
    fake_api(monkeypatch, [promotion, {}])
    times = iter([0, 181])
    monkeypatch.setattr(promote_vercel.time, "monotonic", lambda: next(times))
    with pytest.raises(TimeoutError, match="180 seconds"):
        promote_vercel.promote_deployment("https://innova.vercel.app")
