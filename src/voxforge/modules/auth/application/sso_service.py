import secrets
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from voxforge.config import Settings
from voxforge.core.domain.auth import OrgRole, Principal, TokenPair
from voxforge.core.domain.sso import (
    SamlConnection,
    SamlConnectionStatus,
    SamlLoginRedirect,
    SamlProviderType,
)
from voxforge.core.exceptions import ForbiddenError, SamlAssertionError
from voxforge.infrastructure.db.auth_repositories import (
    AuditLogRepository,
    OrganizationMemberRepository,
    SamlConnectionRepository,
    UserRepository,
)
from voxforge.infrastructure.security.saml import (
    build_sp_initiated_login_redirect,
    build_sp_metadata,
    parse_saml_assertion,
    resolve_role_from_mapping,
    validate_saml_response,
)
from voxforge.infrastructure.security.tokens import (
    create_access_token,
    create_refresh_token,
    hash_password,
)
from voxforge.modules.auth.application.service import AuthService


class SamlConnectionService:
    def __init__(self, db_session: AsyncSession, settings: Settings) -> None:
        self._db = db_session
        self._settings = settings
        self._repo = SamlConnectionRepository(db_session)
        self._users = UserRepository(db_session)
        self._members = OrganizationMemberRepository(db_session)
        self._audit = AuditLogRepository(db_session)

    async def list_connections(self, org_id: UUID, actor: Principal) -> list[SamlConnection]:
        self._require_org_scope(actor, org_id, "orgs:read")
        return await self._repo.list_for_org(org_id)

    async def create_connection(
        self,
        *,
        org_id: UUID,
        provider_type: SamlProviderType,
        idp_entity_id: str,
        idp_sso_url: str,
        idp_x509_cert: str,
        sp_entity_id: str,
        acs_url: str,
        default_role: OrgRole,
        role_mapping_rules: dict,
        actor: Principal,
    ) -> SamlConnection:
        self._require_org_scope(actor, org_id, "orgs:write")
        connection = await self._repo.create(
            org_id=org_id,
            provider_type=provider_type,
            status=SamlConnectionStatus.DRAFT,
            idp_entity_id=idp_entity_id,
            idp_sso_url=idp_sso_url,
            idp_x509_cert=idp_x509_cert,
            sp_entity_id=sp_entity_id,
            acs_url=acs_url,
            default_role=default_role,
            role_mapping_rules=role_mapping_rules,
            actor_user_id=actor.user_id,
        )
        await self._audit.log(
            action="sso.saml.connection_created",
            resource_type="saml_connection",
            org_id=org_id,
            user_id=actor.user_id,
            resource_id=str(connection.id),
            metadata={
                "provider_type": provider_type.value,
                "status": connection.status.value,
            },
        )
        return connection

    async def update_connection(
        self,
        *,
        org_id: UUID,
        connection_id: UUID,
        status: SamlConnectionStatus,
        role_mapping_rules: dict,
        actor: Principal,
    ) -> SamlConnection:
        self._require_org_scope(actor, org_id, "orgs:write")
        existing = await self._repo.get(connection_id)
        if existing.org_id != org_id:
            raise ForbiddenError("Access denied for this organization")
        updated = await self._repo.update(
            connection_id=connection_id,
            status=status,
            role_mapping_rules=role_mapping_rules,
            actor_user_id=actor.user_id,
        )
        await self._audit.log(
            action="sso.saml.connection_updated",
            resource_type="saml_connection",
            org_id=org_id,
            user_id=actor.user_id,
            resource_id=str(updated.id),
            metadata={"status": updated.status.value},
        )
        return updated

    async def delete_connection(
        self, *, org_id: UUID, connection_id: UUID, actor: Principal
    ) -> None:
        self._require_org_scope(actor, org_id, "orgs:write")
        existing = await self._repo.get(connection_id)
        if existing.org_id != org_id:
            raise ForbiddenError("Access denied for this organization")
        await self._repo.delete(connection_id)
        await self._audit.log(
            action="sso.saml.connection_deleted",
            resource_type="saml_connection",
            org_id=org_id,
            user_id=actor.user_id,
            resource_id=str(connection_id),
        )

    async def get_sp_metadata(self, *, org_id: UUID, connection_id: UUID, actor: Principal) -> str:
        self._require_org_scope(actor, org_id, "orgs:read")
        connection = await self._repo.get(connection_id)
        if connection.org_id != org_id:
            raise ForbiddenError("Access denied for this organization")
        return build_sp_metadata(connection)

    async def begin_login(
        self, *, org_id: UUID, connection_id: UUID, actor: Principal | None = None
    ) -> SamlLoginRedirect:
        connection = await self._require_active_connection(
            org_id=org_id, connection_id=connection_id
        )
        if actor is not None:
            self._require_org_scope(actor, org_id, "orgs:read")
        relay_state = f"org:{org_id}:connection:{connection.id}"
        redirect = build_sp_initiated_login_redirect(connection, relay_state=relay_state)
        await self._audit.log(
            action="sso.saml.login_initiated",
            resource_type="saml_connection",
            org_id=org_id,
            user_id=actor.user_id if actor is not None else None,
            resource_id=str(connection.id),
            metadata={"relay_state": relay_state, "binding": redirect.binding},
        )
        return redirect

    async def consume_acs(
        self,
        *,
        org_id: UUID,
        saml_response: str,
        relay_state: str | None,
        connection_id: UUID | None = None,
    ) -> dict:
        connection = await self._resolve_acs_connection(
            org_id=org_id,
            connection_id=connection_id,
            relay_state=relay_state,
        )
        validate_saml_response(
            saml_response,
            connection,
            require_signature=self._settings.saml_require_signed_assertions,
            clock_skew_seconds=self._settings.saml_clock_skew_seconds,
        )
        assertion = parse_saml_assertion(saml_response)
        role = resolve_role_from_mapping(
            groups=assertion.groups,
            role_mapping_rules=connection.role_mapping_rules,
            default_role=connection.default_role,
        )

        user = await self._users.get_by_email(assertion.email)
        if user is None:
            user = await self._users.create(
                email=assertion.email,
                hashed_password=hash_password(secrets.token_urlsafe(32)),
                full_name=assertion.full_name,
            )
            await self._audit.log(
                action="sso.saml.user_provisioned",
                resource_type="user",
                org_id=org_id,
                user_id=user.id,
                resource_id=str(user.id),
                metadata={"email": assertion.email},
            )

        membership = await self._members.upsert_member(
            org_id=org_id,
            user_id=user.id,
            role=role,
        )
        tokens = self._issue_tokens(user_id=user.id, org_id=org_id, role=membership.role)

        await self._audit.log(
            action="sso.saml.login_completed",
            resource_type="saml_connection",
            org_id=org_id,
            user_id=user.id,
            resource_id=str(connection.id),
            metadata={
                "email": assertion.email,
                "role": membership.role.value,
                "relay_state": relay_state,
            },
        )

        return {
            "status": "authenticated",
            "user_id": str(user.id),
            "org_id": str(org_id),
            "role": membership.role.value,
            "tokens": tokens.model_dump(),
        }

    async def commit(self) -> None:
        await self._db.commit()

    async def _resolve_acs_connection(
        self,
        *,
        org_id: UUID,
        connection_id: UUID | None,
        relay_state: str | None,
    ) -> SamlConnection:
        if connection_id is not None:
            connection = await self._repo.get(connection_id)
            if connection.org_id != org_id:
                raise ForbiddenError("Access denied for this organization")
            if connection.status != SamlConnectionStatus.ACTIVE:
                raise SamlAssertionError("SAML connection is not active")
            return connection

        relay_connection_id = self._connection_id_from_relay_state(relay_state)
        if relay_connection_id is not None:
            return await self._require_active_connection(
                org_id=org_id,
                connection_id=relay_connection_id,
            )

        active_connections = await self._repo.get_active_for_org(org_id)
        if len(active_connections) == 1:
            return active_connections[0]
        if not active_connections:
            raise SamlAssertionError("No active SAML connection configured for organization")
        raise SamlAssertionError(
            "connection_id is required when multiple SAML connections are active"
        )

    async def _require_active_connection(
        self, *, org_id: UUID, connection_id: UUID
    ) -> SamlConnection:
        connection = await self._repo.get(connection_id)
        if connection.org_id != org_id:
            raise ForbiddenError("Access denied for this organization")
        if connection.status != SamlConnectionStatus.ACTIVE:
            raise SamlAssertionError("SAML connection is not active")
        return connection

    @staticmethod
    def _connection_id_from_relay_state(relay_state: str | None) -> UUID | None:
        if not relay_state:
            return None
        parts = relay_state.split(":")
        for index, part in enumerate(parts):
            if part == "connection" and index + 1 < len(parts):
                try:
                    return UUID(parts[index + 1])
                except ValueError:
                    return None
        return None

    def _issue_tokens(self, *, user_id: UUID, org_id: UUID, role: OrgRole) -> TokenPair:
        access = create_access_token(
            user_id=user_id,
            org_id=org_id,
            role=role,
            settings=self._settings,
        )
        refresh = create_refresh_token(user_id=user_id, org_id=org_id, settings=self._settings)
        return TokenPair(
            access_token=access,
            refresh_token=refresh,
            expires_in=self._settings.jwt_access_token_expire_minutes * 60,
        )

    @staticmethod
    def _require_org_scope(actor: Principal, org_id: UUID, scope: str) -> None:
        if actor.org_id != org_id:
            raise ForbiddenError("Access denied for this organization")
        AuthService.require_scope(actor, scope)
