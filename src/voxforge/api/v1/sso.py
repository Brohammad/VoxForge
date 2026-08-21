from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from voxforge.api.dependencies import (
    get_current_principal,
    get_optional_principal,
    get_saml_connection_service,
)
from voxforge.core.domain.auth import OrgRole, Principal, TokenPair
from voxforge.core.domain.sso import (
    SamlConnection,
    SamlConnectionStatus,
    SamlLoginRedirect,
    SamlProviderType,
)
from voxforge.core.exceptions import ForbiddenError, SamlAssertionError, SamlConnectionNotFoundError
from voxforge.modules.auth.application.sso_service import SamlConnectionService

router = APIRouter(prefix="/orgs/{org_id}/sso/saml", tags=["sso"])


class SamlConnectionCreateRequest(BaseModel):
    provider_type: SamlProviderType = SamlProviderType.GENERIC
    idp_entity_id: str = Field(min_length=1, max_length=255)
    idp_sso_url: str = Field(min_length=1, max_length=512)
    idp_x509_cert: str = Field(min_length=1)
    sp_entity_id: str = Field(min_length=1, max_length=255)
    acs_url: str = Field(min_length=1, max_length=512)
    default_role: OrgRole = OrgRole.MEMBER
    role_mapping_rules: dict = Field(default_factory=dict)


class SamlConnectionUpdateRequest(BaseModel):
    status: SamlConnectionStatus
    role_mapping_rules: dict = Field(default_factory=dict)


class SamlAcsConsumeRequest(BaseModel):
    saml_response: str = Field(min_length=1)
    relay_state: str | None = None
    connection_id: UUID | None = None


class SamlAcsResponse(BaseModel):
    status: str
    user_id: str
    org_id: str
    role: str
    tokens: TokenPair


class SamlLoginResponse(BaseModel):
    status: str
    connection_id: UUID
    sso_url: str
    redirect_url: str
    relay_state: str
    binding: str
    saml_request: str

    @classmethod
    def from_entity(cls, redirect: SamlLoginRedirect) -> "SamlLoginResponse":
        return cls(
            status=redirect.status,
            connection_id=redirect.connection_id,
            sso_url=redirect.sso_url,
            redirect_url=redirect.redirect_url,
            relay_state=redirect.relay_state,
            binding=redirect.binding,
            saml_request=redirect.saml_request,
        )


class SamlConnectionResponse(BaseModel):
    id: UUID
    org_id: UUID
    provider_type: SamlProviderType
    status: SamlConnectionStatus
    idp_entity_id: str
    idp_sso_url: str
    idp_x509_cert: str
    sp_entity_id: str
    acs_url: str
    default_role: OrgRole
    role_mapping_rules: dict
    created_by_user_id: UUID | None
    updated_by_user_id: UUID | None
    created_at: str
    updated_at: str

    @classmethod
    def from_entity(cls, connection: SamlConnection) -> "SamlConnectionResponse":
        return cls(
            id=connection.id,
            org_id=connection.org_id,
            provider_type=connection.provider_type,
            status=connection.status,
            idp_entity_id=connection.idp_entity_id,
            idp_sso_url=connection.idp_sso_url,
            idp_x509_cert=connection.idp_x509_cert,
            sp_entity_id=connection.sp_entity_id,
            acs_url=connection.acs_url,
            default_role=connection.default_role,
            role_mapping_rules=connection.role_mapping_rules,
            created_by_user_id=connection.created_by_user_id,
            updated_by_user_id=connection.updated_by_user_id,
            created_at=connection.created_at.isoformat(),
            updated_at=connection.updated_at.isoformat(),
        )


@router.get("", response_model=list[SamlConnectionResponse])
async def list_saml_connections(
    org_id: UUID,
    principal: Principal = Depends(get_current_principal),
    service: SamlConnectionService = Depends(get_saml_connection_service),
) -> list[SamlConnectionResponse]:
    try:
        connections = await service.list_connections(org_id, principal)
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=exc.message) from exc
    return [SamlConnectionResponse.from_entity(connection) for connection in connections]


@router.post("", response_model=SamlConnectionResponse, status_code=201)
async def create_saml_connection(
    org_id: UUID,
    body: SamlConnectionCreateRequest,
    principal: Principal = Depends(get_current_principal),
    service: SamlConnectionService = Depends(get_saml_connection_service),
) -> SamlConnectionResponse:
    try:
        created = await service.create_connection(
            org_id=org_id,
            provider_type=body.provider_type,
            idp_entity_id=body.idp_entity_id,
            idp_sso_url=body.idp_sso_url,
            idp_x509_cert=body.idp_x509_cert,
            sp_entity_id=body.sp_entity_id,
            acs_url=body.acs_url,
            default_role=body.default_role,
            role_mapping_rules=body.role_mapping_rules,
            actor=principal,
        )
        await service.commit()
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=exc.message) from exc
    return SamlConnectionResponse.from_entity(created)


@router.patch("/{connection_id}", response_model=SamlConnectionResponse)
async def update_saml_connection(
    org_id: UUID,
    connection_id: UUID,
    body: SamlConnectionUpdateRequest,
    principal: Principal = Depends(get_current_principal),
    service: SamlConnectionService = Depends(get_saml_connection_service),
) -> SamlConnectionResponse:
    try:
        updated = await service.update_connection(
            org_id=org_id,
            connection_id=connection_id,
            status=body.status,
            role_mapping_rules=body.role_mapping_rules,
            actor=principal,
        )
        await service.commit()
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=exc.message) from exc
    except SamlConnectionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    return SamlConnectionResponse.from_entity(updated)


@router.delete("/{connection_id}", status_code=204)
async def delete_saml_connection(
    org_id: UUID,
    connection_id: UUID,
    principal: Principal = Depends(get_current_principal),
    service: SamlConnectionService = Depends(get_saml_connection_service),
) -> None:
    try:
        await service.delete_connection(org_id=org_id, connection_id=connection_id, actor=principal)
        await service.commit()
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=exc.message) from exc
    except SamlConnectionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc


@router.get("/{connection_id}/metadata")
async def get_saml_metadata(
    org_id: UUID,
    connection_id: UUID,
    principal: Principal = Depends(get_current_principal),
    service: SamlConnectionService = Depends(get_saml_connection_service),
) -> Response:
    try:
        metadata = await service.get_sp_metadata(
            org_id=org_id,
            connection_id=connection_id,
            actor=principal,
        )
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=exc.message) from exc
    except SamlConnectionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    return Response(content=metadata, media_type="application/samlmetadata+xml")


@router.get("/{connection_id}/login", response_model=SamlLoginResponse)
async def begin_saml_login(
    org_id: UUID,
    connection_id: UUID,
    principal: Principal | None = Depends(get_optional_principal),
    service: SamlConnectionService = Depends(get_saml_connection_service),
) -> SamlLoginResponse:
    """Start SP-initiated SAML login. Public when logged out (cold SSO)."""
    try:
        redirect = await service.begin_login(
            org_id=org_id,
            connection_id=connection_id,
            actor=principal,
        )
        await service.commit()
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=exc.message) from exc
    except SamlConnectionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    except SamlAssertionError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    return SamlLoginResponse.from_entity(redirect)


@router.post("/acs", response_model=SamlAcsResponse)
async def consume_saml_acs(
    org_id: UUID,
    body: SamlAcsConsumeRequest,
    service: SamlConnectionService = Depends(get_saml_connection_service),
) -> SamlAcsResponse:
    try:
        result = await service.consume_acs(
            org_id=org_id,
            saml_response=body.saml_response,
            relay_state=body.relay_state,
            connection_id=body.connection_id,
        )
        await service.commit()
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=exc.message) from exc
    except SamlAssertionError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    return SamlAcsResponse(**result)
