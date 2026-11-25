import asyncio
import dataclasses
from contextlib import asynccontextmanager

from bot.config import Config
from bot.engine import Engine
from bot.models import BetResult, GameState
from bot.state import Store

TIP = """Live
MÉTODO {m}
ENTRADA NO OVER {line} GOLS

Liga: BRASIL: BRASILEIRÃO BETANO - RODADA 28
Jogo: Atlético-MG x Chapecoense
Tempo decorrido: 65
Resultando parcial: {hg} X {ag}

1u @1.80
"""


def tip(m=2, line="2.5", hg=1, ag=1):
    return TIP.format(m=m, line=line, hg=hg, ag=ag)


class FakeTab:
    def __init__(self, odds, states=None, found=True):
        self.odds = list(odds)
        self.states = list(states or [])
        self.found = found
        self.bets = []
        self.on_read = None

    async def open_game(self, home, away, attempts=3):
        return self.found

    async def read_state(self):
        if self.states:
            return self.states.pop(0) if len(self.states) > 1 else self.states[0]
        return GameState(minute=70, home_goals=1, away_goals=1, live=True)

    async def read_over_odd(self, line):
        if self.on_read:
            await self.on_read()
        return self.odds.pop(0) if len(self.odds) > 1 else self.odds[0]

    async def place_bet(self, line, stake, min_odd, dry_run):
        self.bets.append((line, stake, min_odd, dry_run))
        return BetResult("accepted", odd=2.0, stake=stake, receipt="123")

    def stalled_for(self):
        return 0.0

    async def maintain(self):
        pass

    async def recover(self):
        return True


class FakeDriver:
    def __init__(self, tab):
        self.tab = tab
        self.ui_lock = asyncio.Lock()

    @asynccontextmanager
    async def open_tab(self):
        yield self.tab

    async def read_balance(self):
        return 1000.0


def make(tmp_path, tab, **over):
    base = dict(unit_value=2.0, dry_run=False, poll_min_s=0.01, poll_max_s=0.02, monitor_timeout_s=1,
                max_stake=500, daily_max_total=2000)
    base.update(over)
    cfg = dataclasses.replace(Config.load(str(tmp_path / "none.env")), **base)
    msgs = []

    async def notify(t):
        msgs.append(t)

    eng = Engine(cfg, FakeDriver(tab), notify, Store(str(tmp_path / "s.db")))
    return eng, msgs


def run(coro):
    return asyncio.run(coro)


def test_waits_for_odd_then_bets_one_unit(tmp_path):
    tab = FakeTab([1.3, 1.5, 1.7, 1.85])

    async def go():
        eng, msgs = make(tmp_path, tab)
        await eng.on_message(1, tip(), None, None)
        await eng.wait_idle()
        return msgs

    msgs = run(go())
    assert tab.bets == [(2.5, 2.0, 1.8, False)]
    done = [m for m in msgs if "APOSTA REALIZADA" in m]
    assert done and "Odd: 2.0" in done[0] and "Valor: R$ 2,00" in done[0] and "Jogo:" in done[0]


def test_never_bets_below_min_odd(tmp_path):
    tab = FakeTab([1.2, 1.4, 1.6])
    tab.states = [GameState(minute=70, home_goals=1, away_goals=1, live=True)] * 5 + \
                 [GameState(minute=90, home_goals=1, away_goals=1, live=True)]

    async def go():
        eng, msgs = make(tmp_path, tab)
        await eng.on_message(1, tip(), None, None)
        await eng.wait_idle()

    run(go())
    assert tab.bets == []


def test_extra_tip_adds_quarter_unit_before_bet(tmp_path):
    tab = FakeTab([1.2, 1.2, 2.0])

    async def go():
        eng, msgs = make(tmp_path, tab)
        await eng.on_message(1, tip(m=2), None, None)
        await asyncio.sleep(0.01)
        await eng.on_message(2, tip(m=6), None, None)
        await eng.on_message(3, tip(m=1), None, None)
        await eng.wait_idle()

    run(go())
    # 1u + 0,25 + 0,25 = 1,5u => R$ 3,00 com 1u = R$ 2
    assert len(tab.bets) == 1 and tab.bets[0][1] == 3.0


def test_extra_tip_after_bet_places_separate_quarter(tmp_path):
    tab = FakeTab([2.0])

    async def go():
        eng, msgs = make(tmp_path, tab)
        await eng.on_message(1, tip(m=2), None, None)
        await asyncio.sleep(0.2)
        await eng.on_message(2, tip(m=6), None, None)
        await asyncio.sleep(0.3)
        await eng.wait_idle()

    run(go())
    stakes = [b[1] for b in tab.bets]
    assert stakes == [2.0, 0.5]


def test_deleted_tip_cancels_before_bet(tmp_path):
    tab = FakeTab([1.2, 1.2, 1.2, 2.0])

    async def go():
        eng, msgs = make(tmp_path, tab)

        async def hook():
            if not getattr(hook, "done", False):
                hook.done = True
                await eng.on_deleted([1])

        tab.on_read = hook
        await eng.on_message(1, tip(), None, None)
        await eng.wait_idle()

    run(go())
    assert tab.bets == []


def test_reply_cancel_stops_bet(tmp_path):
    tab = FakeTab([1.2, 1.2, 2.0])

    async def go():
        eng, msgs = make(tmp_path, tab)
        await eng.on_message(10, tip(), None, None)
        await eng.on_message(11, "Cancelada, não fazer", 10, None)
        await eng.wait_idle()

    run(go())
    assert tab.bets == []


def test_score_change_stops(tmp_path):
    tab = FakeTab([1.2, 2.0], states=[GameState(minute=70, home_goals=1, away_goals=1, live=True),
                                       GameState(minute=71, home_goals=2, away_goals=1, live=True)])

    async def go():
        eng, msgs = make(tmp_path, tab)
        await eng.on_message(1, tip(), None, None)
        await eng.wait_idle()

    run(go())
    assert tab.bets == []


def test_incoherent_tip_ignored(tmp_path):
    tab = FakeTab([2.0])

    async def go():
        eng, msgs = make(tmp_path, tab)
        await eng.on_message(1, tip(line="1.5"), None, None)  # over 1.5 com 1x1
        await eng.wait_idle()
        return msgs

    msgs = run(go())
    assert tab.bets == [] and any("ignorada" in m for m in msgs)


def test_old_tip_ignored(tmp_path):
    import time
    tab = FakeTab([2.0])

    async def go():
        eng, msgs = make(tmp_path, tab)
        await eng.on_message(1, tip(), None, time.time() - 3600)
        await eng.wait_idle()

    run(go())
    assert tab.bets == []


def test_stake_limit_blocks(tmp_path):
    tab = FakeTab([2.0])

    async def go():
        eng, msgs = make(tmp_path, tab)
        eng.cfg = dataclasses.replace(eng.cfg, max_stake=1.0)
        await eng.on_message(1, tip(), None, None)
        await eng.wait_idle()

    run(go())
    assert tab.bets == []


def test_game_not_found(tmp_path):
    tab = FakeTab([2.0], found=False)

    async def go():
        eng, msgs = make(tmp_path, tab)
        await eng.on_message(1, tip(), None, None)
        await eng.wait_idle()
        return msgs

    msgs = run(go())
    assert tab.bets == [] and any("Não achei" in m for m in msgs)


def test_pregame_message_ignored(tmp_path):
    tab = FakeTab([2.0])

    async def go():
        eng, msgs = make(tmp_path, tab)
        await eng.on_message(1, "PRÉ-LIVE\nENTRADA NO OVER 2.5 GOLS", None, None)
        await eng.wait_idle()
        return eng

    eng = run(go())
    assert tab.bets == [] and not eng.sessions


def test_test_mode_adopts_screen_score():
    from bot.engine import Engine
    from bot.models import GameState

    class S:
        expected_goals = 0
        not_live = 0
        unread_score = 0
        line = 2.5

    e = Engine.__new__(Engine)
    import types
    e.cfg = types.SimpleNamespace(give_up_minute=88, require_score_check=True)
    e.allow_line_mismatch = True
    s = S()
    stop, can = e._judge(s, GameState(minute=30, home_goals=1, away_goals=1, live=True))
    assert stop is None and can and s.expected_goals == 2
    stop, can = e._judge(s, GameState(minute=31, home_goals=2, away_goals=1, live=True))
    assert stop and not can                       # depois de adotado, gol novo ainda encerra
    e.allow_line_mismatch = False
    s2 = S()
    stop, _ = e._judge(s2, GameState(minute=30, home_goals=1, away_goals=1, live=True))
    assert stop                                    # na lógica real, placar diferente da tip encerra


def test_extra_tip_after_bet_uses_extra_units(tmp_path):
    tab = FakeTab([1.85, 1.85, 1.85, 1.85, 1.85, 1.85])

    async def go():
        eng, msgs = make(tmp_path, tab)
        await eng.on_message(1, tip(), None, None)
        await eng.wait_idle()                     # apostou 1u e encerrou o fluxo
        await eng.on_message(2, tip(), None, None)
        await eng.wait_idle()
        return msgs

    msgs = run(go())
    assert [b[1] for b in tab.bets] == [2.0, 0.5]   # 1u = R$2; tip extra = 0.25u = R$0.50


class WatchTab(FakeTab):
    """Imita o modo 'monitorar pelo cupom': sequência de (placar_legível?, odd, linha_sumiu_há_s)."""

    def __init__(self, seq):
        super().__init__([None])
        self.seq = list(seq)
        self.gone = 0.0

    async def watch(self, line):
        readable, odd, gone = self.seq.pop(0) if len(self.seq) > 1 else self.seq[0]
        self.gone = gone
        st = GameState(minute=None, live=readable, home_goals=1 if readable else None,
                       away_goals=1 if readable else None)
        return st, odd

    def line_missing_for(self):
        return self.gone


def test_momentary_lock_and_unreadable_score_do_not_stop(tmp_path):
    # placar ok -> 30 leituras "trancado" (sem placar, sem odd) -> destrava com odd boa -> aposta
    seq = [(True, 1.5, 0)] + [(False, None, 0)] * 30 + [(True, 1.9, 0)]
    tab = WatchTab(seq)

    async def go():
        eng, msgs = make(tmp_path, tab, monitor_timeout_s=60)
        await eng.on_message(1, tip(), None, None)
        await eng.wait_idle()
        return msgs

    msgs = run(go())
    assert len(tab.bets) == 1, msgs
    assert not any("Encerrei" in m for m in msgs)


def test_stops_only_when_line_is_gone(tmp_path):
    seq = [(True, 1.5, 0)] * 3 + [(False, None, 10)] * 3 + [(False, None, 999)]
    tab = WatchTab(seq)

    async def go():
        eng, msgs = make(tmp_path, tab, monitor_timeout_s=60)
        await eng.on_message(1, tip(), None, None)
        await eng.wait_idle()
        return msgs

    msgs = run(go())
    assert tab.bets == []
    assert any("não existe mais" in m for m in msgs)


def test_outside_hours_ignores_new_tips(tmp_path):
    tab = FakeTab([2.0])

    async def go():
        eng, msgs = make(tmp_path, tab)
        eng.accepting = False
        await eng.on_message(1, tip(), None, None)
        await eng.wait_idle()
        return msgs

    msgs = run(go())
    assert tab.bets == [] and any("Fora do horário" in m for m in msgs)
