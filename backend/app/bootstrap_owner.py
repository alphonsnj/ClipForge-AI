"""Create the first workspace owner from a private administrative terminal."""

import asyncio
import getpass

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from .auth_routes import hash_password, normalize_email
from .configuration import validate_runtime_configuration
from .db import SessionFactory, engine
from .models import Project, Team, TeamMembership, User


async def create_owner(email: str, password: str) -> None:
    async with SessionFactory() as session:
        await session.execute(text("SELECT pg_advisory_xact_lock(1128813132, 6)"))
        if int(await session.scalar(select(func.count(User.id))) or 0):
            raise RuntimeError("An account already exists; refusing to create another initial owner.")

        user = User(email=normalize_email(email), password_hash=await asyncio.to_thread(hash_password, password))
        session.add(user)
        team = await session.scalar(
            select(Team)
            .outerjoin(TeamMembership, TeamMembership.team_id == Team.id)
            .where(TeamMembership.id.is_(None))
            .order_by(Team.created_at)
            .limit(1)
        )
        if team is None:
            team = Team(name=f"{user.email.split('@', 1)[0]}'s workspace")
            session.add(team)
            await session.flush()
        else:
            team.name = f"{user.email.split('@', 1)[0]}'s workspace"
        await session.execute(
            Project.__table__.update()
            .where(Project.team_id == team.id, Project.created_by_user_id.is_(None))
            .values(created_by_user_id=user.id)
        )
        session.add(TeamMembership(team_id=team.id, user_id=user.id, role="owner"))
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise RuntimeError("Account setup was already completed; no account was created.") from None


async def main() -> None:
    validate_runtime_configuration()
    email = input("Initial owner email: ").strip()
    password = getpass.getpass("Initial owner password (12-128 characters): ")
    if not 12 <= len(password) <= 128:
        raise RuntimeError("Password must contain between 12 and 128 characters.")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise RuntimeError("Passwords do not match.")
    await create_owner(email, password)
    print("Initial workspace owner created.")


async def run() -> None:
    try:
        await main()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
