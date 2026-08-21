from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from voxforge.config import Settings
from voxforge.core.domain.auth import (
    ALL_API_KEY_SCOPES,
    ApiKey,
    LoginRequest,
    Organization,
    OrganizationMember,
    OrgRole,
    Principal,
    RegisterRequest,
    TokenPair,
    User,
)
from voxforge.core.exceptions import (
    ForbiddenError,
    InvalidCredentialsError,
    OrganizationNotFoundError,
    UnauthorizedError,
)
from voxforge.infrastructure.db.auth_repositories import (
    ApiKeyRepository,
    AuditLogRepository,
    OrganizationInviteRepository,
    OrganizationMemberRepository,
    OrganizationRepository,
    UserRepository,
)
from voxforge.infrastructure.db.models import UserModel
from voxforge.infrastructure.observability.logging import get_logger
from voxforge.infrastructure.security.tokens import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    principal_from_access_token,
    principal_from_api_key_record,
    verify_password,
)

logger = get_logger(__name__)


class AuthService:
    def __init__(self, db_session: AsyncSession, settings: Settings) -> None:
        self._db = db_session
        self._settings = settings
        self._users = UserRepository(db_session)
        self._orgs = OrganizationRepository(db_session)
        self._members = OrganizationMemberRepository(db_session)
        self._invites = OrganizationInviteRepository(db_session)
        self._api_keys = ApiKeyRepository(db_session)
        self._audit = AuditLogRepository(db_session)

    async def register(self, request: RegisterRequest) -> tuple[User, Organization, TokenPair]:
        existing = await self._users.get_by_email(request.email)
        if existing:
            raise InvalidCredentialsError("Email already registered")

        user = await self._users.create(
            email=request.email,
            hashed_password=hash_password(request.password),
            full_name=request.full_name,
        )
        org = await self._orgs.create(name=request.org_name)
        await self._members.add_member(org_id=org.id, user_id=user.id, role=OrgRole.OWNER)
        await self._audit.log(
            action="user.registered",
            resource_type="user",
            org_id=org.id,
            user_id=user.id,
            resource_id=str(user.id),
        )
        tokens = self._issue_tokens(user_id=user.id, org_id=org.id, role=OrgRole.OWNER)
        return user, org, tokens

    async def login(self, request: LoginRequest, *, org_id: UUID | None = None) -> TokenPair:
        user_model = await self._users.get_by_email(request.email)
        if user_model is None:
            raise InvalidCredentialsError()

        stored = await self._db.get(UserModel, user_model.id)
        if stored is None or not verify_password(request.password, stored.hashed_password):
            raise InvalidCredentialsError()
        if not user_model.is_active:
            raise UnauthorizedError("Account is inactive")

        membership = await self._resolve_membership(user_model.id, org_id)
        tokens = self._issue_tokens(
            user_id=user_model.id, org_id=membership.org_id, role=membership.role
        )
        await self._audit.log(
            action="user.login",
            resource_type="user",
            org_id=membership.org_id,
            user_id=user_model.id,
        )
        return tokens

    async def refresh(self, refresh_token: str) -> TokenPair:
        payload = decode_token(refresh_token, self._settings)
        if payload.get("type") != "refresh":
            raise UnauthorizedError("Invalid token type")
        user_id = UUID(payload["sub"])
        org_id = UUID(payload["org_id"])
        membership = await self._members.get_membership(org_id=org_id, user_id=user_id)
        if membership is None:
            raise UnauthorizedError("Organization membership not found")
        return self._issue_tokens(user_id=user_id, org_id=org_id, role=membership.role)

    async def resolve_principal_from_bearer(self, token: str) -> Principal:
        return principal_from_access_token(token, self._settings)

    async def resolve_principal_from_api_key(self, raw_key: str) -> Principal:
        if not raw_key.startswith(self._settings.api_key_prefix):
            raise UnauthorizedError("Invalid API key format")

        key_prefix = raw_key[:12]
        key_hash = hash_api_key(raw_key, self._settings.api_key_hash_pepper)
        candidates = await self._api_keys.find_by_prefix(key_prefix)

        for candidate in candidates:
            if candidate.key_hash != key_hash:
                continue
            if candidate.revoked_at is not None:
                raise UnauthorizedError("API key revoked")
            if candidate.expires_at and candidate.expires_at < datetime.now(UTC):
                raise UnauthorizedError("API key expired")
            return principal_from_api_key_record(
                api_key_id=candidate.id,
                org_id=candidate.org_id,
                scopes=candidate.scopes or [],
            )

        raise UnauthorizedError("Invalid API key")

    async def get_user(self, user_id: UUID) -> User:
        return await self._users.get(user_id)

    async def create_org(self, *, name: str, user_id: UUID) -> Organization:
        org = await self._orgs.create(name=name)
        await self._members.add_member(org_id=org.id, user_id=user_id, role=OrgRole.OWNER)
        await self._audit.log(
            action="org.created",
            resource_type="organization",
            org_id=org.id,
            user_id=user_id,
            resource_id=str(org.id),
        )
        return org

    async def list_orgs(self, user_id: UUID) -> list[Organization]:
        return await self._orgs.list_for_user(user_id)

    async def get_org(self, org_id: UUID) -> Organization:
        return await self._orgs.get(org_id)

    async def add_member(
        self, *, org_id: UUID, user_id: UUID, role: OrgRole, actor: Principal
    ) -> OrganizationMember:
        self._require_scope(actor, "orgs:manage_members", org_id)
        return await self._members.add_member(org_id=org_id, user_id=user_id, role=role)

    async def create_invite(
        self, *, org_id: UUID, email: str, role: OrgRole, actor: Principal
    ) -> tuple[object, str, str]:
        """Create (or refresh) an org invite. Returns invite model, raw token, accept URL."""
        self._require_scope(actor, "orgs:manage_members", org_id)
        normalized = email.lower().strip()
        if not normalized or "@" not in normalized:
            raise InvalidCredentialsError("Invalid invite email")

        raw_token = token_urlsafe(32)
        token_hash = sha256(raw_token.encode("utf-8")).hexdigest()
        expires_at = datetime.now(UTC) + timedelta(hours=self._settings.invite_ttl_hours)
        invite = await self._invites.create(
            org_id=org_id,
            email=normalized,
            role=role,
            token_hash=token_hash,
            invited_by_user_id=actor.user_id,
            expires_at=expires_at,
        )
        base = self._settings.public_base_url.rstrip("/") or "http://localhost:8000"
        accept_url = f"{base}/dashboard?invite={raw_token}"
        await self._audit.log(
            action="org.member_invited",
            resource_type="organization_invite",
            org_id=org_id,
            user_id=actor.user_id,
            resource_id=str(invite.id),
            metadata={"email": normalized, "role": role.value},
        )
        logger.info(
            "org_invite_created",
            org_id=str(org_id),
            email=normalized,
            accept_url=accept_url,
        )
        return invite, raw_token, accept_url

    async def accept_invite(
        self, *, token: str, password: str, full_name: str
    ) -> tuple[User, UUID, TokenPair]:
        token_hash = sha256(token.encode("utf-8")).hexdigest()
        invite = await self._invites.get_by_token_hash(token_hash)
        if invite is None or invite.accepted_at is not None:
            raise InvalidCredentialsError("Invalid or already used invite")
        expires_at = invite.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at < datetime.now(UTC):
            raise InvalidCredentialsError("Invite has expired")

        role = OrgRole(invite.role)
        existing = await self._users.get_by_email(invite.email)
        if existing is None:
            user = await self._users.create(
                email=invite.email,
                hashed_password=hash_password(password),
                full_name=full_name,
            )
        else:
            user = existing
            stored = await self._db.get(UserModel, user.id)
            if stored is not None and not verify_password(password, stored.hashed_password):
                raise InvalidCredentialsError("Password does not match existing account")

        await self._members.upsert_member(org_id=invite.org_id, user_id=user.id, role=role)
        await self._invites.mark_accepted(invite)
        await self._audit.log(
            action="org.invite_accepted",
            resource_type="organization_invite",
            org_id=invite.org_id,
            user_id=user.id,
            resource_id=str(invite.id),
        )
        tokens = self._issue_tokens(user_id=user.id, org_id=invite.org_id, role=role)
        return user, invite.org_id, tokens

    async def list_members(self, org_id: UUID, actor: Principal) -> list[OrganizationMember]:
        self._require_scope(actor, "orgs:read", org_id)
        return await self._members.list_members(org_id)

    async def create_api_key(
        self,
        *,
        org_id: UUID,
        name: str,
        scopes: list[str],
        actor: Principal,
        expires_at: datetime | None = None,
    ) -> tuple[ApiKey, str]:
        self._require_scope(actor, "api_keys:write", org_id)
        invalid_scopes = sorted(set(scopes) - ALL_API_KEY_SCOPES)
        if invalid_scopes:
            raise ForbiddenError(f"Invalid API key scopes: {', '.join(invalid_scopes)}")
        for scope in scopes:
            if not actor.has_scope(scope):
                raise ForbiddenError(f"Cannot grant scope you do not have: {scope}")
        raw_key, key_prefix, key_hash = generate_api_key(
            self._settings.api_key_prefix, self._settings.api_key_hash_pepper
        )
        api_key = await self._api_keys.create(
            org_id=org_id,
            name=name,
            key_prefix=key_prefix,
            key_hash=key_hash,
            scopes=scopes,
            created_by_user_id=actor.user_id,
            expires_at=expires_at,
        )
        await self._audit.log(
            action="api_key.created",
            resource_type="api_key",
            org_id=org_id,
            user_id=actor.user_id,
            resource_id=str(api_key.id),
        )
        return api_key, raw_key

    async def list_api_keys(self, org_id: UUID, actor: Principal) -> list[ApiKey]:
        self._require_scope(actor, "api_keys:read", org_id)
        return await self._api_keys.list_for_org(org_id)

    async def revoke_api_key(self, key_id: UUID, actor: Principal) -> ApiKey:
        key = await self._api_keys.get(key_id)
        self._require_scope(actor, "api_keys:delete", key.org_id)
        revoked = await self._api_keys.revoke(key_id)
        await self._audit.log(
            action="api_key.revoked",
            resource_type="api_key",
            org_id=key.org_id,
            user_id=actor.user_id,
            resource_id=str(key_id),
        )
        return revoked

    async def list_audit_logs(
        self, org_id: UUID, actor: Principal, *, limit: int = 500
    ) -> list[dict]:
        self._require_scope(actor, "orgs:read", org_id)
        records = await self._audit.list_for_org(org_id, limit=limit)
        return [
            {
                "id": str(record.id),
                "org_id": str(record.org_id) if record.org_id else None,
                "user_id": str(record.user_id) if record.user_id else None,
                "action": record.action,
                "resource_type": record.resource_type,
                "resource_id": record.resource_id,
                "metadata": record.metadata_ or {},
                "created_at": record.created_at.isoformat(),
            }
            for record in records
        ]

    async def commit(self) -> None:
        await self._db.commit()

    def _issue_tokens(self, *, user_id: UUID, org_id: UUID, role: OrgRole) -> TokenPair:
        access = create_access_token(
            user_id=user_id, org_id=org_id, role=role, settings=self._settings
        )
        refresh = create_refresh_token(user_id=user_id, org_id=org_id, settings=self._settings)
        return TokenPair(
            access_token=access,
            refresh_token=refresh,
            expires_in=self._settings.jwt_access_token_expire_minutes * 60,
        )

    async def _resolve_membership(self, user_id: UUID, org_id: UUID | None) -> OrganizationMember:
        if org_id:
            membership = await self._members.get_membership(org_id=org_id, user_id=user_id)
            if membership is None:
                raise OrganizationNotFoundError(str(org_id))
            return membership

        orgs = await self._orgs.list_for_user(user_id)
        if not orgs:
            raise OrganizationNotFoundError("no organizations")
        membership = await self._members.get_membership(org_id=orgs[0].id, user_id=user_id)
        if membership is None:
            raise OrganizationNotFoundError(str(orgs[0].id))
        return membership

    @staticmethod
    def _require_scope(actor: Principal, scope: str, org_id: UUID) -> None:
        if actor.org_id != org_id:
            raise ForbiddenError("Access denied for this organization")
        if not actor.has_scope(scope):
            raise ForbiddenError(f"Missing required scope: {scope}")

    @staticmethod
    def require_scope(actor: Principal, scope: str) -> None:
        if not actor.has_scope(scope):
            raise ForbiddenError(f"Missing required scope: {scope}")
