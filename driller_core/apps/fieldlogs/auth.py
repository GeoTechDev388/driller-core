from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.core import signing
from django.utils import timezone

from driller_core.apps.accounts.models import UserAccount

from .models import DrillerUser


class DrillerAuthError(Exception):
    def __init__(self, detail: str, *, code: str = "driller_auth_failed"):
        super().__init__(detail)
        self.detail = detail
        self.code = code


@dataclass(frozen=True)
class DrillerAccessContext:
    user_account: UserAccount
    driller_user: DrillerUser

    @property
    def driller(self):
        return self.driller_user.driller


def get_driller_access_context(user_account: UserAccount) -> DrillerAccessContext:
    if not user_account.is_active:
        raise DrillerAuthError("This driller portal account is inactive.", code="inactive_account")

    driller_user = DrillerUser.objects.select_related("driller", "user_account").filter(
        user_account=user_account,
        is_active=True,
    ).first()
    if driller_user is None:
        raise DrillerAuthError("Driller portal access is not enabled for this account.", code="access_not_enabled")
    if not driller_user.portal_access_enabled:
        raise DrillerAuthError("Driller portal access is disabled for this account.", code="portal_access_disabled")
    if not driller_user.driller.is_active:
        raise DrillerAuthError("The assigned driller profile is inactive.", code="inactive_driller")

    return DrillerAccessContext(
        user_account=user_account,
        driller_user=driller_user,
    )


def build_driller_session_token(user_account: UserAccount) -> str:
    payload = {
        "user_id": user_account.pk,
        "issued_at": int(timezone.now().timestamp()),
    }
    return signing.dumps(payload, salt=settings.DRILLER_ACCESS_TOKEN_SALT)


def resolve_driller_session_token(token: str) -> DrillerAccessContext:
    if not token:
        raise DrillerAuthError("Driller access token is required.", code="missing_token")

    try:
        payload = signing.loads(
            token,
            max_age=settings.DRILLER_ACCESS_TOKEN_TTL_SECONDS,
            salt=settings.DRILLER_ACCESS_TOKEN_SALT,
        )
    except signing.BadSignature as exc:
        raise DrillerAuthError("Driller access token is invalid or expired.", code="invalid_token") from exc

    user_account = UserAccount.objects.filter(pk=payload.get("user_id")).first()
    if user_account is None:
        raise DrillerAuthError("Driller access account was not found.", code="account_not_found")

    return get_driller_access_context(user_account)


def driller_response_payload(context: DrillerAccessContext) -> dict:
    user_account = context.user_account
    driller_user = context.driller_user
    driller = driller_user.driller
    return {
        "user": {
            "id": user_account.id,
            "email": user_account.email,
            "is_active": user_account.is_active,
        },
        "driller_user": {
            "id": driller_user.id,
            "shared_uuid": str(driller_user.shared_uuid),
            "email": driller_user.email,
            "is_active": driller_user.is_active,
            "portal_access_enabled": driller_user.portal_access_enabled,
        },
        "driller": {
            "id": driller.id,
            "shared_uuid": str(driller.shared_uuid),
            "company_name": driller.company_name,
            "contact_name": driller.contact_name,
            "email": driller.email,
            "phone": driller.phone,
            "active": driller.is_active,
        },
    }
