"""Conexão com o Telegram usando a SUA conta (Telethon). Lê o canal/grupo de tips."""
from __future__ import annotations

import logging
from typing import Optional

from telethon import TelegramClient, events

from .config import Config

log = logging.getLogger("telegram")


def _channel_ref(value: str):
    v = value.strip()
    if v.lstrip("-").isdigit():
        return int(v)
    return v


async def connect(cfg: Config) -> TelegramClient:
    if not cfg.tg_api_id or not cfg.tg_api_hash:
        raise SystemExit("Preencha TG_API_ID e TG_API_HASH no .env (https://my.telegram.org -> API development tools)")
    client = TelegramClient(cfg.tg_session, cfg.tg_api_id, cfg.tg_api_hash)
    await client.start()  # 1ª vez: pede telefone + código (+ senha 2FA do Telegram, se tiver)
    me = await client.get_me()
    log.info("Telegram conectado como %s", getattr(me, "username", None) or me.id)
    return client


async def resolve_channel(client: TelegramClient, cfg: Config):
    if not cfg.tg_channel:
        raise SystemExit("Preencha TG_CHANNEL no .env (rode: python -m tools.list_chats)")
    return await client.get_entity(_channel_ref(cfg.tg_channel))


def register_handlers(client: TelegramClient, entity, engine) -> None:
    @client.on(events.NewMessage(chats=entity))
    async def _new(ev):
        m = ev.message
        reply_to = getattr(getattr(m, "reply_to", None), "reply_to_msg_id", None)
        ts = m.date.timestamp() if m.date else None
        await engine.on_message(m.id, m.raw_text or "", reply_to=reply_to, date_ts=ts)

    @client.on(events.MessageEdited(chats=entity))
    async def _edited(ev):
        await engine.on_edited(ev.message.id, ev.message.raw_text or "")

    @client.on(events.MessageDeleted())
    async def _deleted(ev):
        # em canais/supergrupos o evento pode vir sem chat; filtramos pelos IDs que acompanhamos
        await engine.on_deleted(list(ev.deleted_ids or []))


def make_alive_check(client: TelegramClient, entity):
    """Confere no servidor se as tips ainda existem (o admin apaga a tip cancelada)."""
    async def check(ids: list[int]) -> list[int]:
        msgs = await client.get_messages(entity, ids=ids)
        if not isinstance(msgs, list):
            msgs = [msgs]
        return [i for i, m in zip(ids, msgs) if m is None]
    return check
