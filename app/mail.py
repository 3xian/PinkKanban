from __future__ import annotations

import smtplib
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from fastapi import HTTPException

from app.config import mail_capture, smtp_from, smtp_host, smtp_password, smtp_port, smtp_ssl, smtp_starttls, smtp_user

_captured: dict[str, str] = {}


def captured_code(email: str) -> str:
    return _captured[email]


def clear_captured() -> None:
    _captured.clear()


def build_register_message(email: str, code: str, *, minutes: int) -> EmailMessage:
    sender = smtp_from()
    message = EmailMessage()
    message["Subject"] = "看板注册验证码"
    message["From"] = sender
    message["To"] = email
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = make_msgid(domain=_sender_domain(sender))
    message.set_content(f"你的看板注册验证码是 {code}\n\n{minutes} 分钟内有效。如果不是你本人操作，忽略这封邮件即可。\n")
    return message


def _sender_domain(sender: str) -> str:
    address = sender.rsplit("<", 1)[-1].strip().strip(">")
    domain = address.rsplit("@", 1)[-1].strip()
    return domain or "localhost"


def send_register_code(email: str, code: str, *, minutes: int) -> None:
    if mail_capture():
        _captured[email] = code
        return
    if not smtp_host():
        raise HTTPException(503, "邮件服务未配置")
    message = build_register_message(email, code, minutes=minutes)
    try:
        _deliver(message)
    except OSError as exc:
        raise HTTPException(503, "验证码发送失败，请稍后再试") from exc


def _deliver(message: EmailMessage) -> None:
    host = smtp_host()
    port = smtp_port()
    if smtp_ssl():
        client = smtplib.SMTP_SSL(host, port, timeout=15)
    else:
        client = smtplib.SMTP(host, port, timeout=15)
    try:
        if not smtp_ssl() and smtp_starttls():
            client.starttls()
        user = smtp_user()
        if user:
            client.login(user, smtp_password())
        client.send_message(message)
    finally:
        try:
            client.quit()
        except OSError:
            client.close()
