"""Scheduler entry point: sync connected Instagram accounts without HTTP.

Usage (cron-friendly, exits non-zero on failure):
    cd backend && .venv/bin/python -m app.sync_cli [--email user@example.com] [--force]

Syncs every connected account (or just one user's), honoring the same
per-account throttle as the "Sync now" button unless --force is given.
Designed to run from cron/systemd; see README.md.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from sqlalchemy import select

from app.db.session import async_session
from app.models.instagram import InstagramAccount, User
from app.services import sync_service
from app.services.providers.base import get_provider

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("sync_cli")


async def _run(email: str | None, force: bool) -> int:
    provider = get_provider()  # enforces the mock-in-production safety gate
    failures = 0
    synced = 0
    async with async_session() as session:
        query = select(InstagramAccount)
        if email:
            user = (
                await session.execute(select(User).where(User.email == email.lower()))
            ).scalar_one_or_none()
            if user is None:
                log.error("No app user with email %s", email)
                return 2
            query = query.where(InstagramAccount.user_id == user.id)
        accounts = (await session.execute(query)).scalars().all()
        if not accounts:
            log.info("No connected Instagram accounts to sync.")
            return 0
        for account in accounts:
            try:
                result = await sync_service.sync_account(session, account, provider, force=force)
                status = result.get("status")
                if status == "failed":
                    failures += 1
                    log.error("Sync failed for %s: %s", account.username, result.get("error"))
                else:
                    synced += 1
                    log.info(
                        "Sync %s for %s (%s)", status, account.username, account.instagram_user_id
                    )
            except Exception as exc:  # noqa: BLE001 - report and continue with other accounts
                failures += 1
                log.exception("Sync crashed for %s: %s", account.username, exc)
    log.info("Done: %d synced, %d failed", synced, failures)
    return 1 if failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Instagram analytics for connected accounts.")
    parser.add_argument("--email", help="Only sync this app user's account.")
    parser.add_argument("--force", action="store_true", help="Skip the per-account sync throttle.")
    args = parser.parse_args()
    sys.exit(asyncio.run(_run(args.email, args.force)))


if __name__ == "__main__":
    main()
