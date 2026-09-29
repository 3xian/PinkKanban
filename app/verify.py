from __future__ import annotations

import hashlib
import hmac
import math
import secrets
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import secret_key
from app.models import EmailCode, utcnow

CODE_TTL = 600
RESEND_WAIT = 60
MAX_ATTEMPTS = 5
_INVALID = "验证码不正确或已过期"


def issue_code(db: Session, email: str) -> str:
    now = utcnow()
    row = db.get(EmailCode, email)
    if row is not None:
        elapsed = (now - row.sent_at).total_seconds()
        if elapsed < RESEND_WAIT:
            wait = max(1, min(RESEND_WAIT, math.ceil(RESEND_WAIT - elapsed)))
            raise HTTPException(429, f"请 {wait} 秒后再获取验证码")
    code = f"{secrets.randbelow(1_000_000):06d}"
    expires = now + timedelta(seconds=CODE_TTL)
    if row is None:
        db.add(EmailCode(email=email, code_hash=_hash(email, code), expires_at=expires, sent_at=now, attempts=0))
    else:
        row.code_hash = _hash(email, code)
        row.expires_at = expires
        row.sent_at = now
        row.attempts = 0
    db.flush()
    return code


def consume_code(db: Session, email: str, code: str) -> None:
    row = db.get(EmailCode, email)
    now = utcnow()
    if row is None:
        raise HTTPException(400, _INVALID)
    if row.expires_at <= now:
        db.delete(row)
        db.commit()
        raise HTTPException(400, _INVALID)
    if hmac.compare_digest(row.code_hash, _hash(email, code)):
        db.delete(row)
        return
    row.attempts += 1
    if row.attempts >= MAX_ATTEMPTS:
        db.delete(row)
    db.commit()
    raise HTTPException(400, _INVALID)


def _hash(email: str, code: str) -> str:
    return hmac.new(secret_key().encode(), f"{email}\n{code}".encode(), hashlib.sha256).hexdigest()
