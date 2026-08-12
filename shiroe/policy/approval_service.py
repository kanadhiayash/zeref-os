"""Human-only approval request service."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from shiroe.policy.approvals import (
    ApprovalRequest,
    ApprovalStatus,
    ApprovalType,
    scope_digest,
)
from shiroe.storage.state import StateDB


class AuthorizationError(PermissionError):
    """Raised when a non-human actor attempts to decide an approval."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _loads(text: str) -> Any:
    return json.loads(text)


class ApprovalService:
    def __init__(self, root: Path | str):
        self.db = StateDB(root)
        self.conn = self.db.connect()
        self.db.migrate()

    def close(self) -> None:
        self.db.close()

    def request(
        self,
        *,
        approval_type: ApprovalType | str,
        requested_action: str,
        scope: Mapping[str, Any],
        reason: str,
        risk: str,
        graph_id: str | None = None,
        node_id: str | None = None,
        action_kind: str | None = None,
        options: tuple[str, ...] = (),
        evidence_refs: tuple[str, ...] = (),
        request_id: str | None = None,
    ) -> ApprovalRequest:
        req = ApprovalRequest(
            id=request_id or f"apr_{uuid.uuid4().hex}",
            approval_type=approval_type,
            requested_action=requested_action,
            scope=scope,
            reason=reason,
            risk=risk,
            graph_id=graph_id,
            node_id=node_id,
            action_kind=action_kind,
            options=options,
            evidence_refs=evidence_refs,
            status=ApprovalStatus.pending,
            requested_at=_now(),
        )
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO approval_requests(
                    id, graph_id, node_id, approval_type, action_kind,
                    requested_action, scope_json, scope_digest, reason,
                    options_json, evidence_refs_json, risk, status, requested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    req.id,
                    req.graph_id,
                    req.node_id,
                    req.approval_type.value,
                    req.action_kind,
                    req.requested_action,
                    _json(dict(req.scope)),
                    req.digest,
                    req.reason,
                    _json(list(req.options)),
                    _json(list(req.evidence_refs)),
                    req.risk,
                    req.status.value,
                    req.requested_at,
                ),
            )
        return req

    def get(self, approval_id: str) -> ApprovalRequest:
        row = self.conn.execute(
            """
            SELECT id, graph_id, node_id, approval_type, action_kind,
                   requested_action, scope_json, reason, options_json,
                   evidence_refs_json, risk, status, requested_at, decided_at,
                   decided_by, decision_reason
            FROM approval_requests WHERE id=?
            """,
            (approval_id,),
        ).fetchone()
        if row is None:
            raise KeyError(approval_id)
        return ApprovalRequest(
            id=row[0],
            graph_id=row[1],
            node_id=row[2],
            approval_type=row[3],
            action_kind=row[4],
            requested_action=row[5],
            scope=_loads(row[6]),
            reason=row[7],
            options=tuple(_loads(row[8])),
            evidence_refs=tuple(_loads(row[9])),
            risk=row[10],
            status=row[11],
            requested_at=row[12],
            decided_at=row[13],
            decided_by=row[14],
            decision_reason=row[15],
        )

    def decide_human(
        self,
        approval_id: str,
        *,
        decision: ApprovalStatus | str,
        actor: str,
        reason: str,
        actor_kind: str | None = None,
    ) -> ApprovalRequest:
        if actor != "human" or (actor_kind is not None and actor_kind != "human"):
            raise AuthorizationError("approval decisions require a human actor")
        status = ApprovalStatus(decision)
        if status in {ApprovalStatus.pending, ApprovalStatus.stale}:
            raise ValueError(f"{status.value!r} is not a human decision")
        with self.conn:
            cur = self.conn.execute(
                """
                UPDATE approval_requests
                SET status=?, decided_at=?, decided_by=?, decision_reason=?
                WHERE id=?
                """,
                (status.value, _now(), actor, reason, approval_id),
            )
        if cur.rowcount != 1:
            raise KeyError(approval_id)
        return self.get(approval_id)

    def assert_current(
        self,
        approval_id: str,
        *,
        current_scope: Mapping[str, Any],
    ) -> ApprovalRequest:
        req = self.get(approval_id)
        if scope_digest(current_scope) == req.digest:
            return req
        with self.conn:
            self.conn.execute(
                "UPDATE approval_requests SET status=? WHERE id=?",
                (ApprovalStatus.stale.value, approval_id),
            )
        return self.get(approval_id)

    def find_pending(
        self,
        *,
        graph_id: str | None,
        node_id: str | None,
        action_kind: str | None,
        requested_action: str,
        scope: Mapping[str, Any],
    ) -> ApprovalRequest | None:
        digest = scope_digest(scope)
        row = self.conn.execute(
            """
            SELECT id FROM approval_requests
            WHERE COALESCE(graph_id, '')=COALESCE(?, '')
              AND COALESCE(node_id, '')=COALESCE(?, '')
              AND COALESCE(action_kind, '')=COALESCE(?, '')
              AND requested_action=?
              AND scope_digest=?
              AND status=?
            ORDER BY requested_at DESC
            LIMIT 1
            """,
            (
                graph_id,
                node_id,
                action_kind,
                requested_action,
                digest,
                ApprovalStatus.pending.value,
            ),
        ).fetchone()
        return self.get(row[0]) if row else None

    def find_latest_matching(
        self,
        *,
        graph_id: str | None,
        node_id: str | None,
        action_kind: str | None,
        requested_action: str,
        scope: Mapping[str, Any],
    ) -> ApprovalRequest | None:
        """Latest request for the exact scope, regardless of status.

        Used by the policy service to consult prior human decisions
        before minting a new pending request -- so an approved decision
        can advance execution and a rejected one can fail it, instead of
        being invisible because ``find_pending`` filters by pending only.
        """
        digest = scope_digest(scope)
        row = self.conn.execute(
            """
            SELECT id FROM approval_requests
            WHERE COALESCE(graph_id, '')=COALESCE(?, '')
              AND COALESCE(node_id, '')=COALESCE(?, '')
              AND COALESCE(action_kind, '')=COALESCE(?, '')
              AND requested_action=?
              AND scope_digest=?
            ORDER BY requested_at DESC
            LIMIT 1
            """,
            (
                graph_id,
                node_id,
                action_kind,
                requested_action,
                digest,
            ),
        ).fetchone()
        return self.get(row[0]) if row else None
