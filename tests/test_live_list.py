import asyncio
from pathlib import Path

import pytest

MOCK = Path(__file__).with_name("live_list_mock.html").resolve().as_uri()


@pytest.mark.parametrize("target,idx", [(("Al Duhail", "Al Arabi Doha"), 17), (("Time 9 A", "Time 9 B"), 9)])
def test_finds_game_deep_in_virtualized_list(target, idx, monkeypatch, tmp_path):
    playwright = pytest.importorskip("playwright.async_api")
    from bot.config import Config
    from bot.casas.pinnacle import driver as drv

    monkeypatch.chdir(tmp_path)

    class FakeDriver:
        cfg = Config.load("/nonexistent")

    async def run():
        async with playwright.async_playwright() as pw:
            try:
                b = await pw.chromium.launch()
            except Exception:
                pytest.skip("sem Chromium")
            pg = await b.new_page(viewport={"width": 421, "height": 868})
            await pg.goto(MOCK)
            tab = drv.GameTab(FakeDriver(), pg)
            found, seen = await tab.find_and_open(pg.main_frame, *target)
            opened = await pg.evaluate("window.opened || null")
            await b.close()
            return found, seen, opened

    found, seen, opened = asyncio.run(run())
    assert found, seen
    assert opened == ("Al-Duhail SC" if idx == 17 else "Time 9 A")
