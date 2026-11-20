"""Reset a local ClipForge account password from a private terminal."""

import asyncio
import getpass

from sqlalchemy import select

from .auth_routes import hash_password, normalize_email
from .configuration import validate_runtime_configuration
from .db import SessionFactory, engine
from .models import AuthSession, User, utc_now


async def reset_password(email: str, password: str) -> None:
    async with SessionFactory() as session:
        user = await session.scalar(select(User).where(User.email == normalize_email(email)).with_for_update())
        if user is None:
            raise RuntimeError("No account exists for that email address.")
        user.password_hash = await asyncio.to_thread(hash_password, password)
        await session.execute(
            AuthSession.__table__.update()
            .where(AuthSession.user_id == user.id)
            .values(revoked_at=utc_now())
        )
        await session.commit()


async def main() -> None:
    validate_runtime_configuration()
    email = input("Account email: ").strip()
    password = getpass.getpass("New password (12-128 characters): ")
    if not 12 <= len(password) <= 128:
        raise RuntimeError("Password must contain between 12 and 128 characters.")
    confirmation = getpass.getpass("Confirm new password: ")
    if password != confirmation:
        raise RuntimeError("Passwords do not match.")
    await reset_password(email, password)
    print("Password updated. All sessions for this account were signed out.")


async def run() -> None:
    try:
        await main()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
