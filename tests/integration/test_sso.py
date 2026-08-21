import base64

import pytest
from lxml import etree

from tests.helpers.saml_fixtures import build_signed_saml_response, generate_idp_key_and_cert

DS_NS = "http://www.w3.org/2000/09/xmldsig#"


def _strip_signatures(signed_response: str) -> str:
    root = etree.fromstring(base64.b64decode(signed_response))
    for signature in root.findall(f".//{{{DS_NS}}}Signature"):
        parent = signature.getparent()
        if parent is not None:
            parent.remove(signature)
    return base64.b64encode(etree.tostring(root)).decode("utf-8")


async def _register_user(auth_client, email: str, org_name: str) -> tuple[str, str]:
    response = await auth_client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "securepass123",
            "full_name": email.split("@")[0].title(),
            "org_name": org_name,
        },
    )
    assert response.status_code == 201
    payload = response.json()
    return payload["tokens"]["access_token"], payload["org_id"]


@pytest.mark.asyncio
async def test_saml_connection_crud_scaffold(auth_client):
    sp_entity_id = "voxforge-sp"
    cert_pem, signed_response = build_signed_saml_response(sp_entity_id=sp_entity_id)

    token, org_id = await _register_user(auth_client, "sso-owner@example.com", "SSO Org")
    headers = {"Authorization": f"Bearer {token}"}

    create_resp = await auth_client.post(
        f"/api/v1/orgs/{org_id}/sso/saml",
        headers=headers,
        json={
            "provider_type": "okta",
            "idp_entity_id": "http://idp.example.com/metadata",
            "idp_sso_url": "https://idp.example.com/sso",
            "idp_x509_cert": cert_pem,
            "sp_entity_id": sp_entity_id,
            "acs_url": "https://voxforge.example.com/api/v1/orgs/abc/sso/saml/acs",
            "default_role": "member",
            "role_mapping_rules": {"admin_group": "admin"},
        },
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["status"] == "draft"
    assert created["provider_type"] == "okta"
    connection_id = created["id"]

    list_resp = await auth_client.get(f"/api/v1/orgs/{org_id}/sso/saml", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    update_resp = await auth_client.patch(
        f"/api/v1/orgs/{org_id}/sso/saml/{connection_id}",
        headers=headers,
        json={"status": "active", "role_mapping_rules": {"support_admins": "admin"}},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["status"] == "active"

    begin_login_resp = await auth_client.get(
        f"/api/v1/orgs/{org_id}/sso/saml/{connection_id}/login",
        headers=headers,
    )
    assert begin_login_resp.status_code == 200
    begin_payload = begin_login_resp.json()
    assert begin_payload["status"] == "redirect"
    assert begin_payload["connection_id"] == connection_id
    assert begin_payload["redirect_url"].startswith("https://idp.example.com/sso")
    assert "SAMLRequest=" in begin_payload["redirect_url"]
    assert begin_payload["binding"] == "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
    assert begin_payload["saml_request"]
    assert begin_payload["relay_state"] == f"org:{org_id}:connection:{connection_id}"

    public_login_resp = await auth_client.get(
        f"/api/v1/orgs/{org_id}/sso/saml/{connection_id}/login",
    )
    assert public_login_resp.status_code == 200
    assert public_login_resp.json()["connection_id"] == connection_id

    metadata_resp = await auth_client.get(
        f"/api/v1/orgs/{org_id}/sso/saml/{connection_id}/metadata",
        headers=headers,
    )
    assert metadata_resp.status_code == 200
    assert "EntityDescriptor" in metadata_resp.text

    acs_resp = await auth_client.post(
        f"/api/v1/orgs/{org_id}/sso/saml/acs",
        json={
            "saml_response": signed_response,
            "relay_state": f"org:{org_id}:connection:{connection_id}",
        },
    )
    assert acs_resp.status_code == 200
    acs_payload = acs_resp.json()
    assert acs_payload["status"] == "authenticated"
    assert acs_payload["role"] == "admin"
    assert acs_payload["tokens"]["access_token"]

    delete_resp = await auth_client.delete(
        f"/api/v1/orgs/{org_id}/sso/saml/{connection_id}",
        headers=headers,
    )
    assert delete_resp.status_code == 204

    list_after_delete = await auth_client.get(f"/api/v1/orgs/{org_id}/sso/saml", headers=headers)
    assert list_after_delete.status_code == 200
    assert list_after_delete.json() == []


@pytest.mark.asyncio
async def test_saml_acs_rejects_unsigned_response(auth_client):
    sp_entity_id = "voxforge-sp"
    cert_pem, signed_response = build_signed_saml_response(sp_entity_id=sp_entity_id)
    unsigned_response = _strip_signatures(signed_response)

    token, org_id = await _register_user(auth_client, "sso-unsigned@example.com", "Unsigned Org")
    headers = {"Authorization": f"Bearer {token}"}

    create_resp = await auth_client.post(
        f"/api/v1/orgs/{org_id}/sso/saml",
        headers=headers,
        json={
            "provider_type": "okta",
            "idp_entity_id": "http://idp.example.com/metadata",
            "idp_sso_url": "https://idp.example.com/sso",
            "idp_x509_cert": cert_pem,
            "sp_entity_id": sp_entity_id,
            "acs_url": "https://voxforge.example.com/acs",
            "default_role": "member",
        },
    )
    connection_id = create_resp.json()["id"]
    await auth_client.patch(
        f"/api/v1/orgs/{org_id}/sso/saml/{connection_id}",
        headers=headers,
        json={"status": "active", "role_mapping_rules": {}},
    )

    acs_resp = await auth_client.post(
        f"/api/v1/orgs/{org_id}/sso/saml/acs",
        json={
            "saml_response": unsigned_response,
            "relay_state": f"org:{org_id}:connection:{connection_id}",
        },
    )
    assert acs_resp.status_code == 400
    assert "signature" in acs_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_saml_connection_org_scope_protected(auth_client):
    token_one, org_one = await _register_user(auth_client, "sso-tenant1@example.com", "Org One")
    token_two, _ = await _register_user(auth_client, "sso-tenant2@example.com", "Org Two")
    headers_one = {"Authorization": f"Bearer {token_one}"}
    headers_two = {"Authorization": f"Bearer {token_two}"}

    create_resp = await auth_client.post(
        f"/api/v1/orgs/{org_one}/sso/saml",
        headers=headers_one,
        json={
            "provider_type": "generic",
            "idp_entity_id": "idp-org-one",
            "idp_sso_url": "https://org-one.example.com/sso",
            "idp_x509_cert": generate_idp_key_and_cert()[1],
            "sp_entity_id": "voxforge-org-one",
            "acs_url": "https://voxforge.example.com/api/v1/orgs/org-one/sso/saml/acs",
            "default_role": "member",
        },
    )
    assert create_resp.status_code == 201

    forbidden_list = await auth_client.get(f"/api/v1/orgs/{org_one}/sso/saml", headers=headers_two)
    assert forbidden_list.status_code == 403
