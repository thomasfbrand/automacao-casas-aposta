"""Marcadores aplicados por arquivo, para a suíte padrão ficar rápida e focada.

`pinnacle`: testes de NAVEGADOR da Pinnacle (página simulada e HTML real capturado). Ficam FORA do
`pytest` padrão por decisão do usuário em 25/11/2026 (Pinnacle fora do ar; foco na stake.com).
Não foram apagados nem afrouxados: rode com `pytest -m pinnacle`. Situação conhecida em docs/backlog.md.
Os testes da Pinnacle que não abrem navegador (parser, motor, navegador sob demanda) continuam no padrão.
"""
from pathlib import Path

import pytest

_PINNACLE_NAVEGADOR = {
    "test_fixtures_reais.py",
    "test_js_mock.py",
    "test_place_bet_mock.py",
    "test_live_list.py",
    "test_login_shift.py",
}
_PINNACLE_TESTES_SOLTOS = {"test_login_with_email_code_on_mock"}


def pytest_collection_modifyitems(config, items):
    for item in items:
        arquivo = Path(str(item.fspath)).name
        if arquivo in _PINNACLE_NAVEGADOR or item.originalname in _PINNACLE_TESTES_SOLTOS:
            item.add_marker(pytest.mark.pinnacle)
