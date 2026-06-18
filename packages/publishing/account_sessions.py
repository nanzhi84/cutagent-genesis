"""Account browser-session lifecycle (publishing center).

Backend-agnostic orchestration over an accounts repo + ``SecretStore``: storing a
session writes the encrypted ``storage_state`` to the SecretStore and disables the
ref it displaced, so a replaced or cleared session never leaves an orphan secret
on disk. The repo's ``set_account_session`` swaps atomically and returns the
displaced ref (and enforces the ``publish_session`` state machine), so a concurrent
replace disables exactly the ref it replaced rather than a stale read.

The service layer wraps these with request wiring + audit; PR3's QR-login flow
calls ``store_account_session`` once a scan succeeds.
"""

from __future__ import annotations

from datetime import datetime

from packages.core.contracts import PublishAccount
from packages.core.contracts.base import utcnow
from packages.core.storage.secret_store import SecretStore


def store_account_session(
    repo,
    store: SecretStore,
    account_id: str,
    storage_state_json: str,
    *,
    session_expires_at: datetime | None = None,
) -> PublishAccount | None:
    """Persist (or replace) an account's encrypted session; disable the prior one."""
    if repo.get_account(account_id) is None:
        return None
    new_ref = store.put(storage_state_json)
    updated, old_ref = repo.set_account_session(
        account_id,
        secret_ref=new_ref,
        session_status="active",
        session_expires_at=session_expires_at,
        last_validated_at=utcnow(),
    )
    if updated is None:
        store.disable(new_ref)  # account vanished mid-flight — don't orphan the secret
        return None
    if old_ref is not None and old_ref != new_ref:
        store.disable(old_ref)  # disable exactly the ref this swap displaced
    return updated


def clear_account_session(repo, store: SecretStore, account_id: str) -> PublishAccount | None:
    """Disable an account's session secret and mark it expired (no-op if none)."""
    account = repo.get_account(account_id)
    if account is None:
        return None
    if repo.get_account_session_ref(account_id) is None:
        return account
    updated, old_ref = repo.set_account_session(
        account_id, secret_ref=None, session_status="expired"
    )
    if old_ref is not None:
        store.disable(old_ref)
    return updated
