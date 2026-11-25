from __future__ import annotations

import logging

log = logging.getLogger("notify")


class Notifier:
    """Avisos no log e (se conectado) no seu Telegram, em 'Mensagens Salvas' por padrão."""

    def __init__(self, target: str = "me"):
        self.target = target
        self.client = None

    def attach(self, client) -> None:
        self.client = client

    async def __call__(self, text: str) -> None:
        await self.send(text)

    async def send(self, text: str) -> None:
        log.info("AVISO: %s", text)
        if self.client is None:
            return
        try:
            await self.client.send_message(self.target, text)
        except Exception as exc:  # aviso nunca pode derrubar o robô
            log.warning("não consegui avisar no Telegram: %s", exc)
