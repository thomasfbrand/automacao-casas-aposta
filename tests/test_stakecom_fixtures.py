"""stake.com contra HTML REAL capturado (tests/fixtures/stake/, 25/11/2026, deslogado).

Duas camadas:
- js.py lendo o HTML de verdade (precisa do Chromium do Playwright);
- parsing.py decidindo em cima do que foi lido (Python puro, roda em qualquer lugar).
"""
from pathlib import Path

import pytest

from bot.casas.stakecom import js
from bot.casas.stakecom.parsing import (best_card, game_path, minute_from, parse_amount, pick_over, slip_selection,
                                        state_from_game, usable_odd)

FIX = Path(__file__).parent / "fixtures" / "stake"


def html(nome: str) -> str:
    return (FIX / nome).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def pagina():
    pw_api = pytest.importorskip("playwright.sync_api")
    with pw_api.sync_playwright() as pw:
        try:
            nav = pw.chromium.launch()
        except Exception:
            pytest.skip("sem Chromium do Playwright neste ambiente")
        pg = nav.new_page(viewport={"width": 1280, "height": 900})
        yield pg
        nav.close()


def ler(pg, nome, trecho, *args):
    pg.set_content(html(nome))
    return pg.evaluate(trecho, *args)


# ------------------------------------------------------------------ lista ao vivo
def test_lista_le_times_link_placar_e_minuto(pagina):
    cards = ler(pagina, "lista_ao_vivo.html", js.LIST_CARDS)
    assert len(cards) == 3
    c = cards[0]
    assert c["teams"] == ["AL Faisaly (Jor)", "Al Rayyan SC"]
    assert c["href"].endswith("/46867045-al-faisaly-jor-al-rayyan-sc")    # o jogo, não o link "/sgm"
    assert c["score"] == ["0", "1"] and c["minute"] == 45 and c["live"] is True
    assert cards[2]["suspended"] is True and cards[2]["period"].lower() == "2nd half"


def test_acha_o_jogo_da_tip_por_nome_aproximado(pagina):
    cards = ler(pagina, "lista_ao_vivo.html", js.LIST_CARDS)
    card, sim = best_card(cards, "Al Faisaly", "Al Rayyan", 0.70)
    assert card is not None and "al-faisaly" in card["href"]
    card, _ = best_card(cards, "Flamengo", "Palmeiras", 0.70)
    assert card is None                                                  # jogo que não está ao vivo


def test_caminho_do_jogo_sem_prefixo_de_idioma():
    assert game_path("/pl/sports/soccer/a/b/123-x-y") == "/sports/soccer/a/b/123-x-y"
    assert game_path("/sports/soccer/a/b/123-x-y") == "/sports/soccer/a/b/123-x-y"


# ------------------------------------------------------------------ página do jogo
def test_placar_e_minuto_vem_da_sportradar(pagina):
    info = ler(pagina, "jogo_mercados.html", js.READ_GAME)
    assert info["source"] == "sportradar" and info["score"] == [0, 1]
    st = state_from_game(info)
    assert (st.home_goals, st.away_goals, st.minute, st.live) == (0, 1, 44, True)


def test_le_so_o_total_da_partida_nunca_o_da_equipe(pagina):
    info = ler(pagina, "jogo_mercados.html", js.READ_GAME)
    assert info["market"] == "Asian Total"
    assert info["teamTotals"] == 1                                       # a armadilha existe no HTML real...
    linhas = sorted(o["line"] for o in info["overs"])
    assert linhas == [2.25, 2.5, 2.75]                                   # ...e o "Over 1.5" dela NÃO entra
    assert usable_odd(pick_over(info["overs"], 2.5)) == 1.65
    assert pick_over(info["overs"], 2.5)["selected"] is True
    assert pick_over(info["overs"], 1.5) is None                         # linha da tip (0-1 => 1.5) não oferecida


def test_marca_o_botao_certo_ou_diz_que_a_linha_nao_existe(pagina):
    r = ler(pagina, "jogo_mercados.html", js.TAG_OVER, 2.75)
    assert r["found"] is True
    assert pagina.evaluate("document.querySelector('[data-bot-over]').getAttribute('aria-label')") == "Over 2.75"
    r = pagina.evaluate(js.TAG_OVER, 1.5)
    assert r == {"found": False, "why": "linha não oferecida"}           # NÃO pega o "Over 1.5" do total da equipe
    assert pagina.evaluate("document.querySelectorAll('[data-bot-over]').length") == 0


# ------------------------------------------------------------------ cupom
def test_cupom_real_selecao_odd_campo_e_botao(pagina):
    slip = ler(pagina, "cupom_deslogado.html", js.READ_SLIP)
    assert slip["count"] == 1
    s = slip["selections"][0]
    assert s["name"] == "Over 2.5" and s["market"] == "Asian Total" and s["odd"] == 1.65
    assert slip["input"] == {"value": "", "currency": "usdt"}
    assert [b["text"] for b in slip["buttons"]][-1] == "Register to Bet"
    assert slip_selection(slip, 2.5, "Al Faisaly", "Al Rayyan", 0.70) == s
    assert slip_selection(slip, 2.75, "Al Faisaly", "Al Rayyan", 0.70) is None
    assert slip_selection(slip, 2.5, "Flamengo", "Palmeiras", 0.70) is None


def test_deslogado_o_botao_final_nao_e_o_de_apostar(pagina):
    from bot.casas.stakecom import selectors as S
    pagina.set_content(html("cupom_deslogado.html"))
    assert pagina.evaluate(js.TAG_PLACE, S.PLACE_BUTTON.pattern) == {"found": False}


# ------------------------------------------------------------------ Python puro
def test_minuto_pelo_relogio_total_da_sportradar():
    assert minute_from("83:39", "2nd", None) == 83                       # relógio conta o tempo TOTAL
    assert minute_from("44:54", "1st", None) == 44
    assert minute_from(None, None, 73) == 73


def test_valores_em_dolar():
    assert parse_amount("$1,234.50") == 1234.5
    assert parse_amount("0.00") == 0.0
    assert parse_amount("") is None


def test_linha_suspensa_nao_tem_odd_utilizavel():
    assert usable_odd({"line": 1.5, "odd": 1.9, "suspended": True}) is None
    assert usable_odd(None) is None
