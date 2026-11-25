"""Regressão contra HTML REAL capturado da Pinnacle (tests/fixtures/).

Cada arquivo aqui é um instante real de uma execução de 21/09/2026, com os dados
pessoais removidos. Se alguém "simplificar" os seletores e quebrar a leitura do site
de verdade, estes testes falham sem precisar abrir a Pinnacle.

Como acrescentar um caso: ver docs/testes.md.
"""
from pathlib import Path

import pytest

from bot.casas.pinnacle import js

FIXTURES = Path(__file__).parent / "fixtures"


def carregar(nome: str) -> str:
    return (FIXTURES / nome).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def pagina():
    """Abre uma página do Chromium reaproveitada por todos os casos."""
    pw_api = pytest.importorskip("playwright.sync_api")
    with pw_api.sync_playwright() as pw:
        try:
            nav = pw.chromium.launch()
        except Exception:
            pytest.skip("sem Chromium do Playwright neste ambiente")
        pg = nav.new_page(viewport={"width": 421, "height": 868})
        yield pg
        nav.close()


def avaliar(pg, html: str, trecho: str, *args):
    pg.set_content(html)
    return pg.evaluate(trecho, *args)


def test_le_selecao_odd_e_placar_do_cupom_real(pagina):
    r = avaliar(pagina, carregar("cupom_com_selecao.html"), js.SLIP_SELECTION, 1.5)
    assert r["found"] and r["name"] == "Mais de 1.5"
    assert r["odd"] == 1.819                      # odd de verdade daquele instante
    assert r["status"] == "OK" and r["minStake"] == 0.75
    assert r["score"] == [0, 0]                   # placar vem do "[0-0]" no nome do evento
    assert r["live"] is True


def test_ignora_linha_que_nao_e_a_da_tip(pagina):
    r = avaliar(pagina, carregar("cupom_com_selecao.html"), js.SLIP_SELECTION, 2.5)
    assert not r["found"]                          # o cupom tem "Mais de 1.5", não 2.5


def test_acha_o_campo_de_valor_no_cupom_real(pagina):
    r = avaliar(pagina, carregar("cupom_valor_digitado.html"), js.TAG_STAKE_IN_SHEET)
    assert r and r["input"] is True
    assert "stake" in r["desc"].lower()


def test_odds_changed_nao_e_motivo_para_desistir(pagina):
    """A casa devolveu a aposta mudando a odd: status ODDS_CHANGE, seleção ainda no cupom."""
    r = avaliar(pagina, carregar("cupom_odds_changed.html"), js.SLIP_SELECTION, 2.5)
    assert r["found"] and r["odd"] == 2.2
    assert r["status"] in ("OK", "ODDS_CHANGE")   # nenhum deles impede apostar


def test_reconhece_aposta_aceita_e_o_numero_do_bilhete(pagina):
    from bot.casas.pinnacle import selectors as S

    pagina.set_content(carregar("cupom_aposta_aceita.html"))
    texto = pagina.evaluate(js.BODY_TEXT)
    m = S.ACCEPTED_RE.search(texto)
    assert m and m.group(1) == "3127405810"       # bilhete real da aposta aceita


def test_painel_do_cupom_aberto_e_vazio_e_detectado(pagina):
    r = avaliar(pagina, carregar("painel_cupom_vazio.html"), js.SHEET_STATE)
    assert r["open"] is True and r["empty"] is True


def test_acha_o_botao_de_fechar_do_painel(pagina):
    r = avaliar(pagina, carregar("painel_cupom_vazio.html"), js.TAG_SHEET_CLOSE)
    assert r is not None                           # bug 9: a classe muda conforme a seleção


def test_popup_limpar_boletim_tem_sim_e_cancelar(pagina):
    r = avaliar(pagina, carregar("modal_limpar_boletim.html"), js.MODAL_STATE)
    assert r and "Limpar boletim" in r["text"]
    assert any("Sim" == b.strip() for b in r["buttons"])
    assert any("Cancelar" == b.strip() for b in r["buttons"])
