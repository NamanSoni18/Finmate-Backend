# agents/central_context_agent.py

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SessionContext:
    session_id: str
    state: str = "AWAITING_PHONE"
    customer: Optional[Dict[str, Any]] = None
    loan: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    last_seen: float = field(default_factory=lambda: time.time())


class CentralContextAgent:
    """Centralized per-session context store.

    This is intentionally in-memory (prototype-friendly). For production,
    replace with Redis/DB.
    """

    def __init__(self, *, session_ttl_seconds: int = 60 * 60):
        self._ttl = session_ttl_seconds
        self._sessions: Dict[str, SessionContext] = {}

    def get(self, session_id: str) -> SessionContext:
        self._cleanup_expired()
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionContext(session_id=session_id)
        ctx = self._sessions[session_id]
        ctx.last_seen = time.time()
        return ctx

    def update(
        self,
        session_id: str,
        *,
        state: Optional[str] = None,
        customer: Optional[Dict[str, Any]] = None,
        loan_updates: Optional[Dict[str, Any]] = None,
        meta_updates: Optional[Dict[str, Any]] = None,
    ) -> SessionContext:
        ctx = self.get(session_id)
        if state is not None:
            ctx.state = state
        if customer is not None:
            ctx.customer = customer
        if loan_updates:
            ctx.loan.update(loan_updates)
        if meta_updates:
            ctx.meta.update(meta_updates)
        ctx.last_seen = time.time()
        return ctx

    def add_event(self, session_id: str, *, kind: str, payload: Dict[str, Any]) -> None:
        ctx = self.get(session_id)
        ctx.events.append({"ts": time.time(), "kind": kind, "payload": payload})

    def _cleanup_expired(self) -> None:
        now = time.time()
        expired = [sid for sid, ctx in self._sessions.items() if now - ctx.last_seen > self._ttl]
        for sid in expired:
            self._sessions.pop(sid, None)
