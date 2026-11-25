"""Lista seus chats/canais do Telegram com o ID para colocar em TG_CHANNEL.

  python -m tools.list_chats
  python -m tools.list_chats apostas     # filtra pelo nome
"""
import asyncio
import sys

from telethon import TelegramClient

from bot.config import Config


async def main() -> None:
    cfg = Config.load()
    flt = (sys.argv[1] if len(sys.argv) > 1 else "").lower()
    client = TelegramClient(cfg.tg_session, cfg.tg_api_id, cfg.tg_api_hash)
    await client.start()
    async for d in client.iter_dialogs():
        if flt and flt not in (d.name or "").lower():
            continue
        kind = "canal" if d.is_channel and not d.is_group else "grupo" if d.is_group else "chat"
        user = getattr(d.entity, "username", None)
        print(f"{d.id:>16}  {kind:<6} {d.name}" + (f"  (@{user})" if user else ""))
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
