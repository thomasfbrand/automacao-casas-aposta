"""E2E sem navegador: mensagem do Telegram -> aposta, passando por TODOS os componentes.

Os testes unitários testam cada peça isolada; este liga o caminho inteiro
(telegram_client -> engine -> tip_parser -> matching -> rules -> casa -> notifier -> SQLite)
com uma casa falsa que cumpre bot/casas/base.py. Pega defeito de fronteira: assinatura
trocada, unidade calculada errado, aviso que não sai, aposta gravada errado.
"""
from __future__ import annotations

import asyncio
import dataclasses
import datetime
import sqlite3
import types
from contextlib import asynccontextmanager

import pytest

from bot.config import Config
from bot.engine import Engine
from bot.models import BetResult, GameState
from bot.notifier import Notifier
from bot.state import Store

TIP = """Live
MÉTODO 2
ENTRADA NO OVER 2.5 GOLS

Liga: SÉRVIA - PRVA LIGA
Jogo: Spartak Subotica x Vozdovac
Tempo decorrido: 65
Resultando parcial: 1 X 1

1u @1.80
"""


class AbaFalsa:
    """Casa que começa com odd baixa e sobe até passar do mínimo."""

    def __init__(self, odds, placar=(1, 1), odd_depois=None):
        self.odds = list(odds)
        self.placar = placar
        self.apostas = []
        self.jogo = None
        # sincronização para testes sem corrida de tempo:
        self.leu_uma_vez = asyncio.Event()   # a aba avisa que o monitor começou
        self.liberar = asyncio.Event()       # o teste decide quando a odd sobe
        self.odd_depois = odd_depois         # odd usada depois de liberar

    async def open_game(self, home, away, attempts=3):
        self.jogo = (home, away)
        return True

    async def watch(self, line):
        self.leu_uma_vez.set()
        if self.odd_depois is not None:
            odd = self.odd_depois if self.liberar.is_set() else self.odds[0]
            st = GameState(minute=70, home_goals=self.placar[0], away_goals=self.placar[1], live=True)
            return st, odd
        odd = self.odds.pop(0) if len(self.odds) > 1 else self.odds[0]
        st = GameState(minute=70, home_goals=self.placar[0], away_goals=self.placar[1], live=True)
        return st, odd

    async def read_state(self):
        return GameState(minute=70, home_goals=self.placar[0], away_goals=self.placar[1], live=True)

    async def read_over_odd(self, line):
        return self.odds[0]

    def line_missing_for(self):
        return 0.0

    def stalled_for(self):
        return 0.0

    async def place_bet(self, line, stake, min_odd, dry_run):
        self.apostas.append({"linha": line, "valor": stake, "min_odd": min_odd, "dry_run": dry_run})
        return BetResult("accepted", odd=min_odd + 0.05, stake=stake, receipt="E2E-123")

    async def recover(self):
        return True

    async def maintain(self):
        pass


class CasaFalsa:
    def __init__(self, aba):
        self.aba = aba
        self.ui_lock = asyncio.Lock()

    @asynccontextmanager
    async def open_tab(self):
        yield self.aba

    async def ensure_started(self):
        pass

    async def stop(self):
        pass

    async def close_if_idle(self, idle_s):
        return False

    async def read_balance(self, page=None):
        return 500.0


def montar(tmp_path, aba, **over):
    base = dict(unit_value=10.0, dry_run=False, poll_min_s=0.01, poll_max_s=0.02,
                monitor_timeout_s=5, max_stake=500, daily_max_total=2000)
    base.update(over)
    cfg = dataclasses.replace(Config.load(str(tmp_path / "vazio.env")), **base)
    avisos = []
    notificador = Notifier("me")
    notificador.client = types.SimpleNamespace(
        send_message=lambda alvo, texto: avisos.append(texto) or asyncio.sleep(0))
    store = Store(str(tmp_path / "estado.db"))
    return Engine(cfg, CasaFalsa(aba), notificador, store), avisos, cfg, store


def test_e2e_mensagem_do_telegram_vira_aposta(tmp_path):
    """Caminho feliz completo, entrando pelo mesmo handler que o Telegram usa."""
    from bot import telegram_client as tg

    aba = AbaFalsa([1.50, 1.60, 1.75, 1.85])
    engine, avisos, cfg, store = montar(tmp_path, aba)

    handlers = {}

    class ClienteFalso:
        def on(self, evento):
            def deco(fn):
                handlers[type(evento).__name__] = fn
                return fn
            return deco

    tg.register_handlers(ClienteFalso(), "grupo", engine)
    msg = types.SimpleNamespace(id=1, raw_text=TIP, reply_to=None,
                                date=datetime.datetime.now(datetime.timezone.utc))

    async def rodar():
        await handlers["NewMessage"](types.SimpleNamespace(message=msg))
        await engine.wait_idle()

    asyncio.run(rodar())

    assert aba.jogo == ("Spartak Subotica", "Vozdovac")        # casou o nome do jogo
    assert len(aba.apostas) == 1, aba.apostas
    aposta = aba.apostas[0]
    assert aposta["linha"] == 2.5                               # linha = gols + 0,5
    assert aposta["valor"] == 10.0                              # 1u * UNIT_VALUE
    assert aposta["min_odd"] == 1.80                            # odd da tip é o mínimo
    assert aposta["dry_run"] is False

    texto = "\n".join(avisos)
    assert "APOSTA REALIZADA" in texto and "E2E-123" in texto and "R$ 10,00" in texto

    linhas = sqlite3.connect(str(tmp_path / "estado.db")).execute(
        "select game, line, stake, status, receipt from bets").fetchall()
    assert linhas == [("Spartak Subotica x Vozdovac", 2.5, 10.0, "accepted", "E2E-123")]


def test_e2e_cancelamento_no_grupo_impede_a_aposta(tmp_path):
    """Tip chega, monitor começa com odd baixa, admin responde 'cancelada'.
    Só então a odd sobe acima do mínimo: mesmo assim nada pode ser apostado."""
    from bot import telegram_client as tg

    aba = AbaFalsa([1.50], odd_depois=1.90)
    engine, avisos, _cfg, _store = montar(tmp_path, aba)
    handlers = {}

    class ClienteFalso:
        def on(self, evento):
            def deco(fn):
                handlers[type(evento).__name__] = fn
                return fn
            return deco

    tg.register_handlers(ClienteFalso(), "grupo", engine)
    agora = datetime.datetime.now(datetime.timezone.utc)

    async def rodar():
        await handlers["NewMessage"](types.SimpleNamespace(
            message=types.SimpleNamespace(id=10, raw_text=TIP, reply_to=None, date=agora)))
        await asyncio.wait_for(aba.leu_uma_vez.wait(), timeout=5)   # o monitor já está rodando
        await handlers["NewMessage"](types.SimpleNamespace(
            message=types.SimpleNamespace(id=11, raw_text="cancelada", date=agora,
                                          reply_to=types.SimpleNamespace(reply_to_msg_id=10))))
        aba.liberar.set()                                            # agora a odd passa do mínimo
        await engine.wait_idle()

    asyncio.run(rodar())
    assert aba.apostas == [], "apostou numa tip cancelada"
    assert any("cancel" in a.lower() for a in avisos)


def test_e2e_tip_incoerente_nao_vira_aposta(tmp_path):
    """over 1.5 com placar 1x1 (linha != gols+0,5): vira aviso, não aposta."""
    from bot import telegram_client as tg

    aba = AbaFalsa([2.50])
    engine, avisos, _cfg, _store = montar(tmp_path, aba)
    handlers = {}

    class ClienteFalso:
        def on(self, evento):
            def deco(fn):
                handlers[type(evento).__name__] = fn
                return fn
            return deco

    tg.register_handlers(ClienteFalso(), "grupo", engine)

    async def rodar():
        await handlers["NewMessage"](types.SimpleNamespace(
            message=types.SimpleNamespace(id=20, raw_text=TIP.replace("OVER 2.5", "OVER 1.5"),
                                          reply_to=None,
                                          date=datetime.datetime.now(datetime.timezone.utc))))
        await engine.wait_idle()

    asyncio.run(rodar())
    assert aba.apostas == []
    assert any("ignorada" in a.lower() for a in avisos)
