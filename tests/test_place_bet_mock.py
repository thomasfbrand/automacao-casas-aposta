"""Fluxo completo de aposta contra uma página que imita a Pinnacle real (estrutura lida do HTML salvo pelo robô):
painel do cupom aberto por cima de tudo, botões de odd recriados a cada 350 ms, seção 'Total da equipe' com o
mesmo 'o 2.5' (armadilha), odd fora da tela, teclado numérico ou campo de texto."""
import asyncio
import dataclasses
import os
from pathlib import Path

import pytest

MOCK = Path(__file__).with_name("pinnacle_mock.html").resolve().as_uri()


def _run(query: str, dry_run: bool, monkeypatch, tmp_path):
    playwright = pytest.importorskip("playwright.async_api")
    from bot.config import Config
    from bot.casas.pinnacle import driver as drv

    monkeypatch.chdir(tmp_path)

    class FakeDriver:
        cfg = Config.load("/nonexistent")

        async def dismiss_overlays(self, page, rounds=2):
            return []

    async def run():
        async with playwright.async_playwright() as pw:
            try:
                b = await pw.chromium.launch()
            except Exception:
                pytest.skip("sem Chromium")
            pg = await b.new_page(viewport={"width": 421, "height": 868})
            await pg.goto(MOCK + query)
            tab = drv.GameTab(FakeDriver(), pg)

            async def frame():
                return pg.main_frame
            tab.frame = frame
            st = await tab.read_state()
            res = await tab.place_bet(2.5, 2.0, 1.10, dry_run=dry_run)
            state = await pg.evaluate("({sel: S.sel, placed: S.placed, backdrop: S.backdrop, clicks: S.clicksOnOdd,"
                                      " sheet: getComputedStyle(document.getElementById('sheet')).display})")
            await b.close()
            return st, res, state

    return asyncio.run(run())


@pytest.mark.parametrize("mode", ["input", "keypad"])
def test_dry_run_with_sheet_open_and_rerendering_odds(mode, monkeypatch, tmp_path):
    st, res, state = _run(f"?mode={mode}&sheet=open", True, monkeypatch, tmp_path)
    assert (st.home_goals, st.away_goals, st.minute, st.live) == (0, 0, 12, True)
    assert res.status == "dry_run_ok", res
    assert res.stake == 2.0 and 1.7 < res.odd < 1.8          # odd do Acima/Abaixo, não a do "Total da equipe"
    assert state["sel"] is None                                # cupom limpo no fim do DRY_RUN
    assert state["placed"] is None and state["backdrop"] == 0  # nada confirmado, nenhum clique perdido no fundo
    assert state["sheet"] == "none"


def test_real_bet_accepted(monkeypatch, tmp_path):
    st, res, state = _run("?mode=input&sheet=open", False, monkeypatch, tmp_path)
    assert res.status == "accepted", res
    assert res.receipt == "987654" and res.stake == 2.0
    assert state["placed"] in ("2", "2.0", "2.00") and state["clicks"] == 1


def test_dry_run_when_site_opens_slip_by_itself(monkeypatch, tmp_path):
    st, res, state = _run("?mode=input&autoopen=1", True, monkeypatch, tmp_path)
    assert res.status == "dry_run_ok", res
    assert state["sel"] is None and state["backdrop"] == 0 and state["clicks"] >= 1


def test_watch_waits_in_slip_until_min_odd_then_bets(monkeypatch, tmp_path):
    """Seleciona a linha UMA vez, fica só lendo a odd no cupom e aposta quando ela chega no mínimo."""
    playwright = pytest.importorskip("playwright.async_api")
    from bot.config import Config
    from bot.casas.pinnacle import driver as drv
    monkeypatch.chdir(tmp_path)

    class FakeDriver:
        cfg = Config.load("/nonexistent")

        async def dismiss_overlays(self, page, rounds=2):
            return []

    async def run():
        async with playwright.async_playwright() as pw:
            try:
                b = await pw.chromium.launch()
            except Exception:
                pytest.skip("sem Chromium")
            pg = await b.new_page(viewport={"width": 421, "height": 868})
            await pg.goto(MOCK + "?mode=input&rise=15")
            tab = drv.GameTab(FakeDriver(), pg)

            async def frame():
                return pg.main_frame
            tab.frame = frame
            seen = []
            for _ in range(40):
                st, odd = await tab.watch(2.5)
                seen.append(odd)
                if odd and odd >= 1.90:
                    break
                await asyncio.sleep(0.4)
            res = await tab.place_bet(2.5, 2.0, 1.90, dry_run=False)
            state = await pg.evaluate("({clicks: S.clicksOnOdd, placed: S.placed})")
            await b.close()
            return st, seen, res, state

    st, seen, res, state = asyncio.run(run())
    assert (st.home_goals, st.away_goals) == (0, 0)
    assert any(o is not None and o < 1.7 for o in seen) and seen[-1] >= 1.90
    assert res.status == "accepted", res
    assert state["clicks"] == 1            # a odd foi clicada UMA vez só (selecionar); depois só observou


def test_real_bet_retries_when_house_returns_odds_changed(monkeypatch, tmp_path):
    """1º SIM: a casa devolve com 'Odds have changed' (não apostou). O robô tenta de novo e a 2ª entra."""
    st, res, state = _run("?mode=input&sheet=open&reject=1", False, monkeypatch, tmp_path)
    assert res.status == "accepted", res
    assert state["placed"] in ("1", "2", "2.0", "2.00")
