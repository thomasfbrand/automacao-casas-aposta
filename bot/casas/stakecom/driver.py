"""Automação do navegador na stake.com (Playwright). Cumpre bot/casas/base.py.

Diferenças em relação à Pinnacle (detalhes e porquês em CONSTRAINTS.md):
- sem iframe: tudo está na página, com data-testid estáveis;
- valores em US$ (cripto/USDT): o motor recebe a moeda por `moeda` e os valores vêm de STAKECOM_* no .env;
- login pelo Google NÃO é automatizado: perfil persistente; se a sessão cair, avisa e espera você logar na janela;
- o mercado da tip é o "Asian Total" (em linha .5 é igual ao over comum) e a linha gols+0,5 às vezes
  ainda não é oferecida: isso NÃO é sinal de gol (line_missing_for só conta depois de a linha ter aparecido);
- monitorar não exige o cupom: odd e placar são lidos do DOM sem rolar nem clicar.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from ...config import Config
from ...models import BetResult, GameState
from . import js, selectors as S
from .parsing import (best_card, format_stake, game_path, parse_amount, pick_over, slip_selection, state_from_game,
                      usable_odd)

log = logging.getLogger("stakecom")

BASE_URL = "https://stake.com"
RESULT_TIMEOUT_S = 30          # espera pela resposta da casa depois de clicar em apostar (sem resposta = "unknown")


class LoginError(RuntimeError):
    pass


class StakeComDriver:
    moeda = "US$"

    def __init__(self, cfg: Config, notify):
        if not cfg.money_from_casa:
            raise SystemExit("Na stake.com os valores são em US$. Defina no .env: STAKECOM_UNIT_VALUE, "
                             "STAKECOM_MAX_STAKE e STAKECOM_DAILY_MAX_TOTAL (o UNIT_VALUE em reais NÃO vale aqui).")
        self.cfg = cfg
        self.notify = notify
        self._pw = None
        self.context = None
        self.anchor = None
        self.ui_lock = asyncio.Lock()      # o cupom é único na conta: uma aposta por vez
        self._start_lock = asyncio.Lock()
        self.started = False
        self.open_tabs = 0
        self.last_used = time.time()
        self.logged_in = False

    # ---------------------------------------------------------------- ciclo de vida
    async def start(self) -> None:
        from playwright.async_api import async_playwright

        if self.cfg.fresh_session:
            import tempfile
            self._tmp_profile = tempfile.mkdtemp(prefix="stakecom_bot_")
            profile = self._tmp_profile
        else:
            self._tmp_profile = None
            profile = str(Path(self.cfg.profile_dir).resolve())
        self._pw = await async_playwright().start()
        kwargs = dict(user_data_dir=profile, headless=self.cfg.headless, viewport=S.VIEWPORT,
                      locale="en-US", timezone_id="America/Sao_Paulo")
        if self.cfg.chrome_channel:
            kwargs["channel"] = self.cfg.chrome_channel
        self.context = await self._pw.chromium.launch_persistent_context(**kwargs)
        self.anchor = self.context.pages[0] if self.context.pages else await self.context.new_page()
        await self.anchor.goto(S.HOME_URL, wait_until="domcontentloaded")
        await self.ensure_logged_in(self.anchor)

    async def ensure_started(self) -> None:
        async with self._start_lock:
            if self.started and self.context is not None:
                try:
                    _ = self.context.pages
                    return
                except Exception:
                    self.started = False
            log.info("tip recebida: abrindo a stake.com")
            await self.notify("🔐 Abrindo a stake.com para a tip…")
            try:
                await self.start()
                self.started = True
                self.last_used = time.time()
            except Exception:
                await self._stop_quiet()
                raise

    async def close_if_idle(self, idle_s: float) -> bool:
        async with self._start_lock:
            if not self.started or self.open_tabs > 0 or time.time() - self.last_used < idle_s:
                return False
            log.info("sem tips há %d min: fechando o navegador", idle_s // 60)
            await self._stop_quiet()
            return True

    async def _stop_quiet(self) -> None:
        try:
            await self.stop()
        except Exception as exc:
            log.debug("stop: %s", exc)

    async def stop(self) -> None:
        self.started = False
        try:
            if self.context:
                await self.context.close()
        finally:
            self.context = None
            if self._pw:
                await self._pw.stop()
                self._pw = None
            tmp = getattr(self, "_tmp_profile", None)
            if tmp:
                import shutil
                shutil.rmtree(tmp, ignore_errors=True)

    @asynccontextmanager
    async def open_tab(self):
        await self.ensure_started()
        try:
            page = await self.context.new_page()
        except Exception:
            log.warning("navegador fechado; reabrindo")
            self.started = False
            await self.ensure_started()
            page = await self.context.new_page()
        self.open_tabs += 1
        tab = StakeComTab(self, page)
        try:
            yield tab
        finally:
            self.open_tabs -= 1
            self.last_used = time.time()
            try:
                await page.close()
            except Exception:
                pass

    # ---------------------------------------------------------------- sessão
    async def is_logged_out(self, page) -> bool:
        try:
            await page.wait_for_function(js.SESSION_KNOWN, timeout=30000)
        except Exception:
            pass
        return bool(await page.evaluate(js.LOGGED_OUT))

    async def ensure_logged_in(self, page) -> None:
        """Perfil persistente: o login (pelo Google) é feito por VOCÊ na janela, uma vez.
        Se a sessão caiu, avisa no Telegram e espera MANUAL_INTERVENTION_TIMEOUT_S. Em DRY_RUN segue deslogado."""
        if not await self.is_logged_out(page):
            self.logged_in = True
            return
        if self.cfg.dry_run:
            self.logged_in = False
            log.info("stake.com deslogada; DRY_RUN segue sem login (nenhuma aposta é confirmada)")
            await self.notify("ℹ️ stake.com deslogada. Em DRY_RUN sigo assim; para apostar de verdade, "
                              "faça login na janela do robô uma vez.")
            return
        limite = self.cfg.manual_intervention_timeout_s
        await self.notify(f"🔐 A stake.com está DESLOGADA. Faça login na janela do robô (pode ser pelo Google). "
                          f"Espero até {limite // 60} min.")
        fim = time.time() + limite
        while time.time() < fim:
            await asyncio.sleep(5)
            try:
                if not await page.evaluate(js.LOGGED_OUT):
                    self.logged_in = True
                    await self.notify("✅ Login na stake.com feito. Sigo com a tip.")
                    return
            except Exception:
                pass
        raise LoginError("stake.com continua deslogada depois do tempo de espera")

    async def read_balance(self, page=None) -> Optional[float]:
        """NÃO MAPEADO (precisa estar logado): por enquanto devolve None, e o contrato diz que None não bloqueia.
        Os tetos MAX_STAKE e DAILY_MAX_TOTAL continuam valendo."""
        return None


class StakeComTab:
    """Uma aba dedicada a UM jogo."""

    def __init__(self, driver: StakeComDriver, page):
        self.d = driver
        self.cfg = driver.cfg
        self.page = page
        self.home = self.away = ""
        self.url: Optional[str] = None
        self._last_change = time.time()
        self._last_sig = None
        self._line_seen = False
        self._line_missing_since: Optional[float] = None
        self._avisou_linha = False
        self._cookie_ok = False

    # ---------------------------------------------------------------- achar o jogo
    async def _read_cards(self) -> list[dict]:
        try:
            await self.page.wait_for_selector(S.CARD, timeout=20000)
        except Exception:
            return []
        return await self.page.evaluate(js.LIST_CARDS)

    async def open_game(self, home: str, away: str, attempts: int = 3) -> bool:
        self.home, self.away = home, away
        for tentativa in range(1, attempts + 1):
            try:
                await self.page.goto(S.LIVE_SOCCER_URL, wait_until="domcontentloaded")
                card, sim = None, 0.0
                for passo in range(12):                 # a lista pode carregar aos poucos: lê, rola, lê de novo
                    card, sim = best_card(await self._read_cards(), home, away, self.cfg.match_threshold)
                    if card:
                        break
                    await self.page.mouse.wheel(0, int(S.VIEWPORT["height"] * 0.6))
                    await asyncio.sleep(0.6)
                if not card:
                    log.info("jogo %s x %s não está na lista ao vivo (tentativa %d, melhor similaridade %.2f)",
                             home, away, tentativa, sim)
                    await asyncio.sleep(2)
                    continue
                self.url = BASE_URL + game_path(card["href"])
                log.info("abrindo %s x %s (%s x %s, sim %.2f): %s", home, away, *card["teams"][:2], sim, self.url)
                await self.page.goto(self.url, wait_until="domcontentloaded")
                if await self._wait_game():
                    self._last_change = time.time()
                    return True
            except Exception as exc:
                log.warning("abrir jogo (tentativa %d): %s", tentativa, exc)
            await asyncio.sleep(2)
        return False

    async def _wait_game(self, timeout: float = 25.0) -> bool:
        fim = time.time() + timeout
        while time.time() < fim:
            info = await self.page.evaluate(js.READ_GAME)
            if info.get("score") or info.get("market"):
                return True
            await asyncio.sleep(0.8)
        return False

    # ---------------------------------------------------------------- leitura
    async def _read(self) -> dict:
        return await self.page.evaluate(js.READ_GAME)

    async def read_state(self) -> GameState:
        return state_from_game(await self._read())

    async def read_over_odd(self, line: float) -> Optional[float]:
        return usable_odd(pick_over((await self._read()).get("overs") or [], line))

    def line_missing_for(self) -> float:
        """Só conta DEPOIS de a linha ter aparecido: na stake.com a linha gols+0,5 às vezes ainda não é oferecida
        (a casa mostra ~3 linhas em volta da principal), e isso não é sinal de gol."""
        return 0.0 if self._line_missing_since is None else time.time() - self._line_missing_since

    def stalled_for(self) -> float:
        return time.time() - self._last_change

    async def watch(self, line: float) -> tuple[GameState, Optional[float]]:
        """Lê placar e odd do DOM. Não rola, não clica, não recarrega."""
        info = await self._read()
        st = state_from_game(info)
        over = pick_over(info.get("overs") or [], line)
        odd = usable_odd(over)
        if over is not None:
            self._line_seen = True
            self._line_missing_since = None
        elif self._line_seen:
            if self._line_missing_since is None:
                self._line_missing_since = time.time()
        elif not self._avisou_linha:
            self._avisou_linha = True
            linhas = ", ".join(f"{o['line']:g}" for o in info.get("overs") or []) or "nenhuma"
            log.info("linha over %s ainda não oferecida (agora: %s)", line, linhas)
            await self.d.notify(f"⏳ {self.home} x {self.away}: a stake.com ainda não oferece over {line:g} "
                                f"(linhas agora: {linhas}). Continuo esperando.")
        sig = (st.minute, st.home_goals, st.away_goals, odd)
        if sig != self._last_sig:
            self._last_sig = sig
            self._last_change = time.time()
        return st, odd

    async def recover(self) -> bool:
        log.warning("recuperando aba: recarregando o jogo")
        try:
            if self.url:
                await self.page.goto(self.url, wait_until="domcontentloaded")
                ok = await self._wait_game()
            else:
                ok = await self.open_game(self.home, self.away, attempts=2)
            if not self.cfg.dry_run:
                await self.d.ensure_logged_in(self.page)
        except Exception as exc:
            log.error("recover: %s", exc)
            return False
        self._last_change = time.time()
        return ok

    async def maintain(self) -> None:
        """Só o banner de cookies (fica embaixo e pode cobrir o cupom). Não mexe no jogo."""
        if self._cookie_ok:
            return
        try:
            btn = self.page.locator(S.COOKIE_ACCEPT)
            if await btn.count() and await btn.first.is_visible():
                await btn.first.click(timeout=3000)
                self._cookie_ok = True
        except Exception:
            pass

    # ---------------------------------------------------------------- cupom
    async def _slip(self) -> dict:
        return await self.page.evaluate(js.READ_SLIP)

    async def clear_slip(self) -> None:
        for _ in range(10):
            rm = self.page.locator(S.SLIP_REMOVE)
            if await rm.count() == 0:
                return
            try:
                await rm.first.click(timeout=3000)
            except Exception:
                return
            await asyncio.sleep(0.4)

    async def _my_selection(self, line: float) -> Optional[dict]:
        return slip_selection(await self._slip(), line, self.home, self.away, self.cfg.match_threshold)

    async def _select_over(self, line: float) -> Optional[dict]:
        tag = await self.page.evaluate(js.TAG_OVER, line)
        if not tag.get("found") or tag.get("disabled"):
            return None
        if not tag.get("selected"):
            await self.page.locator('[data-bot-over="1"]').click(timeout=5000)
        fim = time.time() + 6
        while time.time() < fim:
            sel = await self._my_selection(line)
            if sel:
                return sel
            await asyncio.sleep(0.3)
        return None

    async def _enter_stake(self, stake: float) -> bool:
        campo = self.page.locator(S.STAKE_INPUT)
        if await campo.count() == 0:
            return False
        await campo.first.fill(format_stake(stake))
        await asyncio.sleep(0.4)
        slip = await self._slip()
        digitado = parse_amount((slip.get("input") or {}).get("value"))
        return digitado is not None and abs(digitado - stake) < 0.005

    async def place_bet(self, line: float, stake: float, min_odd: float, dry_run: bool) -> BetResult:
        info = await self._read()
        odd_tela = usable_odd(pick_over(info.get("overs") or [], line))
        if odd_tela is None:
            return BetResult("unavailable", detail=f"over {line:g} indisponível agora")
        if odd_tela < min_odd:
            return BetResult("odd_low", odd=odd_tela, detail="odd da tela abaixo do mínimo")

        await self.clear_slip()
        sel = await self._select_over(line)
        if not sel:
            return BetResult("unavailable", odd=odd_tela, detail="não consegui pôr a linha no cupom")
        odd = sel.get("odd")
        if odd is None or odd < min_odd:
            return BetResult("odd_low", odd=odd, detail="odd do cupom abaixo do mínimo")   # cupom fica como está
        if not await self._enter_stake(stake):
            await self.clear_slip()
            return BetResult("failed", odd=odd, detail="o valor não entrou certo no campo do cupom")

        if dry_run:
            slip = await self._slip()
            botoes = ", ".join(b["text"] for b in slip.get("buttons") or [])
            await self.clear_slip()
            return BetResult("dry_run_ok", odd=odd, stake=stake,
                             detail=f"cupom montado e limpo sem confirmar (botões vistos: {botoes})")

        # ------------------------------------------------ aposta real (fluxo logado AINDA NÃO MAPEADO)
        if await self.page.evaluate(js.LOGGED_OUT):
            await self.clear_slip()
            return BetResult("failed", odd=odd, detail="stake.com deslogada: não dá para apostar")
        tag = await self.page.evaluate(js.TAG_PLACE, S.PLACE_BUTTON.pattern)
        if not tag.get("found"):
            await self.clear_slip()
            return BetResult("failed", odd=odd, detail="botão de apostar não encontrado no cupom")
        if tag.get("disabled"):
            return BetResult("unavailable", odd=odd, detail="botão de apostar desabilitado agora")
        sel = await self._my_selection(line)                  # confere a odd de novo, no último instante
        if not sel or sel.get("odd") is None or sel["odd"] < min_odd:
            return BetResult("odd_low", odd=sel.get("odd") if sel else None, detail="odd caiu antes de apostar")
        odd = sel["odd"]
        antes = (await self._slip()).get("text", "")        # só vale texto que aparecer DEPOIS do clique
        await self.page.locator('[data-bot-place="1"]').click(timeout=5000)
        log.info("cliquei em apostar: over %s, %s %.2f @ %s", line, self.d.moeda, stake, odd)

        fim = time.time() + RESULT_TIMEOUT_S
        while time.time() < fim:
            await asyncio.sleep(1.0)
            slip = await self._slip()
            avisos = await self.page.evaluate(
                "() => (document.querySelector('[data-testid=\"notification-list\"]')||{}).innerText || ''")
            texto = f"{slip.get('text', '')}\n{avisos}"
            novo = lambda rx: bool(rx.search(texto)) and not rx.search(antes)   # noqa: E731
            if novo(S.ACCEPTED_RE):
                m = re.search(r"(?:ID|#)\s*[:#]?\s*([A-Za-z0-9-]{6,})", texto)
                return BetResult("accepted", odd=odd, stake=stake, receipt=m.group(1) if m else "")
            if novo(S.ODDS_CHANGED_RE):
                return BetResult("unavailable", odd=odd, detail="a casa avisou que a odd mudou; aposta não feita")
            if S.REJECTED_RE.search(slip.get("text", "")) and not S.REJECTED_RE.search(antes):
                return BetResult("failed", odd=odd, detail=f"a casa recusou: {slip.get('text', '')[:120]}")
        # não sabemos se entrou: NÃO repetir (D6)
        return BetResult("unknown", odd=odd, stake=stake,
                         detail=f"sem resposta reconhecível em {RESULT_TIMEOUT_S}s; confira 'My Bets' na stake.com")
