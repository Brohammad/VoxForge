"""Tests for public landing and demo static pages."""

import pytest


@pytest.mark.asyncio
async def test_landing_page(test_client):
    response = await test_client.get("/")
    assert response.status_code == 200
    assert "VoxForge" in response.text
    assert "Voice AI Infrastructure" in response.text


@pytest.mark.asyncio
async def test_demo_page(test_client):
    response = await test_client.get("/demo")
    assert response.status_code == 200
    assert "Interactive Voice Pipeline Demo" in response.text


@pytest.mark.asyncio
async def test_status_page(test_client):
    response = await test_client.get("/status")
    assert response.status_code == 200
    assert "System status" in response.text
    assert "/api/v1/health" in response.text
    assert "/api/v1/ready" in response.text
    css = await test_client.get("/public/status/styles.css")
    assert css.status_code == 200
    js = await test_client.get("/public/status/app.js")
    assert js.status_code == 200


@pytest.mark.asyncio
async def test_landing_static_assets(test_client):
    response = await test_client.get("/public/landing/styles.css")
    assert response.status_code == 200
    assert "color-scheme" in response.text
