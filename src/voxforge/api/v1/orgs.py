import csv
import io
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from voxforge.api.dependencies import (
    get_auth_service,
    get_current_principal,
    get_invite_email_sender,
    require_scope,
)
from voxforge.config import Settings, get_settings
from voxforge.core.domain.auth import Organization, OrgRole, Principal
from voxforge.core.exceptions import (
    ForbiddenError,
    InvalidCredentialsError,
    OrganizationNotFoundError,
)
from voxforge.infrastructure.db.session import get_db_session
from voxforge.infrastructure.email.invite_mailer import InviteEmailPayload, InviteEmailSender
from voxforge.modules.auth.application.service import AuthService

router = APIRouter(prefix="/orgs", tags=["organizations"])


class CreateOrgRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class OrgResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    created_at: str

    @classmethod
    def from_entity(cls, org: Organization) -> "OrgResponse":
        return cls(
            id=org.id,
            name=org.name,
            slug=org.slug,
            created_at=org.created_at.isoformat(),
        )


class AddMemberRequest(BaseModel):
    user_id: UUID
    role: OrgRole = OrgRole.MEMBER


class CreateInviteRequest(BaseModel):
    email: EmailStr
    role: OrgRole = OrgRole.MEMBER


class InviteResponse(BaseModel):
    id: UUID
    org_id: UUID
    email: str
    role: str
    expires_at: str
    accept_url: str
    token: str | None = None
    email_sent: bool = False


class MemberResponse(BaseModel):
    id: UUID
    org_id: UUID
    user_id: UUID
    role: str
    created_at: str


class AuditLogResponse(BaseModel):
    id: str
    org_id: str | None
    user_id: str | None
    action: str
    resource_type: str
    resource_id: str | None
    metadata: dict
    created_at: str


@router.post("", response_model=OrgResponse, status_code=201)
async def create_org(
    body: CreateOrgRequest,
    principal: Principal = Depends(require_scope("orgs:write")),
    auth_service: AuthService = Depends(get_auth_service),
    db: AsyncSession = Depends(get_db_session),
) -> OrgResponse:
    if principal.user_id is None:
        raise HTTPException(status_code=400, detail="API keys cannot create organizations")
    org = await auth_service.create_org(name=body.name, user_id=principal.user_id)
    await auth_service.commit()
    return OrgResponse.from_entity(org)


@router.get("", response_model=list[OrgResponse])
async def list_orgs(
    principal: Principal = Depends(require_scope("orgs:read")),
    auth_service: AuthService = Depends(get_auth_service),
) -> list[OrgResponse]:
    if principal.user_id is None:
        raise HTTPException(status_code=400, detail="API keys cannot list organizations")
    orgs = await auth_service.list_orgs(principal.user_id)
    return [OrgResponse.from_entity(o) for o in orgs]


@router.get("/{org_id}", response_model=OrgResponse)
async def get_org(
    org_id: UUID,
    principal: Principal = Depends(require_scope("orgs:read")),
    auth_service: AuthService = Depends(get_auth_service),
) -> OrgResponse:
    if principal.org_id != org_id:
        raise HTTPException(status_code=403, detail="Access denied for this organization")
    try:
        org = await auth_service.get_org(org_id)
    except OrganizationNotFoundError:
        raise HTTPException(status_code=404, detail="Organization not found") from None
    return OrgResponse.from_entity(org)


@router.get("/{org_id}/members", response_model=list[MemberResponse])
async def list_members(
    org_id: UUID,
    principal: Principal = Depends(get_current_principal),
    auth_service: AuthService = Depends(get_auth_service),
) -> list[MemberResponse]:
    try:
        members = await auth_service.list_members(org_id, principal)
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=exc.message) from exc
    return [
        MemberResponse(
            id=m.id,
            org_id=m.org_id,
            user_id=m.user_id,
            role=m.role.value,
            created_at=m.created_at.isoformat(),
        )
        for m in members
    ]


@router.post("/{org_id}/members", response_model=MemberResponse, status_code=201)
async def add_member(
    org_id: UUID,
    body: AddMemberRequest,
    principal: Principal = Depends(get_current_principal),
    auth_service: AuthService = Depends(get_auth_service),
    db: AsyncSession = Depends(get_db_session),
) -> MemberResponse:
    try:
        member = await auth_service.add_member(
            org_id=org_id, user_id=body.user_id, role=body.role, actor=principal
        )
        await auth_service.commit()
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=exc.message) from exc
    return MemberResponse(
        id=member.id,
        org_id=member.org_id,
        user_id=member.user_id,
        role=member.role.value,
        created_at=member.created_at.isoformat(),
    )


@router.post("/{org_id}/invites", response_model=InviteResponse, status_code=201)
async def create_invite(
    org_id: UUID,
    body: CreateInviteRequest,
    principal: Principal = Depends(get_current_principal),
    auth_service: AuthService = Depends(get_auth_service),
    mailer: InviteEmailSender = Depends(get_invite_email_sender),
    settings: Settings = Depends(get_settings),
    db: AsyncSession = Depends(get_db_session),
) -> InviteResponse:
    try:
        org = await auth_service.get_org(org_id)
        invite, raw_token, accept_url = await auth_service.create_invite(
            org_id=org_id,
            email=str(body.email),
            role=body.role,
            actor=principal,
        )
        await auth_service.commit()
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=exc.message) from exc
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    except OrganizationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc

    email_sent = await mailer.send_invite(
        InviteEmailPayload(
            to_email=invite.email,
            org_name=org.name,
            accept_url=accept_url,
            role=invite.role,
            expires_hours=settings.invite_ttl_hours,
        )
    )
    expose_token = not email_sent and settings.app_env != "production"
    return InviteResponse(
        id=invite.id,
        org_id=invite.org_id,
        email=invite.email,
        role=invite.role,
        expires_at=invite.expires_at.isoformat(),
        accept_url=accept_url,
        token=raw_token if expose_token else None,
        email_sent=email_sent,
    )


@router.get("/{org_id}/audit-logs", response_model=list[AuditLogResponse])
async def list_audit_logs(
    org_id: UUID,
    limit: int = Query(500, ge=1, le=2000),
    principal: Principal = Depends(get_current_principal),
    auth_service: AuthService = Depends(get_auth_service),
) -> list[AuditLogResponse]:
    try:
        records = await auth_service.list_audit_logs(org_id, principal, limit=limit)
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=exc.message) from exc
    return [AuditLogResponse(**record) for record in records]


@router.get("/{org_id}/audit-logs/export")
async def export_audit_logs(
    org_id: UUID,
    format: str = Query("csv", pattern="^(csv|json)$"),
    limit: int = Query(500, ge=1, le=2000),
    principal: Principal = Depends(get_current_principal),
    auth_service: AuthService = Depends(get_auth_service),
) -> Response:
    try:
        records = await auth_service.list_audit_logs(org_id, principal, limit=limit)
    except ForbiddenError as exc:
        raise HTTPException(status_code=403, detail=exc.message) from exc

    if format == "json":
        return Response(
            content=json.dumps(records),
            media_type="application/json",
        )

    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=[
            "id",
            "org_id",
            "user_id",
            "action",
            "resource_type",
            "resource_id",
            "metadata",
            "created_at",
        ],
    )
    writer.writeheader()
    for row in records:
        writer.writerow(
            {
                **row,
                "metadata": str(row.get("metadata", {})),
            }
        )
    return Response(content=buffer.getvalue(), media_type="text/csv")
