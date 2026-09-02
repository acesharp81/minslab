from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any


class WatchDeliveryRepository:
    def __init__(self, connection: Any):
        self.connection = connection

    @staticmethod
    def _state_hash(state: str) -> str:
        return hashlib.sha256(state.encode("utf-8")).hexdigest()

    def begin_oauth(self, subscriber_id: uuid.UUID) -> str:
        state = secrets.token_urlsafe(32)
        self.connection.execute(
            """
            INSERT INTO watch_kakao_oauth_states (state_hash, subscriber_id, expires_at)
            VALUES (%s, %s, now() + interval '10 minutes')
            """,
            (self._state_hash(state), subscriber_id),
        )
        return state

    def create_web_session(
        self, subscriber_id: uuid.UUID, *, user_agent: str = "", days: int = 30,
    ) -> str:
        token = secrets.token_urlsafe(48)
        user_agent_hash = (
            hashlib.sha256(user_agent.encode("utf-8")).hexdigest()
            if user_agent else None
        )
        self.connection.execute(
            """
            INSERT INTO watch_web_sessions (
                id, subscriber_id, token_hash, user_agent_hash, expires_at
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (
                uuid.uuid4(), subscriber_id, self._state_hash(token),
                user_agent_hash,
                datetime.now(timezone.utc) + timedelta(days=max(1, days)),
            ),
        )
        return token

    def revoke_web_session(self, token: str) -> bool:
        row = self.connection.execute(
            """
            UPDATE watch_web_sessions SET revoked_at = now()
            WHERE token_hash = %s AND revoked_at IS NULL RETURNING id
            """,
            (self._state_hash(token),),
        ).fetchone()
        return bool(row)

    def revoke_all_web_sessions(self, subscriber_id: uuid.UUID) -> int:
        rows = self.connection.execute(
            """
            UPDATE watch_web_sessions SET revoked_at = now()
            WHERE subscriber_id = %s AND revoked_at IS NULL RETURNING id
            """,
            (subscriber_id,),
        ).fetchall()
        return len(rows)

    def subscriber_for_kakao_user(self, kakao_user_id: str) -> uuid.UUID | None:
        row = self.connection.execute(
            """
            SELECT subscriber_id FROM watch_kakao_accounts
            WHERE kakao_user_id = %s
            ORDER BY (status = 'ACTIVE') DESC, updated_at DESC LIMIT 1
            FOR UPDATE
            """,
            (kakao_user_id,),
        ).fetchone()
        return row[0] if row else None

    def connected(self, subscriber_id: uuid.UUID) -> bool:
        row = self.connection.execute(
            """
            SELECT 1 FROM watch_kakao_accounts
            WHERE subscriber_id = %s AND status = 'ACTIVE'
              AND access_token_ciphertext <> ''
            LIMIT 1
            """,
            (subscriber_id,),
        ).fetchone()
        return bool(row)

    def lock_kakao_identity(self, kakao_user_id: str) -> None:
        self.connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (kakao_user_id,),
        )

    def prune_operational_history(self) -> dict[str, int]:
        oauth = self.connection.execute(
            """
            DELETE FROM watch_kakao_oauth_states
            WHERE expires_at < now() - interval '1 day' RETURNING state_hash
            """
        ).fetchall()
        attempts = self.connection.execute(
            """
            DELETE FROM notification_outbox
            WHERE channel = 'KAKAO' AND status IN ('FAILED', 'CANCELED')
              AND updated_at < now() - interval '30 days' RETURNING id
            """
        ).fetchall()
        return {"oauth_states": len(oauth), "delivery_attempts": len(attempts)}

    def consume_oauth(self, state: str) -> uuid.UUID | None:
        row = self.connection.execute(
            """
            UPDATE watch_kakao_oauth_states SET consumed_at = now()
            WHERE state_hash = %s AND consumed_at IS NULL AND expires_at > now()
            RETURNING subscriber_id
            """,
            (self._state_hash(state),),
        ).fetchone()
        return row[0] if row else None

    def save_account(self, subscriber_id: uuid.UUID, account: dict[str, Any]) -> None:
        self.connection.execute(
            """
            INSERT INTO watch_kakao_accounts (
                id, subscriber_id, kakao_user_id, access_token_ciphertext,
                refresh_token_ciphertext, access_token_expires_at,
                refresh_token_expires_at, scopes, status, last_error
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'ACTIVE', NULL)
            ON CONFLICT (subscriber_id) DO UPDATE SET
                kakao_user_id = EXCLUDED.kakao_user_id,
                access_token_ciphertext = EXCLUDED.access_token_ciphertext,
                refresh_token_ciphertext = EXCLUDED.refresh_token_ciphertext,
                access_token_expires_at = EXCLUDED.access_token_expires_at,
                refresh_token_expires_at = EXCLUDED.refresh_token_expires_at,
                scopes = EXCLUDED.scopes, status = 'ACTIVE', last_error = NULL,
                connected_at = now(), updated_at = now()
            """,
            (
                uuid.uuid4(), subscriber_id, account["kakao_user_id"],
                account["access_token_ciphertext"], account["refresh_token_ciphertext"],
                account["access_token_expires_at"], account["refresh_token_expires_at"],
                account["scopes"],
            ),
        )

    def status(self, subscriber_id: uuid.UUID) -> dict[str, Any]:
        row = self.connection.execute(
            """
            SELECT id, status, scopes, connected_at, updated_at, last_error
            FROM watch_kakao_accounts WHERE subscriber_id = %s
            """,
            (subscriber_id,),
        ).fetchone()
        if not row:
            return {"connected": False, "status": "NOT_CONNECTED"}
        latest_delivery = self.connection.execute(
            """
            SELECT status, sent_at, last_error
            FROM notification_outbox
            WHERE subscriber_id = %s AND channel = 'KAKAO'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (subscriber_id,),
        ).fetchone()
        result = {
            "account_id": row[0], "connected": row[1] == "ACTIVE",
            "status": row[1], "scopes": row[2], "connected_at": row[3],
            "updated_at": row[4], "last_error": row[5],
        }
        if latest_delivery:
            result.update({
                "last_delivery_status": latest_delivery[0],
                "last_delivered_at": latest_delivery[1],
                "last_delivery_error": latest_delivery[2],
            })
        return result

    def account_for_subscriber(self, subscriber_id: uuid.UUID) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT id, subscriber_id, access_token_ciphertext,
                   refresh_token_ciphertext, access_token_expires_at,
                   refresh_token_expires_at, status
            FROM watch_kakao_accounts WHERE subscriber_id = %s
            """,
            (subscriber_id,),
        ).fetchone()
        if not row:
            return None
        return dict(zip((
            "account_id", "subscriber_id", "access_token_ciphertext",
            "refresh_token_ciphertext", "access_token_expires_at",
            "refresh_token_expires_at", "status",
        ), row, strict=True))

    def disconnect(self, subscriber_id: uuid.UUID) -> None:
        self.connection.execute(
            """
            UPDATE watch_kakao_accounts
            SET status = 'DISCONNECTED', access_token_ciphertext = '',
                refresh_token_ciphertext = '', updated_at = now()
            WHERE subscriber_id = %s
            """,
            (subscriber_id,),
        )
        self.connection.execute(
            """
            UPDATE notification_outbox SET status = 'CANCELED', updated_at = now()
            WHERE subscriber_id = %s AND channel = 'KAKAO'
              AND status IN ('PENDING', 'SENDING', 'FAILED')
            """,
            (subscriber_id,),
        )

    def update_account_tokens(
        self, account_id: uuid.UUID, *, access_token_ciphertext: str,
        access_token_expires_at: datetime,
        refresh_token_ciphertext: str | None = None,
        refresh_token_expires_at: datetime | None = None,
    ) -> None:
        self.connection.execute(
            """
            UPDATE watch_kakao_accounts SET
                access_token_ciphertext = %s, access_token_expires_at = %s,
                refresh_token_ciphertext = COALESCE(%s, refresh_token_ciphertext),
                refresh_token_expires_at = COALESCE(%s, refresh_token_expires_at),
                status = 'ACTIVE', last_error = NULL, updated_at = now()
            WHERE id = %s
            """,
            (
                access_token_ciphertext, access_token_expires_at,
                refresh_token_ciphertext, refresh_token_expires_at, account_id,
            ),
        )

    def mark_reauthorize(self, account_id: uuid.UUID, error: str) -> None:
        self.connection.execute(
            """
            UPDATE watch_kakao_accounts SET status = 'REAUTHORIZE',
                   last_error = %s, updated_at = now() WHERE id = %s
            """,
            (error[:240], account_id),
        )

    def claim(self, worker_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            WITH candidate AS (
                SELECT outbox.id
                FROM notification_outbox outbox
                JOIN watch_kakao_accounts account
                  ON account.subscriber_id = outbox.subscriber_id
                 AND account.status = 'ACTIVE'
                WHERE outbox.channel = 'KAKAO'
                  AND outbox.status IN ('PENDING', 'FAILED', 'SENDING')
                  AND outbox.attempt_count < 3
                  AND outbox.next_attempt_at <= now()
                  AND (outbox.lease_expires_at IS NULL OR outbox.lease_expires_at < now())
                ORDER BY outbox.created_at
                FOR UPDATE OF outbox SKIP LOCKED LIMIT 1
            )
            UPDATE notification_outbox outbox
            SET status = 'SENDING', lease_owner = %s,
                lease_expires_at = now() + interval '2 minutes', updated_at = now()
            FROM candidate WHERE outbox.id = candidate.id
            RETURNING outbox.id, outbox.subscriber_id, outbox.notification_id,
                      outbox.attempt_count
            """,
            (worker_id,),
        ).fetchone()
        if not row:
            return None
        outbox_id, subscriber_id, notification_id, attempt_count = row
        notification = self.connection.execute(
            """
            SELECT title, body, session_id FROM watch_notifications WHERE id = %s
            """,
            (notification_id,),
        ).fetchone()
        account = self.account_for_subscriber(subscriber_id)
        if not notification or not account:
            self.finish(outbox_id, sent=False, error="delivery source missing", retryable=False)
            return None
        return {
            "outbox_id": outbox_id, "subscriber_id": subscriber_id,
            "notification_id": notification_id, "attempt_count": int(attempt_count),
            "title": notification[0], "body": notification[1],
            "session_id": notification[2], "account": account,
        }

    def finish(
        self, outbox_id: uuid.UUID, *, sent: bool, error: str = "",
        retryable: bool = False,
    ) -> None:
        row = self.connection.execute(
            "SELECT attempt_count FROM notification_outbox WHERE id = %s",
            (outbox_id,),
        ).fetchone()
        attempts = int(row[0] if row else 0) + 1
        status = "SENT" if sent else "FAILED"
        delay_minutes = min(60, 2 ** max(0, attempts - 1)) if retryable and attempts < 3 else 0
        self.connection.execute(
            """
            UPDATE notification_outbox SET status = %s, attempt_count = %s,
                   next_attempt_at = now() + (%s * interval '1 minute'),
                   sent_at = CASE WHEN %s THEN now() ELSE sent_at END,
                   last_error = %s, lease_owner = NULL, lease_expires_at = NULL,
                   updated_at = now()
            WHERE id = %s
            """,
            (status, attempts, delay_minutes, sent, error[:240] or None, outbox_id),
        )
