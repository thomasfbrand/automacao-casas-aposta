"""Valida os trechos JS contra uma página simulada com a MESMA estrutura de texto vista na Pinnacle.

(Não substitui testar no site real; garante que a lógica de achar jogo/linha/cupom está correta.)
"""
import pytest

from bot.casas.pinnacle import js
from bot.casas.pinnacle.parsing import (parse_card_teams, parse_confirm, parse_money, parse_slip_odd, parse_state)

LIST_HTML = """
<body>
<div class="league">ESPANHA - LA LIGA</div>
<div class="card"><div>2H 24'</div><div>Partida 1X2</div>
  <div><span>Sevilla</span><b>1</b></div><div><span>Barcelona</span><b>3</b></div>
  <div><span>+ 15 &gt;</span><span>+ 1 Mais Mercados (Partida)</span></div></div>
<div class="league">BRASIL - SÉRIE A</div>
<div class="card"><div>2H 34'</div><div>Partida 1X2</div>
  <div><span>Atlético Mineiro</span><b>1</b></div><div><span>Chapecoense</span><b>1</b></div>
  <div><span>+ 46 &gt;</span><span>+ 12 Mais Mercados (Partida)</span></div></div>
</body>"""

DETAIL_HTML = """
<body>
<div>Espanha - La Liga</div><div>AO VIVO</div><div>2º Tempo - 26'</div><div>Sevilla 1-3 Barcelona</div>
<div>Handicap - Partida</div>
<div><button><span>o 5.5</span><span>9.999</span></button></div>
<div>Acima/Abaixo - Partida</div>
<div><button><span>o 5.25</span><span>2.750</span></button><button><span>u 5.25</span><span>1.480</span></button></div>
<div id="vt"><span>Ver Tudo</span></div>
<div>Total Da Equipe - Partida</div>
<div><button><span>o 1.5</span><span>3.140</span></button></div>
</body>"""

DETAIL_EXPANDED = DETAIL_HTML.replace(
    '<div id="vt">',
    '<div><button><span>o 5.5</span><span>3.310</span></button><button><span>u 5.5</span><span>1.341</span></button></div><div id="vt">')

SLIP_HTML = """
<body>
<div id="slip"><div>Boletim De Apostas</div>
  <div><div>Sevilla vs Barcelona</div><div>Mais de 5.5</div><div>3.310</div><button aria-label="remover">x</button></div>
  <div><label>Aposta</label><input id="i"></div>
</div></body>"""


@pytest.fixture(scope="module")
def page():
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # navegador não instalado neste ambiente
            pytest.skip(f"chromium indisponível: {exc}")
        pg = browser.new_page()
        yield pg
        browser.close()


def test_find_games_and_teams(page):
    page.set_content(LIST_HTML)
    cards = page.evaluate(js.TAG_GAMES)
    assert len(cards) == 2
    teams = [parse_card_teams(c["lines"]) for c in cards]
    assert teams[0] == ("Sevilla", "Barcelona")
    assert teams[1] == ("Atlético Mineiro", "Chapecoense")
    # o botão marcado do 2º card pertence ao card do Atlético
    assert page.locator('[data-bot-plus="1"]').inner_text().startswith("+ 46")


def test_over_line_read_only_in_ou_partida(page):
    page.set_content(DETAIL_HTML)
    r = page.evaluate(js.READ_OVER, 5.5)
    assert r["found"] is False and r["sectionFound"] is True   # handicap tem "o 5.5" mas não conta
    r = page.evaluate(js.READ_OVER, 1.5)
    assert r["found"] is False                                    # total da equipe não conta
    r = page.evaluate(js.READ_OVER, 5.25)
    assert r["found"] and r["odd"] == 2.75
    v = page.evaluate(js.TAG_VER_TUDO)
    assert v["found"] and v["expanded"] is False


def test_over_line_after_expand(page):
    page.set_content(DETAIL_EXPANDED)
    r = page.evaluate(js.READ_OVER, 5.5)
    assert r["found"] and r["odd"] == 3.31
    assert page.locator('[data-bot-over="1"]').inner_text().replace("\n", " ").startswith("o 5.5")


def test_slip_helpers(page):
    page.set_content(SLIP_HTML)
    r = page.evaluate(js.TAG_SLIP_REMOVE, ['[aria-label*="remov" i]'])
    assert r["found"]
    s = page.evaluate(js.TAG_STAKE_INPUT)
    assert s == {"input": True}


def test_parse_state():
    st = parse_state("Espanha - La Liga\nAO VIVO\n2º Tempo - 26'\nSevilla 1-3 Barcelona\n")
    assert st.live and st.minute == 71 and (st.home_goals, st.away_goals) == (1, 3) and not st.ended
    st = parse_state("AO VIVO\n1º Tempo 12'\nA 0-0 B")
    assert st.minute == 12 and st.total_goals == 0
    assert parse_state("Encerrado\nA 2-1 B").ended


def test_money_and_confirm():
    assert parse_money("41.75") == 41.75 and parse_money("41,75") == 41.75
    assert parse_money("12,855.00") == 12855.0 and parse_money("1.234,56") == 1234.56
    assert parse_confirm("Tem certeza de que deseja arriscar 2.00 BRL para ganhar 4.78 BRL?") == (2.0, 4.78, 3.39)
    assert parse_slip_odd("Odds have changed from 3.210 to 3.390.\nMais de 2.5 3.390", 2.5) == 3.39
    assert parse_slip_odd("Mais de 5.5\n3.310", 5.5) == 3.31
