"""Serving the built React bundle from the API.

`frontend/dist` is a build artefact and is not in a checkout, so these build a
throwaway bundle in a tmp directory and mount it on a bare app. Testing against
the real path would skip everywhere except a machine that had just run
`npm run build` — which is not where this regresses.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.main import mount_frontend

INDEX = "<!doctype html><title>Marigold</title>"


@pytest.fixture
def client(tmp_path):
    """A bare app serving a minimal bundle: index.html, an asset, a root file."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX)
    (dist / "assets" / "index-abc123.js").write_text("console.log(1)")
    (dist / "favicon.ico").write_bytes(b"\x00")

    app = FastAPI()

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.get("/api/things")
    def things():
        return {"things": []}

    assert mount_frontend(app, str(dist))
    return TestClient(app)


def test_root_serves_the_bundle(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.text == INDEX


@pytest.mark.parametrize("path", ["/dashboard", "/deck/42", "/login", "/quiz/7/results"])
def test_client_side_routes_fall_back_to_index(client, path):
    """The regression this exists for: a deep link 404ing on refresh.

    These paths have no file behind them — React Router resolves them in the
    browser — so the server has to answer with the shell rather than a 404.
    """
    response = client.get(path)

    assert response.status_code == 200
    assert response.text == INDEX


def test_real_files_are_served_as_themselves(client):
    """The fallback must not swallow files that do exist."""
    assert client.get("/favicon.ico").content == b"\x00"
    assert client.get("/assets/index-abc123.js").text == "console.log(1)"


def test_a_missing_asset_is_a_404_not_the_html_shell(client):
    """A stale asset URL must fail as a 404.

    Answering it with index.html serves HTML with a JavaScript content type,
    which surfaces as a syntax error in the console and hides the real cause.
    """
    response = client.get("/assets/index-deadbeef.js")

    assert response.status_code == 404


def test_unmatched_api_paths_stay_json(client):
    """A mistyped endpoint must 404, not return the shell.

    The frontend calls `res.json()` on every response; HTML there becomes a
    parse error that says nothing about the wrong URL that caused it.
    """
    response = client.get("/api/nope")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


def test_the_api_and_health_routes_still_win(client):
    """The catch-all is registered last and must not shadow what came before."""
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/api/things").json() == {"things": []}


def test_traversal_outside_the_bundle_is_refused(client, tmp_path):
    """A path escaping dist must get the shell, never the file it points at."""
    secret = tmp_path / "secret.txt"
    secret.write_text("do not serve me")

    response = client.get("/../secret.txt")

    assert response.status_code == 200
    assert "do not serve me" not in response.text


def test_nothing_is_mounted_without_a_build(tmp_path):
    """In development the directory is absent and the app must start anyway."""
    app = FastAPI()

    assert mount_frontend(app, str(tmp_path / "does-not-exist")) is False
