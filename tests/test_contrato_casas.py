"""Regra de arquitetura virada em teste: toda casa registrada cumpre bot/casas/base.py.

Sem isso, uma casa nova "quase pronta" passa despercebida e explode em produção.
"""
import inspect

import pytest

from bot.casas import casas_disponiveis, get_casa
from bot.casas.base import Aba, Casa

METODOS_CASA = [m for m in dir(Casa) if not m.startswith("_")]
METODOS_ABA = [m for m in dir(Aba) if not m.startswith("_")]


@pytest.mark.parametrize("nome", casas_disponiveis())
def test_driver_da_casa_tem_todos_os_metodos(nome):
    classe = get_casa(nome)
    faltando = [m for m in METODOS_CASA if not hasattr(classe, m)]
    assert not faltando, f"{classe.__name__} não implementa: {faltando}"


@pytest.mark.parametrize("nome", casas_disponiveis())
def test_aba_da_casa_tem_todos_os_metodos(nome):
    modulo = inspect.getmodule(get_casa(nome))
    abas = [o for n, o in vars(modulo).items()
            if inspect.isclass(o) and o.__module__ == modulo.__name__ and hasattr(o, "place_bet")]
    assert abas, f"{modulo.__name__} não define nenhuma classe de aba (com place_bet)"
    for aba in abas:
        faltando = [m for m in METODOS_ABA if not hasattr(aba, m)]
        assert not faltando, f"{aba.__name__} não implementa: {faltando}"


def test_motor_nao_conhece_nenhuma_casa_pelo_nome():
    """O motor é genérico: citar uma casa dentro dele quebra o modelo multi-casa."""
    from pathlib import Path

    for arquivo in ("bot/engine.py", "bot/rules.py", "bot/tip_parser.py", "bot/matching.py"):
        texto = Path(arquivo).read_text(encoding="utf-8").lower()
        for casa in casas_disponiveis():
            assert casa not in texto, f"{arquivo} cita '{casa}': mova isso para bot/casas/{casa}/"
