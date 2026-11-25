import asyncio
import types

import pytest


def test_new_live_message_triggers_engine():
    pytest.importorskip("telethon")
    from bot import telegram_client as tg

    handlers = []

    class FakeClient:
        def on(self, event):
            def deco(fn):
                handlers.append((type(event).__name__, fn))
                return fn
            return deco

    calls = []

    class FakeEngine:
        async def on_message(self, mid, text, reply_to=None, date_ts=None):
            calls.append((mid, text, reply_to, date_ts))

        async def on_edited(self, mid, text):
            calls.append(("edit", mid))

        async def on_deleted(self, ids):
            calls.append(("del", ids))

    tg.register_handlers(FakeClient(), "grupo", FakeEngine())
    new = dict(handlers)["NewMessage"]
    import datetime
    msg = types.SimpleNamespace(id=77, raw_text="Live\nMÉTODO 2\nENTRADA NO OVER 1.5 GOLS", reply_to=None,
                                date=datetime.datetime(2026, 9, 22, tzinfo=datetime.timezone.utc))
    asyncio.run(new(types.SimpleNamespace(message=msg)))
    assert calls and calls[0][0] == 77 and calls[0][1].startswith("Live") and calls[0][3] is not None
