"""Playwright browser tests for critical user journeys."""

from __future__ import annotations

import json
import re
import uuid

import pytest
from playwright.sync_api import Page, expect

pytestmark = [pytest.mark.browser]


def _post_json(page: Page, url: str, payload: dict, headers: dict | None = None):
    merged = {"Content-Type": "application/json", **(headers or {})}
    return page.request.post(url, data=json.dumps(payload), headers=merged)


def test_landing_page_navigation(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/")
    expect(page).to_have_title(re.compile("VoxForge"))
    expect(page.get_by_role("link", name="Try live demo")).to_be_visible()
    page.get_by_role("link", name="Run interactive demo").click()
    expect(page).to_have_url(re.compile(r"/demo$"))


def test_demo_quickstart(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/demo")
    run_btn = page.get_by_role("button", name="Run one-click sample call")
    if run_btn.is_disabled():
        pytest.skip("Demo disabled — set DEMO_ENABLED=true")
    run_btn.click()
    expect(page.locator("#out-status")).to_contain_text("demo_turn_ok", timeout=20_000)
    expect(page.locator("#results")).to_be_visible()


def test_demo_mic_control_visible(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/demo")
    if "Public demo is disabled" in page.locator("#status").inner_text():
        pytest.skip("Demo disabled — set DEMO_ENABLED=true")
    expect(page.get_by_role("button", name="Start talking")).to_be_visible()
    expect(page.get_by_text("Speak into your microphone", exact=False)).to_be_visible()


def test_dashboard_login_and_overview(page: Page, base_url: str) -> None:
    suffix = uuid.uuid4().hex[:8]
    email = f"browser-{suffix}@example.com"
    password = "securepass123"

    register = _post_json(
        page,
        f"{base_url}/api/v1/auth/register",
        {
            "email": email,
            "password": password,
            "full_name": "Browser QA",
            "org_name": f"Browser Org {suffix}",
        },
    )
    assert register.ok, register.text()

    page.goto(f"{base_url}/dashboard")
    page.locator("#login-email").fill(email)
    page.locator("#login-password").fill(password)
    page.get_by_role("button", name="Login").click()
    expect(page.locator("#auth-status")).to_contain_text("Connected", timeout=10_000)
    expect(page.locator("#overview-cards")).not_to_be_empty()


def test_knowledge_upload_and_search(page: Page, base_url: str) -> None:
    suffix = uuid.uuid4().hex[:8]
    email = f"kb-browser-{suffix}@example.com"
    password = "securepass123"
    token = (
        _post_json(
            page,
            f"{base_url}/api/v1/auth/register",
            {
                "email": email,
                "password": password,
                "full_name": "KB Browser",
                "org_name": f"KB Org {suffix}",
            },
        )
        .json()
        .get("tokens", {})
        .get("access_token")
    )
    assert token

    headers = {"Authorization": f"Bearer {token}"}
    coll = _post_json(
        page,
        f"{base_url}/api/v1/knowledge/collections",
        {"name": f"Browser KB {suffix}"},
        headers=headers,
    )
    assert coll.ok, coll.text()
    collection_id = coll.json()["id"]

    page.goto(f"{base_url}/dashboard")
    page.locator("#login-email").fill(email)
    page.locator("#login-password").fill(password)
    page.get_by_role("button", name="Login").click()
    expect(page.locator("#auth-status")).to_contain_text("Connected", timeout=10_000)

    page.locator('a[data-hub="knowledge"]').click()
    expect(page.locator("#knowledge-collection-name")).to_be_visible(timeout=5_000)

    page.locator("#knowledge-collection-name").fill(f"UI Collection {suffix}")
    page.locator("#knowledge-collection-form button[type='submit']").click()

    page.locator("#knowledge-upload-collection").select_option(collection_id)
    page.locator("#knowledge-upload-file").set_input_files(
        {
            "name": "policy.txt",
            "mimeType": "text/plain",
            "buffer": b"Our refund policy allows returns within 30 days.",
        }
    )
    page.locator("#knowledge-upload-form button[type='submit']").click()
    expect(page.locator("#knowledge-upload-status")).to_contain_text(
        re.compile("Upload|queued|document", re.I), timeout=15_000
    )

    page.locator("#knowledge-search-query").fill("refund policy")
    page.locator("#knowledge-search-form").evaluate("form => form.requestSubmit()")
    page.wait_for_timeout(2000)
    results = page.locator("#knowledge-search-results")
    expect(results).not_to_be_empty(timeout=15_000)


def test_session_replay_api_flow(page: Page, base_url: str) -> None:
    suffix = uuid.uuid4().hex[:8]
    reg = _post_json(
        page,
        f"{base_url}/api/v1/auth/register",
        {
            "email": f"replay-{suffix}@example.com",
            "password": "securepass123",
            "full_name": "Replay QA",
            "org_name": f"Replay Org {suffix}",
        },
    )
    assert reg.ok
    token = reg.json()["tokens"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    sample = page.request.post(
        f"{base_url}/api/v1/onboarding/run-sample-call",
        headers=headers,
    )
    assert sample.ok, sample.text()
    session_id = sample.json()["test_session_id"]

    replay = page.request.get(
        f"{base_url}/api/v1/sessions/{session_id}/replay",
        headers=headers,
    )
    assert replay.ok


def test_handoff_queue_api_flow(page: Page, base_url: str) -> None:
    suffix = uuid.uuid4().hex[:8]
    reg = _post_json(
        page,
        f"{base_url}/api/v1/auth/register",
        {
            "email": f"handoff-{suffix}@example.com",
            "password": "securepass123",
            "full_name": "Handoff QA",
            "org_name": f"Handoff Org {suffix}",
        },
    )
    assert reg.ok
    token = reg.json()["tokens"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    session = _post_json(
        page,
        f"{base_url}/api/v1/sessions",
        {"transport_type": "websocket", "config": {}},
        headers=headers,
    )
    assert session.ok
    session_id = session.json()["session_id"]

    handoff = _post_json(
        page,
        f"{base_url}/api/v1/sessions/{session_id}/handoff",
        {"reason": "browser test", "priority": "normal"},
        headers=headers,
    )
    assert handoff.status in (200, 201), handoff.text()

    listed = page.request.get(f"{base_url}/api/v1/handoffs", headers=headers)
    assert listed.ok
    body = listed.json()
    assert isinstance(body, list) and len(body) >= 1


def test_logout_clears_session(page: Page, base_url: str) -> None:
    suffix = uuid.uuid4().hex[:8]
    email = f"logout-{suffix}@example.com"
    _post_json(
        page,
        f"{base_url}/api/v1/auth/register",
        {
            "email": email,
            "password": "securepass123",
            "full_name": "Logout QA",
            "org_name": f"Logout Org {suffix}",
        },
    )
    page.goto(f"{base_url}/dashboard")
    page.locator("#login-email").fill(email)
    page.locator("#login-password").fill("securepass123")
    page.get_by_role("button", name="Login").click()
    expect(page.locator("#auth-status")).to_contain_text("Connected", timeout=15_000)
    expect(page.get_by_role("button", name="Logout")).to_be_visible(timeout=5_000)
    page.get_by_role("button", name="Logout").click()
    expect(page.locator("#auth-status")).to_contain_text("Not connected", timeout=10_000)


def test_404_returns_not_found(page: Page, base_url: str) -> None:
    response = page.request.get(f"{base_url}/this-route-does-not-exist")
    assert response.status == 404
