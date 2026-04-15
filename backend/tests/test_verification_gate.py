"""The Phase 3 hard block: unverified accounts cannot reach core features.

`get_verified_user` is a single choke point, so the risk is not that one route
checks incorrectly — it is that a route forgets to depend on it at all. The
last test in this file therefore asserts on the dependency graph of the live
app rather than on any one endpoint, so a newly added route that skips the gate
fails the suite instead of shipping open.
"""

import io

from conftest import MOCK_CARDS, register_and_verify, register_user, verify_user

from backend.dependencies import EMAIL_VERIFICATION_REQUIRED, get_verified_user


def unverified_headers(client, email="gate@example.com"):
    resp = register_user(client, email=email, name="Gate")
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    client.cookies.clear()
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Blocked while unverified
# ---------------------------------------------------------------------------

def test_core_endpoints_are_blocked_for_unverified_users(client):
    headers = unverified_headers(client)

    for method, path in [
        ("get", "/api/documents"),
        ("get", "/api/stats/me"),
        ("get", "/api/quiz/history"),
        ("get", "/api/interactions/me"),
    ]:
        resp = getattr(client, method)(path, headers=headers)
        assert resp.status_code == 403, f"{method.upper()} {path} was not gated"


def test_upload_is_blocked_for_unverified_users(client, minimal_pdf):
    headers = unverified_headers(client)
    resp = client.post(
        "/api/documents/upload",
        files={"file": ("notes.pdf", io.BytesIO(minimal_pdf), "application/pdf")},
        headers=headers,
    )
    assert resp.status_code == 403


def test_block_response_is_machine_readable(client):
    """The frontend switches on this code to render the interstitial."""
    headers = unverified_headers(client)
    resp = client.get("/api/documents", headers=headers)

    detail = resp.json()["detail"]
    assert detail["code"] == EMAIL_VERIFICATION_REQUIRED
    assert detail["email"] == "gate@example.com"
    assert detail["message"]


def test_block_is_403_not_401(client):
    """401 would send the SPA into its refresh-and-retry loop forever."""
    headers = unverified_headers(client)
    assert client.get("/api/documents", headers=headers).status_code == 403


def test_gate_also_applies_to_the_session_cookie_path(client):
    """`get_current_user` prefers the session cookie; the gate must still bite."""
    register_user(client, email="cookie@example.com", name="Cookie")
    # No Authorization header at all — resolved purely from the session cookie.
    assert client.get("/api/documents").status_code == 403


# ---------------------------------------------------------------------------
# Allowed once verified
# ---------------------------------------------------------------------------

def test_verifying_unlocks_core_endpoints(client):
    headers = unverified_headers(client, email="unlock@example.com")
    assert client.get("/api/documents", headers=headers).status_code == 403

    token = verify_user(client, "unlock@example.com")
    client.cookies.clear()
    verified = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/documents", headers=verified).status_code == 200


def test_verified_user_can_complete_a_full_upload(client, minimal_pdf):
    from unittest.mock import AsyncMock, patch

    headers = register_and_verify(client, "full@example.com")
    with patch(
        "backend.routes.documents.generate_flashcards", new_callable=AsyncMock
    ) as mock_gen:
        mock_gen.return_value = MOCK_CARDS
        resp = client.post(
            "/api/documents/upload",
            files={"file": ("notes.pdf", io.BytesIO(minimal_pdf), "application/pdf")},
            headers=headers,
        )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Endpoints that must stay reachable while unverified
# ---------------------------------------------------------------------------

def test_auth_endpoints_stay_reachable_while_unverified(client):
    """Otherwise an unverified user could never get themselves verified."""
    headers = unverified_headers(client, email="reach@example.com")

    assert client.get("/api/auth/me", headers=headers).status_code == 200
    assert client.post(
        "/api/auth/resend-verification", json={"email": "reach@example.com"}
    ).status_code == 200
    assert client.get("/api/auth/oauth/providers").status_code == 200


# ---------------------------------------------------------------------------
# Structural: no core route may skip the gate
# ---------------------------------------------------------------------------

def test_every_non_auth_route_depends_on_the_verification_gate():
    """Guards against a future route quietly shipping ungated.

    Any new authenticated feature route — a Stripe checkout route included —
    must depend on `get_verified_user`, not `get_current_user`.
    """
    from backend.main import app

    exempt_prefixes = ("/api/auth",)
    offenders = []

    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/") or path.startswith(exempt_prefixes):
            continue
        dependant = getattr(route, "dependant", None)
        if dependant is None:
            continue
        calls = {
            d.call
            for d in _walk_dependencies(dependant)
            if getattr(d, "call", None) is not None
        }
        if get_verified_user not in calls:
            offenders.append(f"{sorted(route.methods)} {path}")

    assert offenders == [], (
        "these routes are not behind get_verified_user: " + ", ".join(offenders)
    )


def _walk_dependencies(dependant):
    yield dependant
    for sub in dependant.dependencies:
        yield from _walk_dependencies(sub)
