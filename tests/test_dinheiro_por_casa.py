"""Dinheiro por casa: cada casa tem a sua moeda, os seus valores no .env e o seu teto do dia.

O risco que estes testes travam: rodar a stake.com (US$) com o UNIT_VALUE=350 que era em REAIS,
ou somar no teto diário R$ da Pinnacle com US$ da stake.com.
"""
import asyncio
import sqlite3
from types import SimpleNamespace

import pytest

from bot.config import Config
from bot.engine import Engine, Lot, Session
from bot.models import BetResult
from bot.rules import check_limits
from bot.state import Store

VARS = ("CASA", "UNIT_VALUE", "MAX_STAKE", "DAILY_MAX_TOTAL", "STAKECOM_UNIT_VALUE", "STAKECOM_MAX_STAKE",
        "STAKECOM_DAILY_MAX_TOTAL", "STAKECOM_PROFILE_DIR", "STAKECOM_FRESH_SESSION", "FRESH_SESSION", "PROFILE_DIR")


@pytest.fixture
def env(monkeypatch):
    for v in VARS:
        monkeypatch.delenv(v, raising=False)
    return monkeypatch


def test_valores_da_casa_tem_prioridade_e_sao_marcados(env):
    env.setenv("CASA", "stakecom")
    env.setenv("UNIT_VALUE", "350")                     # em reais, da Pinnacle
    env.setenv("STAKECOM_UNIT_VALUE", "0.5")
    env.setenv("STAKECOM_MAX_STAKE", "5")
    env.setenv("STAKECOM_DAILY_MAX_TOTAL", "20")
    env.setenv("STAKECOM_FRESH_SESSION", "false")
    env.setenv("STAKECOM_PROFILE_DIR", "browser_profile_stakecom")
    cfg = Config.load("/nonexistent")
    assert (cfg.unit_value, cfg.max_stake, cfg.daily_max_total) == (0.5, 5.0, 20.0)
    assert cfg.money_from_casa is True
    assert cfg.fresh_session is False and cfg.profile_dir == "browser_profile_stakecom"


def test_sem_valores_da_casa_cai_no_geral_e_nao_marca(env):
    env.setenv("CASA", "pinnacle")
    env.setenv("UNIT_VALUE", "1")
    cfg = Config.load("/nonexistent")
    assert cfg.unit_value == 1.0 and cfg.money_from_casa is False


def test_stakecom_recusa_ligar_com_valores_em_reais(env):
    env.setenv("CASA", "stakecom")
    env.setenv("UNIT_VALUE", "350")
    env.setenv("STAKECOM_UNIT_VALUE", "0.5")             # faltam os tetos em US$
    from bot.casas.stakecom.driver import StakeComDriver
    with pytest.raises(SystemExit, match="STAKECOM_UNIT_VALUE"):
        StakeComDriver(Config.load("/nonexistent"), None)


def test_teto_do_dia_e_por_casa(tmp_path):
    st = Store(str(tmp_path / "s.db"))
    st.add_bet("A x B", 2.5, 1.8, 100.0, "accepted", casa="pinnacle")
    st.add_bet("C x D", 1.5, 1.9, 3.0, "accepted", casa="stakecom")
    st.add_bet("E x F", 1.5, 1.9, 2.0, "unknown", casa="stakecom")
    st.add_bet("G x H", 1.5, 1.9, 9.0, "dry_run", casa="stakecom")
    assert st.spent_today("stakecom") == 5.0             # dry-run não conta; R$ da Pinnacle não entra
    assert st.spent_today("pinnacle") == 100.0


def test_banco_antigo_ganha_a_coluna_casa_sem_perder_apostas(tmp_path):
    caminho = str(tmp_path / "antigo.db")
    db = sqlite3.connect(caminho)
    db.execute("CREATE TABLE bets(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, day TEXT, game TEXT, line REAL,"
               " odd REAL, stake REAL, status TEXT, receipt TEXT, detail TEXT)")
    from datetime import date
    db.execute("INSERT INTO bets(ts, day, game, line, odd, stake, status) VALUES(0, ?, 'X', 2.5, 1.8, 1.0, 'accepted')",
               (date.today().isoformat(),))
    db.commit()
    db.close()
    st = Store(caminho)
    assert st.spent_today("pinnacle") == 1.0             # apostas de antes eram da Pinnacle
    assert st.spent_today("stakecom") == 0.0


def test_mensagens_de_teto_usam_a_moeda_da_casa():
    ok, why = check_limits(6.0, 5.0, 0.0, 20.0, None, "US$")
    assert not ok and "US$ 6.00" in why and "R$" not in why


def test_motor_avisa_e_grava_na_moeda_e_na_casa_certas(tmp_path):
    avisos = []

    async def notify(m):
        avisos.append(m)

    class Aba:
        async def place_bet(self, line, stake, min_odd, dry_run):
            return BetResult("accepted", odd=1.9, stake=stake, receipt="abc123")

    driver = SimpleNamespace(moeda="US$", ui_lock=asyncio.Lock())

    async def saldo():
        return None
    driver.read_balance = saldo

    import dataclasses
    cfg = dataclasses.replace(Config.load("/nonexistent"), casa="stakecom", unit_value=0.5, max_stake=5.0,
                              daily_max_total=20.0, dry_run=False, money_from_casa=True)
    store = Store(str(tmp_path / "s.db"))
    eng = Engine(cfg, driver, notify, store)
    s = Session(key="k", home="A", away="B", line=1.5, expected_goals=1)
    s.lots.append(Lot(1, 1.0, 1.8, 0.0))
    assert asyncio.run(eng._place(s, Aba(), 1.9)) == "stop"
    assert any("Valor: US$ 0,50" in a for a in avisos), avisos
    assert store.spent_today("stakecom") == 0.5
