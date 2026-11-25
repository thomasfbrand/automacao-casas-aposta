"""Fluxo completo da stake.com contra uma página simulada (tests/stakecom_mock.html) servida no lugar do site real.

Cobre o que só aparece com o site "vivo": odds recriadas a cada 300 ms, a linha da tip que ainda não é oferecida,
o "Over 1.5" do total da EQUIPE (armadilha), DRY_RUN que limpa sem confirmar, e as respostas da casa depois de
apostar (aceita, odd mudou, recusada, silêncio).
"""
import asyncio
import dataclasses
import json
from pathlib import Path

import pytest

MOCK = Path(__file__).with_name("stakecom_mock.html").read_text(encoding="utf-8")


def _cfg(**extra):
    from bot.config import Config
    return dataclasses.replace(Config.load("/nonexistent"), money_from_casa=True, match_threshold=0.70, **extra)


@pytest.fixture(scope="module")
def navegador():
    """Um Chromium para o módulo inteiro (abrir um por teste custava ~6 s cada no Windows).
    Cada teste ganha um contexto NOVO (cookies e página limpos), então um teste não vaza no outro."""
    playwright = pytest.importorskip("playwright.async_api")
    loop = asyncio.new_event_loop()
    pw = loop.run_until_complete(playwright.async_playwright().start())
    try:
        b = loop.run_until_complete(pw.chromium.launch())
    except Exception:
        loop.run_until_complete(pw.stop())
        loop.close()
        pytest.skip("sem Chromium")
    yield loop, b
    loop.run_until_complete(b.close())
    loop.run_until_complete(pw.stop())
    loop.close()


@pytest.fixture
def run(navegador):
    loop, b = navegador

    def _run(mock: dict, corpo, **cfg_extra):
        """Abre a página simulada com window.MOCK = mock e roda `corpo(tab, page, avisos)`."""
        from bot.casas.stakecom import driver as drv

        avisos = []

        async def notify(m):
            avisos.append(m)

        async def go():
            ctx = await b.new_context(viewport={"width": 1280, "height": 900})
            try:
                pg = await ctx.new_page()
                await pg.add_init_script(f"window.MOCK = {json.dumps(mock)};")
                await pg.route("https://stake.com/**",
                               lambda r: r.fulfill(status=200, content_type="text/html", body=MOCK))
                tab = drv.StakeComTab(drv.StakeComDriver(_cfg(**cfg_extra), notify), pg)
                return await corpo(tab, pg, avisos)
            finally:
                await ctx.close()

        return loop.run_until_complete(go())

    return _run


async def _abrir(tab):
    assert await tab.open_game("Al Faisaly", "Al Rayyan", attempts=1)


def test_acha_o_jogo_na_lista_e_le_placar_minuto_e_odd(run):
    async def corpo(tab, pg, avisos):
        await _abrir(tab)
        assert tab.url.endswith("/46867045-al-faisaly-jor-al-rayyan-sc")   # sem o /pl/ do link
        st, odd = await tab.watch(1.5)
        return st, odd

    st, odd = run({"odds": [1.70]}, corpo)
    assert (st.home_goals, st.away_goals, st.minute, st.live) == (0, 1, 66, True)
    assert odd == 1.70


def test_linha_ainda_nao_oferecida_nao_e_gol_mas_linha_que_some_e(run):
    async def corpo(tab, pg, avisos):
        await _abrir(tab)
        _, odd = await tab.watch(1.5)
        antes = (odd, tab.line_missing_for(), list(avisos))
        await asyncio.sleep(1.6)                                   # a linha aparece
        _, odd2 = await tab.watch(1.5)
        await pg.evaluate("document.getElementById('asian').remove()")   # e some (gol)
        await tab.watch(1.5)
        await asyncio.sleep(0.3)
        return antes, odd2, tab.line_missing_for()

    (odd, faltando, avisos), odd2, faltando_depois = run({"lineAfterMs": 1200, "odds": [1.8]}, corpo)
    assert odd is None and faltando == 0.0                         # não oferecida ainda: NÃO conta como sumida
    assert any("ainda não oferece over 1.5" in a for a in avisos)
    assert odd2 == 1.8
    assert faltando_depois > 0                                     # já tinha aparecido e sumiu: aí conta


def test_dry_run_monta_o_cupom_e_limpa_sem_confirmar(run):
    async def corpo(tab, pg, avisos):
        await _abrir(tab)
        res = await tab.place_bet(1.5, 2.0, 1.60, dry_run=True)
        return res, await pg.evaluate("({sel: S.sel, placed: S.placed, clicks: S.clicksPlace, stake: S.stake})")

    res, s = run({"logged": True, "odds": [1.75]}, corpo)
    assert res.status == "dry_run_ok", res
    assert res.stake == 2.0 and res.odd == 1.75
    assert s["stake"] == "2.00"                                    # o valor entrou no campo
    assert s["clicks"] == 0 and s["placed"] is None                # nunca clicou em apostar
    assert s["sel"] is None                                        # cupom limpo no fim


def test_aposta_real_aceita_com_odd_que_mexe_o_tempo_todo(run):
    async def corpo(tab, pg, avisos):
        await _abrir(tab)
        res = await tab.place_bet(1.5, 2.0, 1.60, dry_run=False)
        return res, await pg.evaluate("S.placed")

    res, placed = run({"logged": True, "odds": [1.70, 1.72, 1.71, 1.74], "result": "accepted"}, corpo)
    assert res.status == "accepted", res
    assert res.receipt == "7f3a9c21-bb"
    assert placed["line"] == 1.5 and placed["stake"] == "2.00"     # a linha certa, não a 2.5 nem a da equipe
    assert placed["odd"] >= 1.60


def test_odd_abaixo_do_minimo_nao_aposta(run):
    async def corpo(tab, pg, avisos):
        await _abrir(tab)
        res = await tab.place_bet(1.5, 2.0, 1.90, dry_run=False)
        return res, await pg.evaluate("({placed: S.placed, clicks: S.clicksPlace})")

    res, s = run({"logged": True, "odds": [1.70]}, corpo)
    assert res.status == "odd_low" and s["clicks"] == 0 and s["placed"] is None


def test_odd_mudou_na_hora_nao_conta_como_aposta(run):
    async def corpo(tab, pg, avisos):
        await _abrir(tab)
        return await tab.place_bet(1.5, 2.0, 1.60, dry_run=False)

    res = run({"logged": True, "odds": [1.70], "result": "oddschange"}, corpo)
    assert res.status == "unavailable" and "odd mudou" in res.detail


def test_recusa_da_casa_vira_falha(run):
    async def corpo(tab, pg, avisos):
        await _abrir(tab)
        return await tab.place_bet(1.5, 2.0, 1.60, dry_run=False)

    res = run({"logged": True, "odds": [1.70], "result": "rejected"}, corpo)
    assert res.status == "failed" and "recusou" in res.detail


def test_casa_em_silencio_vira_incerta_e_nao_repete(run, monkeypatch):
    from bot.casas.stakecom import driver as drv
    monkeypatch.setattr(drv, "RESULT_TIMEOUT_S", 3)

    async def corpo(tab, pg, avisos):
        await _abrir(tab)
        res = await tab.place_bet(1.5, 2.0, 1.60, dry_run=False)
        return res, await pg.evaluate("S.clicksPlace")

    res, cliques = run({"logged": True, "odds": [1.70], "result": "silent"}, corpo)
    assert res.status == "unknown"                                 # o motor para e avisa (D6)
    assert cliques == 1                                            # clicou UMA vez só


def test_deslogado_nunca_aposta_de_verdade(run):
    async def corpo(tab, pg, avisos):
        await _abrir(tab)
        res = await tab.place_bet(1.5, 2.0, 1.60, dry_run=False)
        return res, await pg.evaluate("({clicks: S.clicksPlace, sel: S.sel})")

    res, s = run({"logged": False, "odds": [1.70]}, corpo)
    assert res.status == "failed" and "deslogada" in res.detail
    assert s["clicks"] == 0 and s["sel"] is None


def test_linha_que_so_existe_no_total_da_equipe_nao_e_apostada(run):
    async def corpo(tab, pg, avisos):
        await _abrir(tab)
        res = await tab.place_bet(1.5, 2.0, 1.10, dry_run=False)
        return res, await pg.evaluate("({clicks: S.clicksPlace, sel: S.sel})")

    res, s = run({"logged": True, "lineAfterMs": 999999}, corpo)    # Asian Total sem 1.5; equipe tem "Over 1.5"
    assert res.status == "unavailable"
    assert s["sel"] is None and s["clicks"] == 0
