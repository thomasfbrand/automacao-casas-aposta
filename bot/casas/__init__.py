"""Registro das casas de apostas apoiadas.

Para adicionar uma casa: crie o pacote em bot/casas/<nome>/ seguindo `base.py`
e acrescente uma linha em `_CASAS`.
"""
from __future__ import annotations

_CASAS = {
    "pinnacle": ("bot.casas.pinnacle.driver", "PinnacleDriver"),
    # "stakecom" e não "stake": a palavra "stake" (valor apostado) já aparece no motor e o teste de contrato
    # reprova motor que cita nome de casa. Também deixa espaço para uma futura stake.bet.br.
    "stakecom": ("bot.casas.stakecom.driver", "StakeComDriver"),
}


def casas_disponiveis() -> list[str]:
    return sorted(_CASAS)


def get_casa(nome: str):
    """Devolve a CLASSE do driver da casa (instancie com (cfg, notify))."""
    import importlib

    chave = (nome or "").strip().lower()
    if chave not in _CASAS:
        raise SystemExit(f"Casa '{nome}' não existe. Disponíveis: {', '.join(casas_disponiveis())}")
    modulo, classe = _CASAS[chave]
    return getattr(importlib.import_module(modulo), classe)
