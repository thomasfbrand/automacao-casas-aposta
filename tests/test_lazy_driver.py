import asyncio
import dataclasses

from bot.config import Config
from bot.casas.pinnacle import driver as drv


class FakePage:
    async def close(self):
        pass


class FakeContext:
    pages = []

    async def new_page(self):
        return FakePage()

    async def close(self):
        pass


def test_browser_opens_only_on_tip_once_and_closes_when_idle():
    cfg = Config.load("/nonexistent")
    msgs = []

    async def notify(m):
        msgs.append(m)

    d = drv.PinnacleDriver(cfg, notify)
    starts = []

    async def fake_start():
        starts.append(1)
        await asyncio.sleep(0.05)
        d.context = FakeContext()

    d.start = fake_start

    async def use():
        async with d.open_tab():
            await asyncio.sleep(0.05)

    async def go():
        assert not d.started                       # robô ligado: navegador fechado
        await asyncio.gather(use(), use())          # duas tips ao mesmo tempo
        assert d.started and len(starts) == 1       # abriu e logou UMA vez
        assert not await d.close_if_idle(9999)      # ainda não ficou ocioso tempo suficiente
        d.last_used -= 10000
        assert await d.close_if_idle(9999)          # ocioso: fecha
        assert not d.started
        await use()                                 # nova tip: reabre
        assert len(starts) == 2

    asyncio.run(go())
    assert any("Abrindo a Pinnacle" in m for m in msgs)
