import asyncio
import secrets
import string
from dataclasses import dataclass

import razorpay
from sqlalchemy.ext.asyncio import AsyncSession

from models.institute_base import InstituteSchema, RazorpayStatus
from models.owner_base import OwnerSchema
from repositories.institute_repository import InstituteRepository
from services.crypto_service import decrypt_secret


class InvalidRazorpayCredentialsError(ValueError):
    """Raised when submitted Razorpay keys are test-mode or fail live authentication."""


def _generate_join_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


@dataclass
class InstituteSearchResult:
    institute: InstituteSchema
    owner: OwnerSchema


@dataclass
class InstituteQRInfo:
    join_code: str
    join_url: str
    institute_name: str
    owner_phone: str


class InstituteService:
    def __init__(self):
        self.institute_repo = InstituteRepository()

    async def create_institute(
        self, db: AsyncSession, owner_id: int, name: str, city: str
    ) -> InstituteSchema:
        """Create institute for owner. Raises ValueError if one already exists."""
        existing = await self.institute_repo.get_by_owner_id(db, owner_id)
        if existing:
            raise ValueError("Institute already exists for this owner")
        join_code = _generate_join_code()
        institute = InstituteSchema(owner_id=owner_id, name=name, city=city, join_code=join_code)
        return await self.institute_repo.create(db, institute)

    async def get_institute_by_owner_id(
        self, db: AsyncSession, owner_id: int
    ) -> InstituteSchema | None:
        return await self.institute_repo.get_by_owner_id(db, owner_id)

    async def get_by_owner_id(
        self, db: AsyncSession, owner_id: int
    ) -> InstituteSchema | None:
        return await self.institute_repo.get_by_owner_id(db, owner_id)

    async def get_by_id(self, db: AsyncSession, institute_id: int) -> InstituteSchema | None:
        return await self.institute_repo.get_by_id(db, institute_id)

    async def get_by_join_code(
        self, db: AsyncSession, join_code: str
    ) -> InstituteSchema | None:
        return await self.institute_repo.get_by_join_code(db, join_code)

    async def find_by_owner_phone(
        self, db: AsyncSession, owner_phone: str
    ) -> InstituteSearchResult | None:
        row = await self.institute_repo.find_by_owner_phone(db, owner_phone)
        if row is None:
            return None
        institute, owner = row
        return InstituteSearchResult(institute=institute, owner=owner)

    async def get_qr_info(
        self, db: AsyncSession, owner_id: int, owner_phone: str, base_url: str
    ) -> InstituteQRInfo | None:
        institute = await self.institute_repo.get_by_owner_id(db, owner_id)
        if not institute:
            return None
        join_url = f"{base_url.rstrip('/')}/join/{institute.join_code}"
        return InstituteQRInfo(
            join_code=institute.join_code,
            join_url=join_url,
            institute_name=institute.name,
            owner_phone=owner_phone,
        )

    async def update_institute(
        self, db: AsyncSession, owner_id: int, updates: dict
    ) -> InstituteSchema | None:
        institute = await self.institute_repo.get_by_owner_id(db, owner_id)
        if not institute:
            return None
        return await self.institute_repo.update(db, institute, updates)

    async def connect_razorpay(
        self, db: AsyncSession, owner_id: int, key_id: str, key_secret: str
    ) -> InstituteSchema:
        """Save an owner's own Razorpay Key ID/Secret; encrypts the secret at rest.

        Rejects test-mode keys and confirms the submitted keys actually
        authenticate against Razorpay before persisting anything.

        Raises:
            ValueError: If no institute exists for this owner.
            InvalidRazorpayCredentialsError: If the key is test-mode or Razorpay
                rejects the credentials.
        """
        from services.crypto_service import encrypt_secret

        institute = await self.institute_repo.get_by_owner_id(db, owner_id)
        if not institute:
            raise ValueError("No institute found for this owner")

        if not key_id.startswith("rzp_live_"):
            raise InvalidRazorpayCredentialsError(
                "Test-mode keys (rzp_test_...) aren't accepted — payments made with "
                "them never settle anywhere real. Use the live Key ID/Secret from "
                "Razorpay Dashboard → Account & Settings → API Keys."
            )

        client = razorpay.Client(auth=(key_id, key_secret))
        try:
            await asyncio.to_thread(client.payment.all, {"count": 1})
        except razorpay.errors.BadRequestError as e:
            raise InvalidRazorpayCredentialsError(f"Razorpay rejected these credentials: {e}") from e

        updates = {
            "razorpay_key_id": key_id,
            "razorpay_key_secret_encrypted": encrypt_secret(key_secret),
            "razorpay_status": RazorpayStatus.CONNECTED,
        }
        return await self.institute_repo.update(db, institute, updates)

    async def set_webhook_secret(
        self, db: AsyncSession, owner_id: int, webhook_secret: str
    ) -> InstituteSchema:
        """Save the webhook secret the owner generated when registering BatchBook's
        webhook URL in their own Razorpay dashboard; encrypts it at rest.

        Raises:
            ValueError: If no institute exists for this owner.
        """
        from services.crypto_service import encrypt_secret

        institute = await self.institute_repo.get_by_owner_id(db, owner_id)
        if not institute:
            raise ValueError("No institute found for this owner")

        updates = {"razorpay_webhook_secret_encrypted": encrypt_secret(webhook_secret)}
        return await self.institute_repo.update(db, institute, updates)

    async def flag_needs_reconnect(
        self, db: AsyncSession, institute_id: int
    ) -> InstituteSchema | None:
        """Flip an institute's payout status to NEEDS_RECONNECT after a Razorpay
        auth failure using its stored keys (rotated/revoked on the owner's own
        Razorpay dashboard).

        Idempotent: a no-op if the institute is already NEEDS_RECONNECT, so a
        second auth failure (e.g. a retried backfill sweep) doesn't re-write it.

        Returns None if no institute with this id exists, so callers (which
        already hold a live institute reference in most cases) can treat a
        vanished institute as a no-op rather than an error.
        """
        institute = await self.institute_repo.get_by_id(db, institute_id)
        if not institute:
            return None
        if institute.razorpay_status == RazorpayStatus.NEEDS_RECONNECT:
            return institute
        return await self.institute_repo.update(
            db, institute, {"razorpay_status": RazorpayStatus.NEEDS_RECONNECT}
        )

    async def test_razorpay_connection(self, db: AsyncSession, owner_id: int) -> InstituteSchema:
        """Re-validate an institute's already-saved Razorpay keys with a live API call.

        Unlike connect_razorpay, this doesn't take new keys — it re-checks the
        ones already on file, which is exactly what's needed after an owner
        reports "reconnect" isn't clearing: confirm whether the stored keys
        actually still work before assuming a UI bug.

        Flips CONNECTED -> NEEDS_RECONNECT on an auth failure, and
        NEEDS_RECONNECT -> CONNECTED on success, so a manual "Test connection"
        click can both catch a silent rotation and confirm recovery after the
        owner pastes fresh keys via connect_razorpay.

        Raises:
            ValueError: If no institute exists for this owner, or no
                credentials have been saved yet.
        """
        institute = await self.institute_repo.get_by_owner_id(db, owner_id)
        if not institute:
            raise ValueError("No institute found for this owner")
        if not institute.razorpay_key_id or not institute.razorpay_key_secret_encrypted:
            raise ValueError("No Razorpay credentials saved yet — connect an account first")

        secret = decrypt_secret(institute.razorpay_key_secret_encrypted)
        client = razorpay.Client(auth=(institute.razorpay_key_id, secret))
        try:
            await asyncio.to_thread(client.payment.all, {"count": 1})
        except razorpay.errors.BadRequestError:
            return await self.institute_repo.update(
                db, institute, {"razorpay_status": RazorpayStatus.NEEDS_RECONNECT}
            )

        if institute.razorpay_status != RazorpayStatus.CONNECTED:
            return await self.institute_repo.update(
                db, institute, {"razorpay_status": RazorpayStatus.CONNECTED}
            )
        return institute


def get_institute_service() -> InstituteService:
    return InstituteService()
