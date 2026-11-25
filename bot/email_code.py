"""Lê o código de login da Pinnacle que chega por e-mail (Gmail via IMAP).

Precisa de uma "senha de app" do Google (não é a sua senha normal). Veja o README.
Só LÊ a caixa de entrada; nunca apaga nem envia nada.
"""
from __future__ import annotations

import email
import html
import imaplib
import logging
import re
import time
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from typing import Optional

log = logging.getLogger("email_code")

_CODE_NEAR = re.compile(r"c[oó]digo\s+de\s+aprova[cç][aã]o[^0-9]{0,80}(\d{6})", re.I)
_CODE_ANY = re.compile(r"(?<!\d)(\d{6})(?!\d)")


def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw or "")
    raw = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|h\d|td)>", "\n", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    return html.unescape(raw)


def extract_code(text: str) -> Optional[str]:
    """Acha o código de 6 dígitos no texto do e-mail. Prefere o que vem depois de 'código de aprovação'."""
    text = re.sub(r"[ \t\r\f\v\xa0]+", " ", text or "")
    m = _CODE_NEAR.search(text.replace("\n", " "))
    if m:
        return m.group(1)
    m = _CODE_ANY.search(text)
    return m.group(1) if m else None


def _decode(msg) -> tuple[str, str, datetime | None, str]:
    subject = str(make_header(decode_header(msg.get("Subject", ""))))
    sender = str(make_header(decode_header(msg.get("From", ""))))
    try:
        dt = parsedate_to_datetime(msg.get("Date"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except Exception:
        dt = None
    parts: list[str] = []
    for part in msg.walk():
        ctype = part.get_content_type()
        if ctype not in ("text/plain", "text/html"):
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        txt = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        parts.append(html_to_text(txt) if ctype == "text/html" else txt)
    return subject, sender, dt, "\n".join(parts)


VALID_WINDOW_S = 30 * 60   # um código enviado nos últimos 30 minutos ainda vale


def pick_code(messages: list[tuple[str, str, datetime | None, str]], since_ts: float,
              sender_hint: str = "pinnacle", window_s: float = VALID_WINDOW_S) -> Optional[str]:
    """messages = [(assunto, remetente, data, corpo)]. Devolve o código do e-mail MAIS NOVO da Pinnacle
    recebido nos últimos `window_s` (30 min) antes de since_ts ou depois dele: um código recente ainda vale."""
    best: tuple[float, str] | None = None
    for subject, sender, dt, body in messages:
        if sender_hint.lower() not in (sender or "").lower():
            continue
        if dt is None or dt.timestamp() < since_ts - window_s:
            continue
        code = extract_code(body) or extract_code(subject)
        if code and (best is None or dt.timestamp() > best[0]):
            best = (dt.timestamp(), code)
    return best[1] if best else None


def _fetch_once(user: str, app_password: str, since_ts: float, sender_hint: str, host: str) -> Optional[str]:
    imap = imaplib.IMAP4_SSL(host, 993)
    try:
        imap.login(user, app_password)
        for folder in ("INBOX", "[Gmail]/Spam"):
            try:
                st, _ = imap.select(folder, readonly=True)
            except Exception:
                continue
            if st != "OK":
                continue
            day = datetime.fromtimestamp(since_ts - 86400, timezone.utc).strftime("%d-%b-%Y")
            st, data = imap.search(None, "SINCE", day, "FROM", f'"{sender_hint}"')
            if st != "OK" or not data or not data[0]:
                continue
            ids = data[0].split()[-6:]  # só os mais recentes
            msgs = []
            for mid in ids:
                st, md = imap.fetch(mid, "(BODY.PEEK[])")
                if st == "OK" and md and isinstance(md[0], tuple):
                    msgs.append(_decode(email.message_from_bytes(md[0][1])))
            code = pick_code(msgs, since_ts, sender_hint)
            if code:
                return code
        return None
    finally:
        try:
            imap.logout()
        except Exception:
            pass


def fetch_code(user: str, app_password: str, since_ts: float, timeout_s: float = 90,
               sender_hint: str = "pinnacle", host: str = "imap.gmail.com", poll_s: float = 4.0) -> Optional[str]:
    """Bloqueante: fica consultando o Gmail até o código aparecer ou o tempo acabar."""
    deadline = time.time() + timeout_s
    last_err = None
    while time.time() < deadline:
        try:
            code = _fetch_once(user, app_password, since_ts, sender_hint, host)
            if code:
                return code
            last_err = None
        except imaplib.IMAP4.error as exc:
            log.warning("Gmail recusou o login IMAP (senha de app errada ou IMAP desligado?): %s", exc)
            return None
        except Exception as exc:  # rede etc.: tenta de novo
            last_err = exc
        time.sleep(poll_s)
    if last_err:
        log.warning("erro lendo o Gmail: %s", last_err)
    return None
