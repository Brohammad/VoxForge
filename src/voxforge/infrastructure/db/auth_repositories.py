from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voxforge.core.domain.auth import ApiKey, Organization, OrganizationMember, OrgRole, User
from voxforge.core.domain.sso import SamlConnection, SamlConnectionStatus, SamlProviderType
from voxforge.core.exceptions import (
    ApiKeyNotFoundError,
    OrganizationNotFoundError,
    SamlConnectionNotFoundError,
    UserNotFoundError,
)
from voxforge.infrastructure.db.models import (
    ApiKeyModel,
    AuditLogModel,
    OrganizationInviteModel,
    OrganizationMemberModel,
    OrganizationModel,
    SamlConnectionModel,
    UserModel,
)
from voxforge.infrastructure.security.tokens import slugify


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, email: str, hashed_password: str, full_name: str) -> User:
        model = UserModel(email=email, hashed_password=hashed_password, full_name=full_name)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_entity(model)

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(UserModel).where(UserModel.email == email)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get(self, user_id: UUID) -> User:
        model = await self._session.get(UserModel, user_id)
        if model is None:
            raise UserNotFoundError(str(user_id))
        return self._to_entity(model)

    @staticmethod
    def _to_entity(model: UserModel) -> User:
        return User(
            id=model.id,
            email=model.email,
            full_name=model.full_name,
            is_active=model.is_active,
            created_at=model.created_at,
        )


class OrganizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, name: str, slug: str | None = None) -> Organization:
        base_slug = slug or slugify(name)
        unique_slug = await self._unique_slug(base_slug)
        model = OrganizationModel(name=name, slug=unique_slug)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_entity(model)

    async def get(self, org_id: UUID) -> Organization:
        model = await self._session.get(OrganizationModel, org_id)
        if model is None:
            raise OrganizationNotFoundError(str(org_id))
        return self._to_entity(model)

    async def list_for_user(self, user_id: UUID) -> list[Organization]:
        stmt = (
            select(OrganizationModel)
            .join(OrganizationMemberModel)
            .where(OrganizationMemberModel.user_id == user_id)
            .order_by(OrganizationModel.created_at)
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def _unique_slug(self, base: str) -> str:
        slug = base
        counter = 1
        while True:
            stmt = select(OrganizationModel).where(OrganizationModel.slug == slug)
            result = await self._session.execute(stmt)
            if result.scalar_one_or_none() is None:
                return slug
            counter += 1
            slug = f"{base}-{counter}"

    @staticmethod
    def _to_entity(model: OrganizationModel) -> Organization:
        return Organization(
            id=model.id,
            name=model.name,
            slug=model.slug,
            created_at=model.created_at,
        )


class OrganizationMemberRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_member(
        self, *, org_id: UUID, user_id: UUID, role: OrgRole = OrgRole.MEMBER
    ) -> OrganizationMember:
        model = OrganizationMemberModel(org_id=org_id, user_id=user_id, role=role)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_entity(model)

    async def get_membership(self, *, org_id: UUID, user_id: UUID) -> OrganizationMember | None:
        stmt = select(OrganizationMemberModel).where(
            OrganizationMemberModel.org_id == org_id,
            OrganizationMemberModel.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def upsert_member(
        self, *, org_id: UUID, user_id: UUID, role: OrgRole
    ) -> OrganizationMember:
        stmt = select(OrganizationMemberModel).where(
            OrganizationMemberModel.org_id == org_id,
            OrganizationMemberModel.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return await self.add_member(org_id=org_id, user_id=user_id, role=role)
        model.role = role
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_entity(model)

    async def list_members(self, org_id: UUID) -> list[OrganizationMember]:
        stmt = (
            select(OrganizationMemberModel)
            .where(OrganizationMemberModel.org_id == org_id)
            .order_by(OrganizationMemberModel.created_at)
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def remove_member(self, *, org_id: UUID, user_id: UUID) -> None:
        stmt = select(OrganizationMemberModel).where(
            OrganizationMemberModel.org_id == org_id,
            OrganizationMemberModel.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model:
            await self._session.delete(model)

    @staticmethod
    def _to_entity(model: OrganizationMemberModel) -> OrganizationMember:
        return OrganizationMember(
            id=model.id,
            org_id=model.org_id,
            user_id=model.user_id,
            role=OrgRole(model.role),
            created_at=model.created_at,
        )


class OrganizationInviteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        org_id: UUID,
        email: str,
        role: OrgRole,
        token_hash: str,
        invited_by_user_id: UUID | None,
        expires_at: datetime,
    ) -> OrganizationInviteModel:
        existing = await self.get_pending_by_org_email(org_id=org_id, email=email)
        if existing is not None:
            existing.role = role.value
            existing.token_hash = token_hash
            existing.invited_by_user_id = invited_by_user_id
            existing.expires_at = expires_at
            existing.accepted_at = None
            await self._session.flush()
            await self._session.refresh(existing)
            return existing
        model = OrganizationInviteModel(
            org_id=org_id,
            email=email.lower().strip(),
            role=role.value,
            token_hash=token_hash,
            invited_by_user_id=invited_by_user_id,
            expires_at=expires_at,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return model

    async def get_pending_by_org_email(
        self, *, org_id: UUID, email: str
    ) -> OrganizationInviteModel | None:
        stmt = select(OrganizationInviteModel).where(
            OrganizationInviteModel.org_id == org_id,
            OrganizationInviteModel.email == email.lower().strip(),
            OrganizationInviteModel.accepted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_token_hash(self, token_hash: str) -> OrganizationInviteModel | None:
        stmt = select(OrganizationInviteModel).where(
            OrganizationInviteModel.token_hash == token_hash
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_accepted(self, invite: OrganizationInviteModel) -> None:
        invite.accepted_at = datetime.now(UTC)
        await self._session.flush()


class ApiKeyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        org_id: UUID,
        name: str,
        key_prefix: str,
        key_hash: str,
        scopes: list[str],
        created_by_user_id: UUID | None,
        expires_at: datetime | None = None,
    ) -> ApiKey:
        model = ApiKeyModel(
            org_id=org_id,
            name=name,
            key_prefix=key_prefix,
            key_hash=key_hash,
            scopes=scopes,
            created_by_user_id=created_by_user_id,
            expires_at=expires_at,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_entity(model)

    async def get(self, key_id: UUID) -> ApiKey:
        model = await self._session.get(ApiKeyModel, key_id)
        if model is None:
            raise ApiKeyNotFoundError(str(key_id))
        return self._to_entity(model)

    async def list_for_org(self, org_id: UUID) -> list[ApiKey]:
        stmt = (
            select(ApiKeyModel)
            .where(ApiKeyModel.org_id == org_id, ApiKeyModel.revoked_at.is_(None))
            .order_by(ApiKeyModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def find_by_prefix(self, key_prefix: str) -> list[ApiKeyModel]:
        stmt = select(ApiKeyModel).where(
            ApiKeyModel.key_prefix == key_prefix,
            ApiKeyModel.revoked_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def revoke(self, key_id: UUID) -> ApiKey:
        model = await self._session.get(ApiKeyModel, key_id)
        if model is None:
            raise ApiKeyNotFoundError(str(key_id))
        model.revoked_at = datetime.now(UTC)
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_entity(model)

    @staticmethod
    def _to_entity(model: ApiKeyModel) -> ApiKey:
        return ApiKey(
            id=model.id,
            org_id=model.org_id,
            name=model.name,
            key_prefix=model.key_prefix,
            scopes=model.scopes or [],
            expires_at=model.expires_at,
            revoked_at=model.revoked_at,
            created_by_user_id=model.created_by_user_id,
            created_at=model.created_at,
        )


class AuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def log(
        self,
        *,
        action: str,
        resource_type: str,
        org_id: UUID | None = None,
        user_id: UUID | None = None,
        resource_id: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        model = AuditLogModel(
            org_id=org_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata_=metadata or {},
        )
        self._session.add(model)

    async def list_for_org(self, org_id: UUID, *, limit: int = 500) -> list[AuditLogModel]:
        stmt = (
            select(AuditLogModel)
            .where(AuditLogModel.org_id == org_id)
            .order_by(AuditLogModel.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class SamlConnectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        org_id: UUID,
        provider_type: SamlProviderType,
        status: SamlConnectionStatus,
        idp_entity_id: str,
        idp_sso_url: str,
        idp_x509_cert: str,
        sp_entity_id: str,
        acs_url: str,
        default_role: OrgRole,
        role_mapping_rules: dict,
        actor_user_id: UUID | None,
    ) -> SamlConnection:
        model = SamlConnectionModel(
            org_id=org_id,
            provider_type=provider_type,
            status=status,
            idp_entity_id=idp_entity_id,
            idp_sso_url=idp_sso_url,
            idp_x509_cert=idp_x509_cert,
            sp_entity_id=sp_entity_id,
            acs_url=acs_url,
            default_role=default_role,
            role_mapping_rules=role_mapping_rules,
            created_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_entity(model)

    async def get(self, connection_id: UUID) -> SamlConnection:
        model = await self._session.get(SamlConnectionModel, connection_id)
        if model is None:
            raise SamlConnectionNotFoundError(str(connection_id))
        return self._to_entity(model)

    async def list_for_org(self, org_id: UUID) -> list[SamlConnection]:
        stmt = (
            select(SamlConnectionModel)
            .where(SamlConnectionModel.org_id == org_id)
            .order_by(SamlConnectionModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(model) for model in result.scalars().all()]

    async def get_active_for_org(self, org_id: UUID) -> list[SamlConnection]:
        stmt = (
            select(SamlConnectionModel)
            .where(
                SamlConnectionModel.org_id == org_id,
                SamlConnectionModel.status == SamlConnectionStatus.ACTIVE,
            )
            .order_by(SamlConnectionModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(model) for model in result.scalars().all()]

    async def update(
        self,
        *,
        connection_id: UUID,
        status: SamlConnectionStatus,
        role_mapping_rules: dict,
        actor_user_id: UUID | None,
    ) -> SamlConnection:
        model = await self._session.get(SamlConnectionModel, connection_id)
        if model is None:
            raise SamlConnectionNotFoundError(str(connection_id))
        model.status = status
        model.role_mapping_rules = role_mapping_rules
        model.updated_by_user_id = actor_user_id
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_entity(model)

    async def delete(self, connection_id: UUID) -> None:
        model = await self._session.get(SamlConnectionModel, connection_id)
        if model is None:
            raise SamlConnectionNotFoundError(str(connection_id))
        await self._session.delete(model)

    @staticmethod
    def _to_entity(model: SamlConnectionModel) -> SamlConnection:
        return SamlConnection(
            id=model.id,
            org_id=model.org_id,
            provider_type=SamlProviderType(model.provider_type),
            status=SamlConnectionStatus(model.status),
            idp_entity_id=model.idp_entity_id,
            idp_sso_url=model.idp_sso_url,
            idp_x509_cert=model.idp_x509_cert,
            sp_entity_id=model.sp_entity_id,
            acs_url=model.acs_url,
            default_role=OrgRole(model.default_role),
            role_mapping_rules=model.role_mapping_rules or {},
            created_by_user_id=model.created_by_user_id,
            updated_by_user_id=model.updated_by_user_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
