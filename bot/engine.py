"""Cérebro: recebe as mensagens, decide o que fazer e coordena o navegador.

Fluxo de cada tip válida (Live + over coerente com o placar):
  1. abre uma aba, acha o jogo na lista ao vivo e abre todos os mercados;
  2. fica lendo a odd do "Mais de <linha>" sem recarregar a página;
  3. antes de qualquer aposta confere: tip ainda existe no grupo, jogo ao vivo, minuto ok,
     placar da tela == placar da tip, odd >= odd da tip, limites de valor e saldo;
  4. aposta (1u; cada tip extra do mesmo jogo soma +0,25u) ou desiste com aviso.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

from .config import Config
from .models import BetResult, GameState
from .rules import check_limits, stake_for
from .state import Store
from .tip_parser import Tip, is_cancel, parse_tip

log = logging.getLogger("engine")

AliveCheck = Callable[[list[int]], Awaitable[list[int]]]  # recebe ids, devolve os que SUMIRAM do grupo


@dataclass
class Lot:
    msg_id: int
    units: float
    min_odd: float
    received: float
    placed: bool = False
    cancelled: bool = False


@dataclass
class Session:
    key: str
    home: str
    away: str
    line: float
    expected_goals: int
    lots: list[Lot] = field(default_factory=list)
    task: Optional[asyncio.Task] = None
    finished: bool = False
    fail_count: int = 0
    unread_score: int = 0
    not_live: int = 0
    last_alive_check: float = 0.0
    last_score_ok: float = 0.0      # última vez que o placar lido bateu com o da tip

    def pending(self) -> list[Lot]:
        return [l for l in self.lots if not l.placed and not l.cancelled]

    def active(self) -> list[Lot]:
        return [l for l in self.lots if not l.cancelled]

    def has_lot(self, msg_id: int) -> Optional[Lot]:
        return next((l for l in self.lots if l.msg_id == msg_id), None)


class Engine:
    def __init__(self, cfg: Config, driver, notify, store: Store, alive_check: Optional[AliveCheck] = None):
        self.cfg = cfg
        self.driver = driver
        self.notify = notify
        self.store = store
        self.alive_check = alive_check
        self.sessions: dict[str, Session] = {}
        self.bet_games: dict[str, float] = {}   # jogos já apostados nesta execução (chave -> linha)
        self.accepting = True                    # False = fora do horário: não abre tip nova (cancelamentos valem)

    # ------------------------------------------------------------------ entrada de mensagens
    async def on_message(self, msg_id: int, text: str, reply_to: Optional[int] = None,
                         date_ts: Optional[float] = None) -> None:
        if self.store.seen(msg_id):
            return
        self.store.mark_seen(msg_id)
        now = time.time()

        if is_cancel(text):
            await self._cancel_from_message(msg_id, reply_to, now)
            return

        res = parse_tip(text, allow_line_mismatch=getattr(self, 'allow_line_mismatch', False))
        if not res.ok:
            log.info("mensagem %s ignorada: %s", msg_id, res.reason)
            if res.reason.startswith("line_mismatch") or res.reason in ("missing_fields", "bad_game", "no_market"):
                await self.notify(f"⚠️ Tip ignorada ({res.reason}). Nada foi apostado.\n{text[:200]}")
            return
        tip = res.tip
        if not self.accepting:
            log.info("fora do horário de funcionamento: tip ignorada (%s)", tip.describe())
            await self.notify(f"🌙 Fora do horário, tip ignorada: {tip.describe()}")
            return

        if date_ts is not None and now - date_ts > self.cfg.max_tip_age_s:
            await self.notify(f"⌛ Tip velha demais ({int(now - date_ts)}s), ignorada: {tip.describe()}")
            return

        s = self.sessions.get(tip.game_key)
        if s and not s.finished:
            if abs(s.line - tip.line) > 1e-9:
                await self.notify(f"⚠️ Outra tip do mesmo jogo com linha diferente (over {tip.line} vs {s.line}); ignorada.")
                return
            s.lots.append(Lot(msg_id, self.cfg.extra_tip_units, tip.min_odd, now))
            await self.notify(f"➕ Tip extra do mesmo jogo (+{self.cfg.extra_tip_units}u): {tip.describe()}")
            return

        units = tip.units
        if tip.game_key in self.bet_games:
            # o jogo já foi apostado e o fluxo dele encerrou: tip nova do mesmo jogo vale só a unidade extra
            if abs(self.bet_games[tip.game_key] - tip.line) > 1e-9:
                await self.notify(f"⚠️ Tip do mesmo jogo com linha diferente (over {tip.line} vs "
                                  f"{self.bet_games[tip.game_key]}), já apostado; ignorada.")
                return
            units = self.cfg.extra_tip_units
            await self.notify(f"➕ Tip extra de jogo já apostado (+{units}u): {tip.describe()}")
        s = Session(key=tip.game_key, home=tip.home, away=tip.away, line=tip.line, expected_goals=tip.total_goals)
        s.lots.append(Lot(msg_id, units, tip.min_odd, now))
        self.sessions[tip.game_key] = s
        await self.notify(f"🎯 Nova tip: {tip.describe()}")
        s.task = asyncio.create_task(self._run(s), name=f"game:{tip.game_key}")

    async def on_edited(self, msg_id: int, text: str) -> None:
        """Edições só importam se viraram cancelamento; ✅/🔄 pós-jogo são ignorados."""
        if is_cancel(text):
            self.cancel_lot(msg_id, "tip editada para cancelada")

    async def on_deleted(self, ids: list[int]) -> None:
        for i in ids:
            self.cancel_lot(i, "tip apagada do grupo")

    # ------------------------------------------------------------------ cancelamentos
    async def _cancel_from_message(self, msg_id: int, reply_to: Optional[int], now: float) -> None:
        if reply_to:
            if self.cancel_lot(reply_to, "cancelada (resposta do administrador)"):
                return
        recent: Optional[tuple[Session, Lot]] = None
        for s in self.sessions.values():
            for l in s.lots:
                if now - l.received <= self.cfg.cancel_window_s and (recent is None or l.received > recent[1].received):
                    recent = (s, l)
        if recent:
            self.cancel_lot(recent[1].msg_id, "cancelada (mensagem logo após a tip)")
        else:
            log.info("cancelamento sem tip associada: %s", msg_id)

    def cancel_lot(self, msg_id: int, why: str) -> bool:
        for s in self.sessions.values():
            lot = s.has_lot(msg_id)
            if not lot or lot.cancelled:
                continue
            if lot.placed:
                asyncio.ensure_future(self.notify(
                    f"⚠️ {why}, mas a aposta de {s.home} x {s.away} JÁ foi feita. Avalie encerrar (cash out) manualmente."))
            else:
                lot.cancelled = True
                asyncio.ensure_future(self.notify(f"🚫 {why}: não vou apostar em {s.home} x {s.away} ({lot.units}u)."))
            return True
        return False

    async def _verify_alive(self, s: Session) -> None:
        if not self.alive_check or time.time() - s.last_alive_check < 6:
            return
        s.last_alive_check = time.time()
        ids = [l.msg_id for l in s.pending()]
        if not ids:
            return
        try:
            for missing in await self.alive_check(ids):
                self.cancel_lot(missing, "tip apagada do grupo")
        except Exception as exc:
            log.warning("checagem de tip apagada falhou: %s", exc)

    # ------------------------------------------------------------------ monitor de um jogo
    def _judge(self, s: Session, st: GameState) -> tuple[Optional[str], bool]:
        """(motivo para encerrar | None, pode apostar neste ciclo?)"""
        if st.ended:
            return "o jogo terminou", False
        if st.minute is not None and st.minute >= self.cfg.give_up_minute:
            return f"passou do minuto limite ({st.minute}' >= {self.cfg.give_up_minute}')", False
        # Tela "trancada"/sem ao vivo por uns instantes é normal: só encerra se durar muito (~5 min de leituras).
        if not st.live and st.minute is None:
            s.not_live += 1
            if s.not_live >= 100:
                return "o jogo não aparece mais como ao vivo há vários minutos", False
        else:
            s.not_live = 0
        tg = st.total_goals
        if tg is None:
            # não leu o placar agora: segue monitorando. Só aposta se o placar foi confirmado há pouco.
            s.unread_score += 1
            if self.cfg.require_score_check:
                return None, (time.time() - s.last_score_ok) < 90
            return None, True
        s.unread_score = 0
        if getattr(self, "allow_line_mismatch", False) and not getattr(s, "_score_adopted", False):
            # SÓ NO TESTE: vale o placar que está na tela agora (a tip de teste não precisa acertar o placar)
            s._score_adopted = True
            if tg != s.expected_goals:
                log.info("teste: placar da tela %sx%s adotado no lugar do da tip", st.home_goals, st.away_goals)
                s.expected_goals = tg
        if tg == s.expected_goals:
            s.last_score_ok = time.time()
        if tg != s.expected_goals:
            return f"o placar mudou (agora {st.home_goals}x{st.away_goals}); a linha over {s.line} não vale mais", False
        return None, True

    async def _run(self, s: Session) -> None:
        started = time.time()
        title = f"{s.home} x {s.away} (over {s.line})"
        errors = 0
        try:
            async with self.driver.open_tab() as tab:
                if not await tab.open_game(s.home, s.away):
                    await self.notify(f"❌ Não achei {title} ao vivo na {self.cfg.casa}. Nada foi apostado.")
                    return
                await self.notify(f"👀 Monitorando {title}.")
                while True:
                    if not s.active():
                        return
                    if time.time() - started > self.cfg.monitor_timeout_s:
                        await self.notify(f"⏱️ Tempo limite de monitoramento: {title}.")
                        return
                    await self._verify_alive(s)
                    if not s.active():
                        return
                    try:
                        watching = hasattr(tab, "watch")
                        if watching:     # linha selecionada no cupom: só lê odd/placar, sem mexer na página
                            st, odd = await tab.watch(s.line)
                        else:
                            st = await tab.read_state()
                        stop, can_bet = self._judge(s, st)
                        if stop:
                            done = all(l.placed or l.cancelled for l in s.lots)
                            await self.notify(f"🛑 Encerrei {title}: {stop}." + ("" if done else " Nada foi apostado nesta tip."))
                            return
                        if not watching:
                            odd = await tab.read_over_odd(s.line)
                        gone = tab.line_missing_for() if hasattr(tab, "line_missing_for") else 0
                        if gone > self.cfg.line_gone_s:
                            done = all(l.placed or l.cancelled for l in s.lots)
                            await self.notify(f"🛑 Encerrei {title}: a linha over {s.line} não existe mais há "
                                              f"{int(gone)}s (provável gol)." + ("" if done else " Nada foi apostado nesta tip."))
                            return
                        errors = 0
                    except Exception as exc:
                        errors += 1
                        log.warning("erro lendo %s (%s/5): %s", title, errors, exc)
                        if errors >= 5:
                            await self.notify(f"❌ Muitos erros de leitura em {title}; parei. Nada além do que já foi confirmado.")
                            return
                        if errors >= 3:
                            await tab.recover()
                        await asyncio.sleep(2)
                        continue

                    pend = s.pending()
                    if can_bet and pend and odd is not None and odd >= max(l.min_odd for l in pend):
                        outcome = await self._place(s, tab, odd)
                        if outcome == "stop":
                            return
                    elif tab.stalled_for() > (900 if hasattr(tab, "watch") else 240):
                        await tab.recover()        # nada mudou em 15 min (nem odd, nem placar): tela congelou

                    await tab.maintain()
                    await asyncio.sleep(random.uniform(self.cfg.poll_min_s, self.cfg.poll_max_s))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("sessão %s caiu", title)
            await self.notify(f"❌ Erro inesperado em {title}: {exc}. Confira manualmente.")
        finally:
            s.finished = True
            if self.sessions.get(s.key) is s:
                self.sessions.pop(s.key, None)

    async def _place(self, s: Session, tab, seen_odd: float) -> str:
        """Tenta apostar os lotes pendentes. Devolve 'stop' para encerrar a sessão, senão 'continue'."""
        async with self.driver.ui_lock:
            # confere de novo, já com exclusividade do cupom
            if self.alive_check:
                ids = [l.msg_id for l in s.pending()]
                if ids:
                    try:
                        for missing in await self.alive_check(ids):
                            self.cancel_lot(missing, "tip apagada do grupo")
                    except Exception as exc:
                        log.warning("checagem final falhou: %s", exc)
            pend = s.pending()
            if not pend:
                return "continue"
            units = round(sum(l.units for l in pend), 4)
            min_odd = max(l.min_odd for l in pend)
            stake = stake_for(units, self.cfg.unit_value)
            balance = await self.driver.read_balance()
            ok, why = check_limits(stake, self.cfg.max_stake, self.store.spent_today(), self.cfg.daily_max_total,
                                   None if self.cfg.dry_run else balance)
            if not ok:
                for l in pend:
                    l.cancelled = True
                await self.notify(f"⛔ Não apostei em {s.home} x {s.away}: {why}.")
                return "stop"

            res: BetResult = await tab.place_bet(s.line, stake, min_odd, self.cfg.dry_run)
            game = f"{s.home} x {s.away}"
            log.info("resultado: %s", res)

            if res.status == "accepted":
                for l in pend:
                    l.placed = True
                self.store.add_bet(game, s.line, res.odd, res.stake or stake, "accepted", res.receipt or "")
                valor = f"{(res.stake or stake):.2f}".replace(".", ",")
                await self.notify("✅ APOSTA REALIZADA\n"
                                  f"Jogo: {s.home} x {s.away}\n"
                                  f"Mercado: Mais de {s.line:g} gols\n"
                                  f"Odd: {res.odd}\n"
                                  f"Valor: R$ {valor} ({units:g}u)\n"
                                  f"Bilhete: #{res.receipt or '?'}")
                self.bet_games[s.key] = s.line
                if not s.pending():
                    log.info("aposta feita: encerrando o fluxo de %s", game)
                    return "stop"
                return "continue"
            if res.status == "dry_run_ok":
                for l in pend:
                    l.placed = True
                self.store.add_bet(game, s.line, res.odd, stake, "dry_run", "", res.detail)
                await self.notify(f"🧪 DRY_RUN: apostaria R$ {stake:.2f} ({units}u) em {game} over {s.line} @ {res.odd}. {res.detail}")
                return "continue"
            if res.status in ("odd_low", "unavailable"):
                log.info("sem aposta agora (%s): %s", res.status, res.detail)
                await asyncio.sleep(random.uniform(3, 6))
                return "continue"
            if res.status == "unknown":
                for l in pend:
                    l.placed = True
                self.store.add_bet(game, s.line, res.odd, res.stake or stake, "unknown", "", res.detail)
                await self.notify(f"❓ Não sei se a aposta entrou em {game}: {res.detail}")
                return "stop"
            # failed
            s.fail_count += 1
            await self.notify(f"⚠️ Falha ao apostar em {game}: {res.detail} (tentativa {s.fail_count}/2)")
            if s.fail_count >= 2:
                await self.notify(f"🛑 Desisti de {game} após 2 falhas. Nada foi confirmado.")
                return "stop"
            return "continue"

    # ------------------------------------------------------------------ utilidades
    async def wait_idle(self) -> None:
        tasks = [s.task for s in list(self.sessions.values()) if s.task]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
