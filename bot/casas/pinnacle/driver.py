"""Automação do navegador na Pinnacle (Playwright).

Casos tratados (todos vistos no mapeamento manual):
- pop-ups em ordem variável: idade, localização (fallback por IP), cookies, aviso do app;
- login por usuário/senha; se aparecer 2FA/verificação/e-mail, avisa e espera VOCÊ resolver;
- sportsbook dentro de iframe de outro domínio;
- deslogado a casa mostra odds atrasadas => nunca lê odd sem estar logado;
- lista ao vivo, busca do jogo por nome aproximado (sem depender do nome da liga);
- odd ao vivo lida do DOM sem recarregar, mercado "Acima/Abaixo - Partida", "Ver Tudo";
- cupom: limpa antes, digita o valor (teclado ou teclado numérico da tela), confere odd,
  confirma, espera "Bet Accepted" (aposta ao vivo fica "Waiting" alguns segundos);
- "seleção indisponível", "Odds have changed", tela congelada (recarrega e reabre).
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from ...config import Config
from ...humanize import human_click, human_type, pause, wander
from ...matching import game_similarity
from ...models import BetResult, GameState
from . import js, selectors as S
from .parsing import (parse_card_teams, parse_confirm, parse_money, parse_slip_odd, parse_state,
                      state_from_scoreboard)

log = logging.getLogger("pinnacle")


def reset_saved_zoom(profile_dir: str) -> bool:
    """O Chrome guarda o zoom por site dentro do perfil (aqui ficou em ~67%, o que faz a Pinnacle virar o layout de
    desktop e quebra a leitura da tela). Zera isso ANTES de abrir o Chrome. Devolve True se limpou algo."""
    import json
    prefs = Path(profile_dir) / "Default" / "Preferences"
    if not prefs.exists():
        return False
    try:
        data = json.loads(prefs.read_text(encoding="utf-8"))
        part = data.get("partition") or {}
        levels = part.get("per_host_zoom_levels")
        changed = False
        if levels:
            part["per_host_zoom_levels"] = {}
            changed = True
        prof = data.get("profile") or {}
        if prof.get("default_zoom_level") not in (None, 0, 0.0):
            prof["default_zoom_level"] = 0.0
            changed = True
        if changed:
            prefs.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            log.info("zoom salvo do Chrome zerado (era %s)", str(levels)[:120])
        return changed
    except Exception as exc:
        log.warning("não consegui limpar o zoom do perfil: %s", exc)
        return False


class LoginError(RuntimeError):
    pass


async def _first_visible(locator):
    try:
        items = await locator.all()
    except Exception:
        return None
    for it in items:
        try:
            if await it.is_visible():
                return it
        except Exception:
            continue
    return None


class PinnacleDriver:
    def __init__(self, cfg: Config, notify):
        self.cfg = cfg
        self.notify = notify           # async callable(str)
        self._pw = None
        self.context = None
        self.anchor = None
        self.ui_lock = asyncio.Lock()  # só uma aposta/ação crítica por vez (o cupom é único na conta)
        self._start_lock = asyncio.Lock()
        self.started = False           # o navegador só abre quando chega uma tip (ensure_started)
        self.open_tabs = 0
        self.last_used = time.time()

    # ---------------------------------------------------------------- ciclo de vida
    async def start(self) -> None:
        from playwright.async_api import async_playwright

        if self.cfg.fresh_session:
            import tempfile
            self._tmp_profile = tempfile.mkdtemp(prefix="pinnacle_bot_")
            profile = self._tmp_profile
            log.info("sessão nova: Chrome limpo (sem login nem cookies de antes)")
        else:
            self._tmp_profile = None
            profile = str(Path(self.cfg.profile_dir).resolve())
            reset_saved_zoom(profile)
        self._pw = await async_playwright().start()
        kwargs = dict(
            user_data_dir=profile,
            headless=self.cfg.headless,
            viewport={"width": self.cfg.viewport_w, "height": self.cfg.viewport_h},
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            args=["--disable-blink-features=AutomationControlled"],
        )
        if self.cfg.chrome_channel:
            kwargs["channel"] = self.cfg.chrome_channel
        self.context = await self._pw.chromium.launch_persistent_context(**kwargs)
        self.anchor = self.context.pages[0] if self.context.pages else await self.context.new_page()
        await self.anchor.goto(S.HOME_URL, wait_until="domcontentloaded")
        await self.ensure_logged_in(self.anchor)

    async def ensure_started(self) -> None:
        """Abre o navegador e faz o login SÓ quando precisa (1ª tip do período). Chamadas simultâneas esperam."""
        async with self._start_lock:
            if self.started and self.context is not None:
                try:
                    _ = self.context.pages          # navegador ainda vivo?
                    return
                except Exception:
                    self.started = False
            log.info("tip recebida: abrindo a Pinnacle e fazendo login")
            await self.notify("🔐 Abrindo a Pinnacle e fazendo login para a tip…")
            try:
                await self.start()
                self.started = True
                self.last_used = time.time()
            except Exception:
                await self._stop_quiet()
                raise

    async def close_if_idle(self, idle_s: float) -> bool:
        """Fecha o navegador se não há jogo sendo acompanhado há idle_s segundos (economiza o PC e a sessão)."""
        async with self._start_lock:
            if not self.started or self.open_tabs > 0 or time.time() - self.last_used < idle_s:
                return False
            log.info("sem tips há %d min: fechando o navegador (reabre sozinho na próxima tip)", idle_s // 60)
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
        except Exception:                     # navegador foi fechado por fora: reabre
            log.warning("navegador fechado; reabrindo")
            self.started = False
            await self.ensure_started()
            page = await self.context.new_page()
        self.open_tabs += 1
        tab = GameTab(self, page)
        try:
            yield tab
        finally:
            self.open_tabs -= 1
            self.last_used = time.time()
            try:
                await page.close()
            except Exception:
                pass

    async def _real_viewport(self, page) -> dict:
        """Tamanho real da janela agora (page.viewport_size pode estar desatualizado se a janela mudou)."""
        try:
            w, h = await page.evaluate("() => [window.innerWidth, window.innerHeight]")
            return {"width": w, "height": h}
        except Exception:
            return page.viewport_size or {"width": self.cfg.viewport_w, "height": self.cfg.viewport_h}

    async def enforce_viewport(self, page) -> None:
        """Garante que a página enxergue ~440 px CSS de largura (layout celular), mesmo se o Chrome estiver com zoom
        diferente de 100%: ajusta o tamanho da janela pelo fator de zoom medido."""
        try:
            inner = await self._real_viewport(page)
            want_w, want_h = self.cfg.viewport_w, self.cfg.viewport_h
            if abs(inner["width"] - want_w) <= 30 and abs(inner["height"] - want_h) <= 60:
                return
            cur = page.viewport_size or {"width": want_w, "height": want_h}
            zoom = cur["width"] / max(inner["width"], 1)          # <1 = Chrome com zoom menor que 100%
            new_w, new_h = round(want_w * zoom), round(want_h * zoom)
            log.warning("página vê %dx%d (zoom~%.0f%%): ajustando janela de %dx%d para %dx%d",
                        inner["width"], inner["height"], zoom * 100, cur["width"], cur["height"], new_w, new_h)
            await page.set_viewport_size({"width": new_w, "height": new_h})
            await asyncio.sleep(1.0)
        except Exception as exc:
            log.debug("enforce_viewport: %s", exc)

    async def dismiss_overlays(self, page, rounds: int = 8) -> list[str]:
        """Fecha idade/localização/cookies/aviso do app, na página e nos iframes. Devolve o que fechou."""
        handled: list[str] = []
        await self.enforce_viewport(page)
        for _ in range(rounds):
            progressed = False
            for frame in list(page.frames):
                for name, title_re, btn_re in S.OVERLAYS:
                    try:
                        title = frame.get_by_text(title_re)
                        if await title.count() == 0 or not await title.first.is_visible():
                            continue
                        btn = await _first_visible(frame.get_by_role("button", name=btn_re))
                        if btn is None:
                            btn = await _first_visible(frame.get_by_text(btn_re))
                        if btn is None:
                            continue
                        await pause(0.4, 0.9)
                        box = await btn.bounding_box()
                        if box:
                            await page.mouse.move(box["x"] + box["width"] / 2 + random.uniform(-6, 6),
                                                  box["y"] + box["height"] / 2 + random.uniform(-4, 4),
                                                  steps=random.randint(5, 10))
                            await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2,
                                                   delay=random.randint(40, 120))
                        else:
                            await btn.click(timeout=3000)
                        handled.append(name)
                        log.info("pop-up tratado: %s", name)
                        progressed = True
                        await pause(0.7, 1.4)
                    except Exception as exc:  # pop-up sumiu no meio do clique, tudo bem
                        log.debug("overlay %s: %s", name, exc)
            if not progressed:
                break
        return handled

    # ---------------------------------------------------------------- login
    async def is_logged_in(self, page, settle: float = 12.0) -> bool:
        """True se logado. Espera a página terminar de carregar (senão 'deslogado' é um falso alarme)."""
        deadline = time.time() + settle
        while True:
            try:
                if await page.evaluate(S.LOGGED_IN_JS):
                    return True
                known = await page.evaluate(S.AUTH_KNOWN_JS)
            except Exception:
                known = False
            if known or time.time() >= deadline:
                return False
            await asyncio.sleep(0.6)

    async def read_balance(self, page=None) -> Optional[float]:
        if not self.started and page is None:
            return None
        page = page or self.anchor
        try:
            raw = await page.evaluate(S.BALANCE_JS)
        except Exception:
            return None
        return parse_money(raw) if raw else None

    async def _on_screen(self, page, locator):
        """Primeiro elemento do locator que esta REALMENTE na tela (a Pinnacle mantem um formulario de login
        escondido fora da tela, no menu lateral; is_visible() dele devolve True e enganou o robo)."""
        vp = await self._real_viewport(page)
        try:
            items = await locator.all()
        except Exception:
            return None
        for it in items:
            try:
                if not await it.is_visible():
                    continue
                box = await it.bounding_box()
                if not box or box["width"] < 5 or box["height"] < 5:
                    continue
                if box["x"] < 0 or box["y"] < 0 or box["x"] + box["width"] > vp["width"] + 2 \
                        or box["y"] + box["height"] > vp["height"] + 2:
                    continue
                return it
            except Exception:
                continue
        return None

    async def _login_fields(self, page):
        user_in = await self._on_screen(page, page.get_by_placeholder(S.LOGIN_USER_PLACEHOLDER))
        pass_in = await self._on_screen(page, page.get_by_placeholder(S.LOGIN_PASS_PLACEHOLDER))
        return user_in, pass_in

    async def _dump_screen(self, page, name: str) -> None:
        """Diagnóstico: foto + lista do que está na tela (inputs/botões), para eu ajustar sem adivinhar."""
        try:
            Path("inspect_out").mkdir(exist_ok=True)
            await page.screenshot(path=f"inspect_out/{name}.png")
            info = await page.evaluate(r"""() => [...document.querySelectorAll('input,button,[role=dialog],mat-mdc-dialog-container')]
              .map(e => { const r = e.getBoundingClientRect();
                return [e.tagName, e.type||'', e.placeholder||'', (e.innerText||'').trim().slice(0,25),
                        Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)].join('|'); })
              .filter(x => !/\|0\|0$/.test(x))""")
            log.info("tela (%s) url=%s vp=%s elementos: %s", name, page.url, page.viewport_size, "; ".join(info[:40]))
        except Exception as exc:
            log.info("dump da tela falhou: %s", exc)

    async def _click_stable(self, page, locator, tries: int = 4) -> bool:
        """Clica no elemento DEPOIS de a posição parar de mudar e confere que o clique vai cair nele
        (a Pinnacle reorganiza a tela logo após abrir o pop-up: clicar na posição antiga acerta outra coisa)."""
        it = locator.first
        for _ in range(12):      # botão cinza (desabilitado) até o código ficar completo
            try:
                if await it.is_enabled():
                    break
            except Exception:
                break
            await asyncio.sleep(0.25)
        for _ in range(tries):
            prev = None
            box = None
            for _ in range(16):
                try:
                    box = await it.bounding_box()
                except Exception:
                    box = None
                if box and prev and all(abs(box[k] - prev[k]) < 1 for k in ("x", "y", "width", "height")):
                    break
                prev = box
                await asyncio.sleep(0.25)
            if not box:
                await asyncio.sleep(0.4)
                continue
            x = box["x"] + box["width"] * random.uniform(0.35, 0.65)
            y = box["y"] + box["height"] * random.uniform(0.35, 0.65)
            try:
                hit = await it.evaluate(
                    "(el, p) => { const t = document.elementFromPoint(p[0], p[1]);"
                    " return !!t && (el === t || el.contains(t) || t.contains(el)); }", [x, y])
            except Exception:
                hit = True
            if not hit:
                log.info("clique estável: algo cobre o ponto (%d,%d), esperando a tela assentar", x, y)
                await asyncio.sleep(0.5)
                continue
            await page.mouse.move(x + random.uniform(-40, 40), y + random.uniform(-30, 30), steps=random.randint(4, 8))
            await page.mouse.move(x, y, steps=random.randint(5, 10))
            await asyncio.sleep(random.uniform(0.08, 0.25))
            await page.mouse.click(x, y, delay=random.randint(40, 120))
            return True
        try:   # último recurso: o clique do próprio Playwright (espera estabilizar e confere o alvo)
            await it.click(timeout=5000)
            return True
        except Exception as exc:
            log.info("clique estável falhou: %s", exc)
            return False

    async def _ensure_trust_checkbox(self, page) -> None:
        """Deixa marcado 'Confiar neste dispositivo' (assim o código não é pedido de novo)."""
        try:
            cb = page.locator("mat-mdc-dialog-container, [role=dialog], .cdk-overlay-container").get_by_role("checkbox")
            if await cb.count() and not await cb.first.is_checked():
                await cb.first.check(timeout=4000)
                log.info("marquei 'Confiar neste dispositivo'")
        except Exception as exc:
            log.debug("checkbox: %s", exc)

    async def _click_login_submit(self, page) -> bool:
        """Clica no ENTRAR de dentro do pop-up de login (nunca no do topo, que so abre o pop-up)."""
        dialog = page.locator("mat-mdc-dialog-container, [role=dialog], .cdk-overlay-container")
        rx = re.compile(r"entrar", re.I)
        strategies = [
            ("role", dialog.get_by_role("button", name=rx)),
            ("submit", dialog.locator("button[type=submit], input[type=submit]")),
            ("texto", dialog.locator("button, [role=button]").filter(has_text=rx)),
        ]
        for name, loc in strategies:
            try:
                n = await loc.count()
            except Exception:
                n = -1
            log.info("login: estrategia %s achou %s candidato(s)", name, n)
            for i in range(max(n, 0)):
                it = loc.nth(i)
                try:
                    if not await it.is_visible():
                        continue
                    box = await it.bounding_box()
                    if not box or box["width"] < 5:
                        continue
                    log.info("login: clicando (%s) em x=%d y=%d w=%d h=%d", name, box["x"], box["y"],
                             box["width"], box["height"])
                    if not await self._click_stable(page, it):
                        await it.click(timeout=3000, force=True)
                    return True
                except Exception as exc:
                    log.info("login: candidato %s falhou: %s", name, exc)
        # ultimo recurso: envia o formulario pelo proprio JS da pagina
        try:
            ok = await page.evaluate("""() => {
              const c = document.querySelector('mat-mdc-dialog-container, [role=dialog]');
              const f = c && (c.querySelector('form'));
              const b = c && [...c.querySelectorAll('button')].find(x => /entrar/i.test(x.innerText||''));
              if (b) { b.click(); return true; }
              if (f && f.requestSubmit) { f.requestSubmit(); return true; }
              return false; }""")
            log.info("login: clique via JS = %s", ok)
            return bool(ok)
        except Exception as exc:
            log.info("login: JS falhou: %s", exc)
            return False

    # ---------------------------------------------------------------- código por e-mail
    async def _code_prompt_visible(self, page) -> bool:
        """True se apareceu uma tela pedindo código (campo na tela que não é usuário/senha)."""
        try:
            body = (await page.evaluate("() => document.body.innerText || ''")) or ""
        except Exception:
            body = ""
        asks = re.search(r"c[oó]digo|verifica|valida[cç]|aprova[cç]|code|token", body, re.I)
        field = await self._code_field(page)
        return bool(field is not None and asks)

    async def _code_field(self, page):
        vp = await self._real_viewport(page)
        loc = page.locator("input:not([type=password]):not([type=hidden]):not([type=checkbox]):not([type=radio])")
        try:
            items = await loc.all()
        except Exception:
            return None
        for it in items:
            try:
                ph = (await it.get_attribute("placeholder")) or ""
                if re.search(r"^\s*(usu[aá]rio|senha)\s*$", ph, re.I):
                    continue
                if not await it.is_visible():
                    continue
                box = await it.bounding_box()
                if not box or box["x"] < 0 or box["x"] + box["width"] > vp["width"] + 2 or box["y"] < 0 \
                        or box["y"] + box["height"] > vp["height"] + 2 or box["width"] < 5:
                    continue
                return it
            except Exception:
                continue
        return None

    async def _submit_email_code(self, page, since_ts: float) -> bool:
        """Pega o código no Gmail, digita e confirma. Devolve True se enviou."""
        try:
            Path("inspect_out").mkdir(exist_ok=True)
            await page.screenshot(path="inspect_out/tela_codigo.png")
        except Exception:
            pass
        if not (self.cfg.gmail_user and self.cfg.gmail_app_password):
            log.warning("tela de código apareceu, mas GMAIL_USER/GMAIL_APP_PASSWORD estão vazios: digite na janela")
            return False
        from ...email_code import fetch_code
        log.info("tela de código detectada: procurando o e-mail da Pinnacle no Gmail")
        code = await asyncio.to_thread(fetch_code, self.cfg.gmail_user, self.cfg.gmail_app_password, since_ts, 90)
        if not code:
            log.warning("não achei o código no Gmail em 90s: digite na janela")
            return False
        log.info("código encontrado no e-mail (%d dígitos)", len(code))
        field = await self._code_field(page)
        if field is None:
            return False
        try:
            await human_click(page, field)
            await human_type(page, code)
            await pause(0.5, 1.0)
            try:
                Path("inspect_out").mkdir(exist_ok=True)
                await page.screenshot(path="inspect_out/codigo_digitado.png")
            except Exception:
                pass
            rx = re.compile(r"confirmar|verificar|validar|enviar|continuar|aprovar|entrar|submit", re.I)
            bad = re.compile(r"cancelar|cadastro|reenviar|voltar|fechar", re.I)
            dialog = page.locator("mat-mdc-dialog-container, [role=dialog], .cdk-overlay-container, form")
            for scope in (dialog, page):
                loc = scope.locator("button, [role=button]").filter(has_text=rx)
                for i in range(await loc.count()):
                    it = loc.nth(i)
                    txt = ((await it.inner_text()) or "").strip()
                    if bad.search(txt) or not await it.is_visible():
                        continue
                    box = await it.bounding_box()
                    if not box or box["y"] < 60 or box["x"] < 0:   # ignora botões do cabeçalho / fora da tela
                        continue
                    await self._ensure_trust_checkbox(page)
                    if not await self._click_stable(page, it):
                        continue
                    log.info("código enviado (botão '%s')", txt[:20])
                    return True
            await page.keyboard.press("Enter")
            log.info("código enviado com Enter (botão não achado)")
            return True
        except Exception as exc:
            log.warning("falha ao digitar o código: %s", exc)
            return False

    async def ensure_logged_in(self, page) -> None:
        await self.dismiss_overlays(page)
        if await self.is_logged_in(page):
            return
        log.info("sessão deslogada: iniciando login")
        submit_ts = time.time()
        code_tried = False
        await self._open_login_form(page)
        await self.dismiss_overlays(page)

        if self.cfg.pinnacle_user and self.cfg.pinnacle_pass:
            try:
                user_in, pass_in = await self._login_fields(page)
                if user_in is None or pass_in is None:
                    await self._dump_screen(page, "sem_campos_login")
                    raise LoginError("campos de usuario/senha nao encontrados na tela")
                await human_click(page, user_in)
                await human_type(page, self.cfg.pinnacle_user)
                await pause(0.4, 0.9)
                await human_click(page, pass_in)
                await human_type(page, self.cfg.pinnacle_pass)
                await pause(0.5, 1.1)
                # confere que os dois campos realmente ficaram preenchidos (sem logar os valores)
                got_u = await user_in.input_value()
                got_p = await pass_in.input_value()
                log.info("login: campos preenchidos usuario=%s senha=%s",
                         len(got_u) == len(self.cfg.pinnacle_user), len(got_p) == len(self.cfg.pinnacle_pass))
                if not got_u or not got_p:
                    raise LoginError("campos ficaram vazios apos digitar")
                submit_ts = time.time()
                if await self._click_login_submit(page):
                    log.info("login: cliquei no botao ENTRAR do formulario")
                else:
                    await page.keyboard.press("Enter")
                    log.info("login: botao nao achado, apertei Enter")
            except Exception as exc:
                log.warning("não consegui preencher o login sozinho: %s", exc)
        else:
            log.warning("PINNACLE_USER/PASS vazios: aguardando login manual")

        deadline = time.time() + 25
        while time.time() < deadline:
            await pause(1.5, 2.5)
            await self.dismiss_overlays(page)
            if await self.is_logged_in(page):
                log.info("login concluído")
                return
            if not code_tried and await self._code_prompt_visible(page):
                code_tried = True
                if await self._submit_email_code(page, submit_ts):
                    deadline = time.time() + 25

        # não entrou: pode ser 2FA / e-mail / facial / senha errada
        head = ""
        try:
            head = (await page.evaluate("() => (document.body.innerText||'').slice(0, 400)")).replace("\n", " | ")
        except Exception:
            pass
        try:
            Path("inspect_out").mkdir(exist_ok=True)
            await page.screenshot(path="inspect_out/login_falhou.png")
            log.info("screenshot salvo em inspect_out/login_falhou.png (url=%s)", page.url)
        except Exception:
            pass
        await self.notify(
            "⚠️ Pinnacle pediu algo além do usuário/senha (2FA, e-mail, verificação ou senha inválida). "
            f"Resolva na janela do navegador. Tenho {self.cfg.manual_intervention_timeout_s}s. Tela: {head[:200]}")
        deadline = time.time() + self.cfg.manual_intervention_timeout_s
        while time.time() < deadline:
            await asyncio.sleep(4)
            await self.dismiss_overlays(page)
            if await self.is_logged_in(page):
                await self.notify("✅ Login concluído.")
                return
        raise LoginError("login não concluído (2FA/verificação não resolvida a tempo)")

    async def _open_login_form(self, page) -> None:
        """Abre o pop-up de login clicando no ENTRAR do topo (o formulario do menu lateral fica fora da tela)."""
        for _ in range(4):
            user_in, _p = await self._login_fields(page)
            if user_in is not None:
                return
            btn = await self._on_screen(page, page.locator("button").filter(
                has_text=re.compile(r"^\s*entrar\s*$", re.I)))
            if btn is not None:
                await human_click(page, btn)
                await pause(1.2, 2.0)
                await self.dismiss_overlays(page)
            else:
                await pause(0.8, 1.5)

    # ---------------------------------------------------------------- iframe
    async def get_sports_frame(self, page, timeout: float = 40.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            for f in page.frames:
                if f is page.main_frame:
                    continue
                if S.SPORTS_FRAME_URL_RE.search(f.url) and "member-auth" not in f.url:
                    return f
            await asyncio.sleep(0.5)
        raise RuntimeError("iframe do sportsbook não carregou")


class GameTab:
    """Uma aba dedicada a um jogo: abre o jogo, lê minuto/placar/odd e faz a aposta."""

    def __init__(self, driver: PinnacleDriver, page):
        self.d = driver
        self.cfg = driver.cfg
        self.page = page
        self.home = ""
        self.away = ""
        self._last_state_sig = None
        self._last_change = time.time()

    async def frame(self):
        return await self.d.get_sports_frame(self.page)

    # ---------------------------------------------------------------- navegação
    async def open_live_list(self) -> None:
        await self.page.goto(S.SPORTSBOOK_URL, wait_until="domcontentloaded")
        await self.d.dismiss_overlays(self.page)
        if not await self.d.is_logged_in(self.page):
            await self.d.ensure_logged_in(self.page)
            await self.page.goto(S.SPORTSBOOK_URL, wait_until="domcontentloaded")
        f = await self.frame()
        await self._wait_frame_ready(f)
        await self.d.dismiss_overlays(self.page)
        tab = await _first_visible(f.get_by_text(S.LIVE_TAB))
        if tab is None:
            raise RuntimeError("aba AO VIVO não encontrada")
        if not await self.safe_click(tab, "aba AO VIVO"):
            await human_click(self.page, tab.locator("xpath=."))
        await pause(1.5, 2.5)
        await self.d.dismiss_overlays(self.page)

    async def _wait_frame_ready(self, f, timeout: float = 40.0) -> None:
        """Espera o sportsbook sair da tela de carregamento (senão o robô lê o CSS da tela de loading)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                ok = await f.evaluate(
                    "() => !document.querySelector('.app-loading') && (document.body.innerText || '').length > 150"
                    " && /AO VIVO|Futebol|Mais Mercados/i.test(document.body.innerText)")
                if ok:
                    await asyncio.sleep(0.8)
                    return
            except Exception:
                pass
            await asyncio.sleep(0.5)
        log.warning("sportsbook demorou mais de %ds para carregar", int(timeout))

    async def _load_all_cards(self, f) -> list[dict]:
        """(compatibilidade) lê os cards visíveis agora."""
        return await f.evaluate(js.TAG_GAMES)

    async def _expand_list(self, f) -> int:
        """Abre ligas recolhidas e clica em 'ver mais'. Devolve quantos cliques fez."""
        n = 0
        for _ in range(3):
            items = await f.evaluate(js.TAG_LIST_EXPANDERS)
            if not items:
                break
            log.info("lista: expandindo %s", items)
            for i in range(len(items)):
                loc = f.locator(f'[data-bot-expand="{i}"]')
                if await loc.count():
                    try:
                        await loc.first.click(timeout=2500, delay=random.randint(15, 45))
                        n += 1
                    except Exception as exc:
                        log.info("lista: não expandiu %s: %s", items[i], str(exc)[:100])
                    await asyncio.sleep(0.5)
        return n

    async def find_and_open(self, f, home: str, away: str) -> tuple[bool, list]:
        """Rola a lista ao vivo EM PASSOS (ela é virtualizada: só os jogos perto da tela existem), lendo os jogos
        a cada passo e abrindo ligas recolhidas. Match quase exato (>=0.95) abre na hora; senão varre tudo, guarda
        o melhor e volta até ele para clicar."""
        seen: dict[tuple, float] = {}
        best = (0.0, None, None)                     # (similaridade, teams, posição da rolagem)
        pos = await f.evaluate(js.SCROLL_STEP, "top")
        log.info("lista: rolagem em %s", pos)
        await asyncio.sleep(0.8)
        stuck = 0

        async def click_if_here(target_teams) -> bool:
            """A lista redesenha a cada rolagem (a marcação some): centraliza o card, espera assentar,
            marca de novo e só então clica."""
            centered = False
            for _ in range(4):
                hit = None
                for c in await f.evaluate(js.TAG_GAMES):
                    if parse_card_teams(c["lines"]) == target_teams:
                        hit = c
                        break
                if hit is None:
                    return False
                loc = f.locator(f'[data-bot-plus="{hit["i"]}"]')
                if not centered:
                    try:
                        await loc.first.evaluate("el => el.scrollIntoView({block: 'center'})")
                    except Exception:
                        pass
                    centered = True
                    await asyncio.sleep(0.8)
                    continue                      # redesenhou: marca de novo
                await self.close_sheet(f, reason="abrir jogo")
                if await self.safe_click(loc, "abrir jogo", timeout=3000):
                    return True
                await asyncio.sleep(0.4)
            return False

        for step in range(80):
            await self._expand_list(f)
            top_now = (pos or {}).get("top", 0)
            for c in await f.evaluate(js.TAG_GAMES):
                teams = parse_card_teams(c["lines"])
                if not teams:
                    continue
                sim = game_similarity(home, away, teams[0], teams[1])
                seen.setdefault(teams, sim)
                if sim > best[0]:
                    best = (sim, teams, top_now)
            if best[0] >= 0.95:
                log.info("lista: achei %s (%.2f) no passo %d; %d jogos vistos", best[1], best[0], step, len(seen))
                if await click_if_here(best[1]):
                    return True, list(seen.items())
            pos = await f.evaluate(js.SCROLL_STEP, 0.6)
            await asyncio.sleep(random.uniform(0.45, 0.8))
            if pos is None or pos["top"] <= pos["before"]:
                stuck += 1
                if stuck >= 2:
                    break
            else:
                stuck = 0
        log.info("lista: varredura completa, %d jogos vistos; melhor %s (%.2f)", len(seen), best[1], best[0])
        if best[1] is not None and best[0] >= self.cfg.match_threshold:
            # volta até onde o jogo estava e clica
            await f.evaluate(js.SCROLL_STEP, "top")
            await asyncio.sleep(0.5)
            for _ in range(80):
                if await click_if_here(best[1]):
                    log.info("lista: abri %s (%.2f)", best[1], best[0])
                    return True, list(seen.items())
                pos = await f.evaluate(js.SCROLL_STEP, 0.6)
                await asyncio.sleep(0.5)
                if pos is None or pos["top"] <= pos["before"]:
                    break
        return False, list(seen.items())

    async def _dump_list(self, f, name: str) -> None:
        try:
            Path("inspect_out").mkdir(exist_ok=True)
            html = await f.evaluate(js.LIST_HTML)
            Path(f"inspect_out/{name}.html").write_text(html or "", encoding="utf-8")
            await self.page.screenshot(path=f"inspect_out/{name}.png")
        except Exception as exc:
            log.info("dump da lista falhou: %s", exc)

    async def open_game(self, home: str, away: str, attempts: int = 3) -> bool:
        self.home, self.away = home, away
        for attempt in range(1, attempts + 1):
            try:
                await self.open_live_list()
                f = await self.frame()
                found, seen = await self.find_and_open(f, home, away)
            except Exception as exc:
                log.warning("abrir lista ao vivo falhou (%s/%s): %s", attempt, attempts, exc)
                await pause(2, 4)
                continue
            if found:
                if await self._wait_detail(f):
                    await self._save_detail_dump(f)
                    return True
                log.info("cliquei no jogo mas a tela dele não abriu")
                continue
            top = sorted(seen, key=lambda x: -x[1])[:3]
            log.info("lista ao vivo: %d jogos vistos, nenhum bate com '%s x %s'. Mais parecidos: %s",
                     len(seen), home, away, [(f"{a} x {b}", round(s, 2)) for (a, b), s in top])
            log.info("lista ao vivo (todos): %s", "; ".join(f"{a} x {b}" for (a, b), _ in seen))
            await self._dump_list(f, f"lista_sem_jogo_t{attempt}")
            await pause(3, 6)  # o jogo pode ainda não ter aparecido/atualizado
        return False

    async def _save_detail_dump(self, f) -> None:
        """Guarda o texto e a foto da tela do jogo (para eu conferir como o robô está lendo minuto/placar)."""
        try:
            Path("inspect_out").mkdir(exist_ok=True)
            txt = await f.evaluate(js.HEAD_TEXT)
            Path("inspect_out/jogo_detalhe.txt").write_text(txt, encoding="utf-8")
            await self.page.screenshot(path="inspect_out/jogo_detalhe.png")
            st = parse_state(txt)
            log.info("tela do jogo lida: placar=%sx%s minuto=%s ao_vivo=%s", st.home_goals, st.away_goals,
                     st.minute, st.live)
        except Exception as exc:
            log.debug("dump do jogo: %s", exc)

    async def _wait_detail(self, f) -> bool:
        pat = re.compile(r"Acima/Abaixo", re.I)
        try:
            await f.get_by_text(pat).first.wait_for(state="attached", timeout=15000)
            return True
        except Exception:
            pass
        # às vezes abre na aba "Popular": muda para "Partida"
        try:
            chip = await _first_visible(f.get_by_text(re.compile(r"^Partida$", re.I)))
            if chip:
                await self.safe_click(chip, "aba Partida")
                await f.get_by_text(pat).first.wait_for(state="attached", timeout=10000)
                return True
        except Exception:
            pass
        return False

    # ================================================================ leitura (estrutura real da página)
    async def read_state(self) -> GameState:
        f = await self.frame()
        st = None
        for attempt in range(2):
            try:
                st = state_from_scoreboard(await f.evaluate(js.READ_SCOREBOARD))
            except Exception as exc:
                log.debug("placar estruturado: %s", exc)
                st = None
            if st is not None:
                break
            # placar sumiu: pop-up por cima, painel do cupom aberto ou a tela saiu do jogo
            if attempt == 0:
                had_modal = await self.handle_modal(f)
                closed = await self.close_sheet(f, reason="ler placar")
                if had_modal or closed:
                    continue
            break
        if st is None:
            self._no_score = getattr(self, "_no_score", 0) + 1
            if self._no_score >= 2:
                log.warning("placar sumiu da tela %d vezes seguidas: reabrindo o jogo", self._no_score)
                await self._snap(f"erro_sem_placar_{self._no_score}", f)
                self._no_score = 0
                if await self.recover():
                    f = await self.frame()
                    try:
                        st = state_from_scoreboard(await f.evaluate(js.READ_SCOREBOARD))
                    except Exception:
                        st = None
        else:
            self._no_score = 0
        head = await f.evaluate(js.HEAD_TEXT)
        if st is None:
            st = parse_state(head)
            log.info("placar: estrutura não encontrada, lido pelo texto -> %sx%s min=%s",
                     st.home_goals, st.away_goals, st.minute)
        # a tela congelou? usa placar/minuto + as odds (que mudam o tempo todo)
        sig = (st.minute, st.home_goals, st.away_goals, hash(re.sub(r"[^0-9.]", "", head)[:600]))
        if sig != self._last_state_sig:
            self._last_state_sig = sig
            self._last_change = time.time()
        return st

    def stalled_for(self) -> float:
        """Segundos sem NENHUMA mudança de minuto/placar/odds (tela pode ter congelado)."""
        return time.time() - self._last_change

    def _over_locator(self, f, line: float):
        """Botão 'o <linha>' da seção 'Acima/Abaixo - Partida', achado pela ESTRUTURA a cada uso
        (os botões são recriados a toda hora; guardar o elemento não funciona)."""
        ls = re.escape(f"{line:g}")
        sec = f.locator(".section-container").filter(
            has=f.locator(".header-name", has_text=re.compile(r"^\s*Acima\s*/\s*Abaixo\s*-\s*Partida\s*$", re.I)))
        # o texto do botão chega grudado ("o 2.51.751"): linha + odd com 2-3 casas decimais
        return sec.locator("button").filter(has_text=re.compile(rf"^\s*o\s*{ls}\s*\d+\.\d{{2,3}}\s*$", re.I))

    async def read_over_odd(self, line: float) -> Optional[float]:
        f = await self.frame()
        info = await f.evaluate(js.READ_OVER_DOM, line)
        if not info.get("found"):
            info = await f.evaluate(js.READ_OVER, line)          # leitura antiga, pelo texto (reserva)
        if not info.get("found"):
            v = await f.evaluate(js.TAG_VER_TUDO)
            if v.get("found") and not v.get("expanded"):
                await self.safe_click(f.locator('[data-bot-vertudo="1"]'), "Ver tudo")
                await pause(0.8, 1.4)
                info = await f.evaluate(js.READ_OVER_DOM, line)
                if not info.get("found"):
                    info = await f.evaluate(js.READ_OVER, line)
        if info.get("found") and info.get("locked"):
            log.info("linha over %s bloqueada no momento (%s)", line, info.get("cls"))
            return None
        return info.get("odd") if info.get("found") else None

    async def recover(self) -> bool:
        """Recarrega e reabre o jogo (tela congelada, sessão caída, etc.)."""
        log.warning("recuperando aba: recarregando e reabrindo o jogo")
        try:
            await self.d.ensure_logged_in(self.page)
        except Exception as exc:
            log.error("recover/login: %s", exc)
            return False
        ok = await self.open_game(self.home, self.away, attempts=2)
        self._last_change = time.time()
        return ok

    async def maintain(self) -> None:
        # só trata pop-ups da página de fora; não mexe o mouse (poderia tocar na lista/cupom)
        await self.d.dismiss_overlays(self.page, rounds=1)

    async def _my_sel(self, f, line: float) -> dict:
        """Seleção 'Mais de <linha>' DESTE jogo no cupom (o cupom pode ter seleções de outros jogos ao mesmo tempo)."""
        res = await f.evaluate(js.SLIP_SELECTION, line)
        cards = res.get("all") or []
        if not cards:
            return {"found": False}
        if not (self.home and self.away):
            return cards[0]
        best, best_sim = None, 0.0
        for c in cards:
            ev = re.sub(r"\[\d+\s*-\s*\d+\]", "", c.get("event") or "").strip()
            parts = re.split(r"\s+vs\.?\s+|\s+x\s+", ev, maxsplit=1, flags=re.I)
            sim = game_similarity(self.home, self.away, parts[0], parts[1]) if len(parts) == 2 else 0.0
            if sim > best_sim:
                best, best_sim = c, sim
        if best is not None and best_sim >= self.cfg.match_threshold:
            return best
        return {"found": False, "other_games": [c.get("event") for c in cards]}

    # ================================================================ monitorar pelo cupom
    def line_missing_for(self) -> float:
        """Há quantos segundos a linha da tip não existe (nem no cupom, nem na tela). 0 = existe."""
        since = getattr(self, "_line_missing_since", None)
        return 0.0 if since is None else time.time() - since

    async def watch(self, line: float) -> tuple[GameState, Optional[float]]:
        """Modo 'esperar a odd': a linha fica SELECIONADA no cupom e o robô só lê o cupom (a Pinnacle atualiza a odd
        e o placar ali sozinha). Nada de rolar, recarregar ou clicar enquanto a odd não chega no mínimo."""
        f = await self.frame()
        try:
            sel = await self._my_sel(f, line)
        except Exception as exc:
            log.info("monitor: leitura do cupom falhou (%s); sigo", str(exc)[:80])
            sel = {"found": False}
        if sel.get("found"):
            # a linha existe (mesmo "trancada"/indisponível por instantes: isso é normal ao vivo)
            self._line_missing_since = None
            if not (await self.sheet_state(f)).get("open"):
                await self.open_sheet(f)
        elif time.time() - getattr(self, "_last_reselect", 0.0) > 8:
            # saiu do cupom: a linha ainda existe na tela? (se não existir por um tempo = saiu gol)
            self._last_reselect = time.time()
            await self.handle_modal(f)
            await self.close_sheet(f, reason="procurar a linha")
            exists = await self.read_over_odd(line) is not None or \
                bool((await f.evaluate(js.READ_OVER_DOM, line)).get("found"))
            if exists:
                self._line_missing_since = None
                log.info("monitor: a linha over %s não está no cupom; selecionando de novo", line)
                await self.clear_slip(f, line)
                if await self.select_over(f, line):
                    await self.open_sheet(f)
                    sel = await self._my_sel(f, line)
                    log.info("monitor: linha no cupom, agora só observo a odd (%s)", sel.get("odd"))
            else:
                if getattr(self, "_line_missing_since", None) is None:
                    self._line_missing_since = time.time()
                log.info("monitor: linha over %s não aparece na tela (há %ds)", line, int(self.line_missing_for()))
        # placar: estrutura da página (se desenhada) -> senão o "[a-b]" do cupom
        st = None
        try:
            st = state_from_scoreboard(await f.evaluate(js.READ_SCOREBOARD))
        except Exception:
            st = None
        head = ""
        try:
            head = await f.evaluate(js.HEAD_TEXT)
        except Exception:
            pass
        if st is None:
            st = parse_state(head)
            sc = sel.get("score") or []
            if len(sc) == 2:
                st.home_goals, st.away_goals = sc
            st.live = st.live or bool(sel.get("live"))
        odd = None
        if sel.get("found") and not re.search(r"CLOS|SUSPEND|UNAVAIL|OFFLINE|LOCK|NOT_?AVAIL|INVALID|ERROR",
                                              str(sel.get("status") or ""), re.I):
            odd = sel.get("odd")
        sig = (st.minute, st.home_goals, st.away_goals, odd, sel.get("sig"))
        if sig != self._last_state_sig:
            self._last_state_sig = sig
            self._last_change = time.time()
        lo, lt = getattr(self, "_last_logged_odd", None), getattr(self, "_last_logged_t", 0.0)
        if (odd is None) != (lo is None) or (odd and lo and abs(odd - lo) >= 0.03) or time.time() - lt > 30:
            self._last_logged_odd, self._last_logged_t = odd, time.time()
            log.info("monitor: over %s odd=%s status=%s placar=%sx%s min=%s", line, odd, sel.get("status"),
                     st.home_goals, st.away_goals, st.minute)
        return st, odd

    # ================================================================ cliques
    async def _covering(self, loc) -> Optional[str]:
        """Se algo cobre o centro do elemento, descreve o que (coordenadas do próprio iframe)."""
        try:
            return await loc.first.evaluate("""el => {
              const r = el.getBoundingClientRect();
              const x = r.x + r.width / 2, y = r.y + r.height / 2;
              if (y < 0 || y > innerHeight) return 'fora da tela (y=' + Math.round(y) + ')';
              const t = document.elementFromPoint(x, y);
              if (!t || el === t || el.contains(t) || t.contains(el)) return null;
              return t.tagName + '.' + String(t.className).slice(0, 60) + ' "' + (t.textContent || '').trim().slice(0, 30) + '"';
            }""")
        except Exception:
            return None

    async def modal_state(self, f=None) -> Optional[dict]:
        f = f or await self.frame()
        try:
            return await f.evaluate(js.MODAL_STATE)
        except Exception:
            return None

    async def handle_modal(self, f=None, confirm_clear: bool = False) -> Optional[str]:
        """Trata um pop-up aberto por cima da página (fica 'cobrindo' tudo e engole os cliques).
        - 'Limpar boletim de apostas': confirma SÓ se nós pedimos para limpar (confirm_clear=True), senão cancela.
        - 'Please login first': fecha e refaz o login.
        - qualquer outro: salva o HTML para análise e fecha sem confirmar nada."""
        f = f or await self.frame()
        m = await self.modal_state(f)
        if not m:
            return None
        self._modal_n = getattr(self, "_modal_n", 0) + 1
        try:
            Path("inspect_out").mkdir(exist_ok=True)
            Path(f"inspect_out/modal_{self._modal_n}.html").write_text(m.get("html") or "", encoding="utf-8")
        except Exception:
            pass
        text = m.get("text") or ""
        log.info("pop-up na tela: %r botões=%s", text[:120], m.get("buttons"))
        yes = r"^\s*(sim|confirmar|limpar|remover|excluir|ok|yes|continuar)\b"
        no = r"^\s*(cancelar|n[aã]o|fechar|voltar|no|cancel)\s*$"
        if re.search(r"limpar boletim", text, re.I):
            pat = yes if confirm_clear else no
        elif S.LOGIN_FIRST_RE.search(text):
            pat = r"^\s*(ok|fechar)\s*$"
        else:
            pat = no + "|^\\s*ok\\s*$"
        label = await f.evaluate(js.TAG_MODAL_BUTTON, pat)
        if label:
            try:
                await f.locator('[data-bot-modal="1"]').first.click(timeout=3000, delay=random.randint(15, 45))
            except Exception:
                await f.locator('[data-bot-modal="1"]').first.evaluate("el => el.click()")
            log.info("pop-up: cliquei em %r", label)
        else:
            log.info("pop-up: nenhum botão conhecido; tentando Escape")
            await self.page.keyboard.press("Escape")
        await asyncio.sleep(0.8)
        if S.LOGIN_FIRST_RE.search(text):
            await self.d.ensure_logged_in(self.page)
        return text

    async def safe_click(self, loc, what: str, timeout: int = 5000) -> bool:
        """Clique confiável dentro do iframe: rola até o elemento, espera ele parar, move o mouse de forma humana e
        usa o clique do Playwright (que confere que é ESSE elemento que recebe o clique, com evento real).
        Nunca clica 'às cegas' em coordenadas (foi isso que acertava o fundo escuro do cupom sem ninguém ver)."""
        it = loc.first
        try:
            await it.wait_for(state="attached", timeout=timeout)
            await it.scroll_into_view_if_needed(timeout=timeout)
        except Exception as exc:
            log.info("clique em %s: elemento não apareceu: %s", what, str(exc)[:150])
            return False
        prev, same, box = None, 0, None
        deadline = time.time() + 3.0
        while time.time() < deadline:            # espera a rolagem/animação terminar
            try:
                box = await it.bounding_box()
            except Exception:
                box = None
            if box and prev and all(abs(box[k] - prev[k]) < 0.5 for k in ("x", "y", "width", "height")):
                same += 1
                if same >= 2:
                    break
            else:
                same = 0
            prev = box
            await asyncio.sleep(0.12)
        if box:
            try:
                x = box["x"] + box["width"] * random.uniform(0.35, 0.65)
                y = box["y"] + box["height"] * random.uniform(0.35, 0.65)
                await self.page.mouse.move(x + random.uniform(-40, 40), y + random.uniform(-25, 25),
                                           steps=random.randint(3, 7))
                await self.page.mouse.move(x, y, steps=random.randint(3, 7))
            except Exception:
                pass
        try:
            # clique curto: a Pinnacle recria o botão quando a odd muda; se isso acontecer entre apertar e soltar
            # o mouse, o clique se perde (por isso cada clique importante é conferido depois)
            await it.click(timeout=timeout, delay=random.randint(15, 45))
            return True
        except Exception as exc:
            cover = await self._covering(it)
            log.info("clique em %s falhou (cobrindo: %s): %s", what, cover, str(exc)[:160])
            if cover and "Modal" in cover and not getattr(self, "_in_modal_retry", False):
                self._in_modal_retry = True
                try:
                    await self.handle_modal()
                    return await self.safe_click(loc, what + " (depois do pop-up)", timeout)
                finally:
                    self._in_modal_retry = False
            if cover:
                return False
        # O elemento é recriado o tempo todo (odds mudando) e o Playwright não o acha "parado".
        # Reserva: confere NA HORA, dentro do iframe, que o ponto central é o próprio elemento e clica ali.
        for _ in range(4):
            try:
                it = loc.first
                box = await it.bounding_box()
                hit = await it.evaluate("""el => { const r = el.getBoundingClientRect();
                    const t = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
                    return !!t && (t === el || el.contains(t)); }""")
                if box and hit:
                    await self.page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2,
                                                delay=random.randint(40, 110))
                    log.info("clique em %s: feito pela reserva (ponto conferido)", what)
                    return True
            except Exception:
                pass
            await asyncio.sleep(0.15)
        return False

    # ================================================================ painel do cupom
    async def _slip_text(self, f=None) -> str:
        f = f or await self.frame()
        return await f.evaluate(js.BODY_TEXT)

    async def sheet_state(self, f=None) -> dict:
        f = f or await self.frame()
        try:
            return await f.evaluate(js.SHEET_STATE)
        except Exception as exc:
            return {"open": False, "error": str(exc)[:100]}

    async def close_sheet(self, f=None, reason: str = "") -> bool:
        """Fecha o painel 'Boletim De Apostas' se estiver aberto. Devolve True se ESTAVA aberto e fechou."""
        f = f or await self.frame()
        st = await self.sheet_state(f)
        if not st.get("open"):
            return False
        log.info("painel do cupom aberto (%s): fechando. topo=%s altura=%s", reason, st.get("top"), st.get("H"))
        for attempt in range(1, 4):
            via = await f.evaluate(js.TAG_SHEET_CLOSE)
            if via:
                ok = await self.safe_click(f.locator('[data-bot-close="1"]'), f"fechar painel ({via})", timeout=3000)
                if not ok:      # clique "real" recusado: aciona o botão pelo próprio JS da página
                    try:
                        await f.locator('[data-bot-close="1"]').first.evaluate("el => el.click()")
                        log.info("fechar painel: acionado via JS")
                    except Exception as exc:
                        log.info("fechar painel via JS falhou: %s", exc)
            else:
                log.info("fechar painel: botão de recolher não achado, tentando Escape")
                await self.page.keyboard.press("Escape")
            await asyncio.sleep(0.9)
            st = await self.sheet_state(f)
            if not st.get("open"):
                log.info("painel fechado (tentativa %d)", attempt)
                return True
        await self._snap("erro_painel_nao_fecha", f)
        log.warning("não consegui fechar o painel do cupom")
        return False

    async def open_sheet(self, f=None) -> bool:
        """Abre o painel do cupom pelo menu de baixo ('Boletim De Apostas')."""
        f = f or await self.frame()
        if (await self.sheet_state(f)).get("open"):
            return True
        for attempt in range(1, 3):
            label = await f.evaluate(js.TAG_NAV_SLIP)
            if not label:
                log.info("abrir painel: item 'Boletim' do menu não achado")
                return False
            await self.safe_click(f.locator('[data-bot-nav="1"]'), f"menu Boletim ({label})", timeout=3000)
            for _ in range(6):
                await asyncio.sleep(0.4)
                if (await self.sheet_state(f)).get("open"):
                    return True
        return False

    async def selection_state(self, f, line: float) -> dict:
        try:
            return await f.evaluate(js.SELECTION_STATE, line)
        except Exception as exc:
            return {"error": str(exc)[:100]}

    @staticmethod
    def _looks_selected(before: dict, now: dict) -> bool:
        if now.get("inSheet"):
            return True
        if now.get("inBody") and not before.get("inBody"):
            return True
        if now.get("btnPressed") in ("true",) and before.get("btnPressed") != "true":
            return True
        b0, b1 = before.get("badge"), now.get("badge")
        if b0 is not None and b1 is not None and b1 > b0:
            return True
        c0, c1 = before.get("btnCls") or "", now.get("btnCls") or ""
        tok = re.compile(r"\b(selected|active|picked|chosen|checked|is-selected)\b", re.I)
        return bool(tok.search(c1) and not tok.search(c0))

    async def select_over(self, f, line: float) -> bool:
        """Coloca o 'Mais de <linha>' no cupom e CONFIRMA que entrou. Só clica de novo quando tem certeza de que
        o cupom está vazio (clicar numa odd já selecionada a desmarca)."""
        for attempt in range(1, 5):
            await self.close_sheet(f, reason="antes de clicar na odd")
            odd = await self.read_over_odd(line)                     # também marca data-bot-over (diagnóstico)
            loc = self._over_locator(f, line)
            if await loc.count() == 0:
                log.info("odd 'o %s' não achada pela estrutura; usando a marcação pelo texto", line)
                loc = f.locator('[data-bot-over="1"]')
            if odd is None or await loc.count() == 0:
                log.info("linha over %s não está disponível agora", line)
                return False
            before = await self.selection_state(f, line)
            log.info("clique na odd o %s @ %s (tentativa %d); antes: %s", line, odd, attempt, before)
            clicked = await self.safe_click(loc, f"odd o {line}")
            await asyncio.sleep(0.4)
            if S.LOGIN_FIRST_RE.search(await self._slip_text(f)):
                log.warning("a Pinnacle pediu login ao clicar na odd: a sessão caiu; refazendo o login")
                await self.d.dismiss_overlays(self.page, rounds=2)
                await self.d.ensure_logged_in(self.page)
                return False
            now = before
            for _ in range(12):                                          # até ~6 s
                await asyncio.sleep(0.5)
                now = await self.selection_state(f, line)
                if self._looks_selected(before, now):
                    log.info("seleção confirmada: %s", now)
                    return True
            try:
                Path("inspect_out").mkdir(exist_ok=True)
                await self.page.screenshot(path=f"inspect_out/01_apos_clicar_na_odd_t{attempt}.png")
            except Exception:
                pass
            log.info("sem sinal de seleção após o clique (clicou=%s): %s", clicked, now)
            # não sabemos se entrou: abre o painel e OLHA antes de clicar de novo
            if await self.open_sheet(f):
                st = await self.sheet_state(f)
                now = await self.selection_state(f, line)
                await self._dump_sheet(f, f"01b_painel_conferencia_t{attempt}")
                if now.get("inSheet") or (not st.get("empty") and st.get("inputs")):
                    log.info("seleção estava lá (painel): %s", st.get("text", "")[:200])
                    return True
                log.info("painel vazio: a seleção não entrou; tento de novo")
            await pause(0.6, 1.2)
        return False

    async def _dump_sheet(self, f, name: str) -> None:
        """Foto + HTML COMPLETO do painel do cupom (o que precisamos ver se algo nele falhar)."""
        try:
            Path("inspect_out").mkdir(exist_ok=True)
            await self.page.screenshot(path=f"inspect_out/{name}.png")
            html = await f.evaluate(js.SHEET_HTML)
            if html:
                Path(f"inspect_out/{name}.html").write_text(html, encoding="utf-8")
            st = await self.sheet_state(f)
            log.info("[painel %s] aberto=%s vazio=%s campos=%s texto=%r", name, st.get("open"), st.get("empty"),
                     st.get("inputs"), (st.get("text") or "")[:300])
        except Exception as exc:
            log.info("[painel %s] falhou: %s", name, exc)

    async def clear_slip(self, f=None, line: Optional[float] = None) -> None:
        """Tira a(s) seleção(ões) do cupom e fecha o painel. Não abre o painel à toa."""
        f = f or await self.frame()
        st = await self.sheet_state(f)
        sel = await self.selection_state(f, line) if line is not None else {}
        if not st.get("open") and not (sel.get("inBody") or (sel.get("badge") or 0) > 0):
            return
        if not st.get("open"):
            await self.open_sheet(f)
        for _ in range(4):
            st = await self.sheet_state(f)
            if not st.get("open") or st.get("empty"):
                break
            via = None
            if line is not None:
                res = await f.evaluate(js.SLIP_SELECTION, line)
                mine = await self._my_sel(f, line)
                others = [c for c in (res.get("all") or []) if c.get("event") != mine.get("event")]
                if others or (res.get("cards") or 0) > len(res.get("all") or []):
                    # tem seleção de OUTRO jogo no cupom: remove só a deste jogo (ou nada, se não houver)
                    if not mine.get("found") or not await f.evaluate(js.TAG_CARD_DELETE, mine.get("event")):
                        log.info("limpar cupom: há seleções de outros jogos; não mexo nelas")
                        break
                    via = "lixeira do card"
            if via is None:
                via = await f.evaluate(js.TAG_SHEET_REMOVE)
            if not via:
                log.info("limpar cupom: botão de remover não achado no painel")
                await self._dump_sheet(f, "erro_sem_botao_remover")
                break
            # a lixeira abre o pop-up "Limpar boletim de apostas / Tem certeza?": o clique em si pode "falhar"
            # porque o pop-up aparece por cima na hora -> não usar safe_click (que cancelaria o pop-up)
            try:
                await f.locator('[data-bot-slip-x="1"]').first.click(timeout=3000, delay=random.randint(15, 45))
            except Exception as exc:
                log.info("lixeira: %s", str(exc)[:120])
            await asyncio.sleep(0.8)
            await self.handle_modal(f, confirm_clear=True)
            await asyncio.sleep(0.6)
        st = await self.sheet_state(f)
        sel = await self.selection_state(f, line) if line is not None else {}
        if st.get("open") and sel.get("inSheet") and not S.ACCEPTED_RE.search(st.get("text") or ""):
            # último recurso: clicar de novo na mesma odd desmarca a seleção (só se ela ESTÁ no cupom)
            await self.close_sheet(f, reason="desmarcar pela odd")
            loc = self._over_locator(f, line)
            if await loc.count():
                await self.safe_click(loc, f"odd o {line} (desmarcar)")
                await asyncio.sleep(0.8)
        await self.close_sheet(f, reason="depois de limpar")

    async def collapse_slip(self) -> None:
        await self.close_sheet(reason="recolher")

    # ================================================================ valor da aposta
    async def _enter_stake(self, f, stake: float) -> bool:
        text = f"{stake:.2f}".rstrip("0").rstrip(".")
        info = await f.evaluate(js.TAG_STAKE_IN_SHEET)
        for _ in range(8):                       # o campo fica só-leitura por instantes quando a odd muda
            if not (info and info.get("input") and info.get("ro")):
                break
            await asyncio.sleep(0.5)
            info = await f.evaluate(js.TAG_STAKE_IN_SHEET)
        log.info("valor: campo no painel = %s", info)
        if info is None:
            await self._dump_sheet(f, "erro_sem_campo_valor")
            return False
        field = f.locator('[data-bot-stake="1"]')
        if not await self.safe_click(field, "campo do valor", timeout=4000):
            await self._dump_sheet(f, "erro_clique_campo_valor")
            return False
        await pause(0.3, 0.6)
        typed = False
        if info.get("input"):
            try:
                await field.first.fill("")                      # limpa valor que tenha ficado
                await self.page.keyboard.type(text, delay=random.randint(70, 160))
                typed = True
            except Exception as exc:
                log.info("valor: digitação direta falhou: %s", exc)
        if not typed:                                               # teclado numérico na tela
            for ch in text:
                if not await f.evaluate(js.TAG_KEYPAD, ch) or \
                        not await self.safe_click(f.locator('[data-bot-key="1"]'), f"tecla {ch}", timeout=3000):
                    log.info("valor: tecla '%s' do teclado na tela não encontrada", ch)
                    await self._dump_sheet(f, "erro_teclado_valor")
                    return False
                await pause(0.12, 0.35)
        await pause(0.4, 0.8)
        got = None
        try:
            val = await field.first.input_value() if info.get("input") else ""
            got = parse_money(val) if val else None
        except Exception:
            pass
        body = await self._slip_text(f)
        m = S.TOTAL_STAKE_RE.search(body)
        total = parse_money(m.group(1)) if m else None
        log.info("valor: campo=%s total=%s (queria %s)", got, total, stake)
        await self._dump_sheet(f, "03_valor_digitado")
        ok_vals = [v for v in (total, got) if v is not None]
        return bool(ok_vals) and all(abs(v - stake) < 0.005 for v in ok_vals)

    # ================================================================ aposta
    async def place_bet(self, line: float, stake: float, min_odd: float, dry_run: bool) -> BetResult:
        """Monta o cupom do 'Mais de <linha>', digita o valor, confere a odd e (se não for dry-run) confirma."""
        f = await self.frame()
        pre = await self._my_sel(f, line)
        if pre.get("found"):
            odd = pre.get("odd")
            log.info("place_bet: linha já no cupom (odd %s); indo direto para o valor", odd)
            if odd is None or odd < min_odd:
                return BetResult("odd_low", odd=odd, detail=f"odd {odd} < mínimo {min_odd}")
        else:
            await self.d.dismiss_overlays(self.page, rounds=2)
            await self.clear_slip(f, line)
            odd = await self.read_over_odd(line)
            log.info("place_bet: over %s odd=%s (mínima %s) stake=%s dry_run=%s", line, odd, min_odd, stake, dry_run)
            if odd is None:
                return BetResult("unavailable", detail=f"linha over {line} não encontrada/bloqueada")
            if odd < min_odd:
                return BetResult("odd_low", odd=odd, detail=f"odd {odd} < mínimo {min_odd}")
            if not await self.select_over(f, line):
                await self.close_sheet(f, reason="falhou a seleção")
                return BetResult("failed", detail="a odd não entrou no cupom depois de clicar")

        if not await self.open_sheet(f):
            await self._snap("erro_painel_nao_abriu", f)
            await self.clear_slip(f, line)
            return BetResult("failed", detail="o painel do cupom não abriu com a seleção")
        await self._dump_sheet(f, "02_cupom_com_selecao")

        body = await self._slip_text(f)
        if S.UNAVAILABLE_RE.search((await self.sheet_state(f)).get("text", "")):
            await self.clear_slip(f, line)
            return BetResult("unavailable", detail="seleção indisponível no momento")

        if not await self._enter_stake(f, stake):
            await self.clear_slip(f, line)
            return BetResult("failed", detail="não consegui digitar o valor da aposta no cupom")

        body = await self._slip_text(f)
        info = {}
        try:
            info = await self._my_sel(f, line)
        except Exception as exc:
            log.info("leitura da seleção no cupom falhou: %s", exc)
        log.info("cupom: %s", info)
        # data-status do cupom: "OK" e "ODDS_CHANGE" (a odd só mudou -- normal ao vivo) seguem; a odd nova é
        # conferida abaixo e de novo no pop-up de confirmação. Só para se a seleção fechou/suspendeu.
        if info.get("found") and re.search(r"CLOS|SUSPEND|UNAVAIL|OFFLINE|LOCK|NOT_?AVAIL|INVALID|ERROR",
                                           str(info.get("status") or ""), re.I):
            await self.clear_slip(f, line)
            return BetResult("unavailable", detail=f"seleção com status {info.get('status')} no cupom")
        if info.get("found") and info.get("minStake") and stake < info["minStake"]:
            await self.clear_slip(f, line)
            return BetResult("failed", detail=f"valor abaixo do mínimo da casa ({info['minStake']})")
        slip_odd = (info.get("odd") if info.get("found") else None) or parse_slip_odd(body, line) or odd
        if slip_odd < min_odd:     # mantém a seleção no cupom: o monitor segue esperando a odd
            return BetResult("odd_low", odd=slip_odd, detail="odd caiu ao montar o cupom")

        if dry_run:
            await self.clear_slip(f, line)
            return BetResult("dry_run_ok", odd=slip_odd, stake=stake,
                             detail="DRY_RUN: cupom montado, valor digitado, odd conferida; NÃO confirmado")

        # ---- confirmação real ----
        return await self._confirm_bet(f, line, stake, min_odd, slip_odd)

    async def _slip_now(self, f, line: float) -> dict:
        try:
            return await self._my_sel(f, line)
        except Exception:
            return {}

    async def _confirm_bet(self, f, line: float, stake: float, min_odd: float, slip_odd: float) -> BetResult:
        """Fazer aposta -> pop-up de confirmação -> SIM -> 'Bet Accepted'.
        Ao vivo a odd mexe o tempo todo: se a Pinnacle devolver o cupom com 'Odds have changed' (aposta NÃO feita:
        a seleção continua no cupom com o valor e o botão 'Fazer 1 aposta'), tenta de novo enquanto a odd >= mínimo."""
        final_odd, risk = slip_odd, stake
        for attempt in range(1, 6):
            sel = await self._slip_now(f, line)
            cur = sel.get("odd") or slip_odd
            if cur is not None and cur < min_odd:
                log.info("confirmação: odd caiu para %s (< %s) antes de apostar; volto a esperar", cur, min_odd)
                return BetResult("odd_low", odd=cur, detail="odd caiu antes de confirmar")
            place = f.locator("button.btn-place-bets")
            if await place.count() == 0:
                place = f.get_by_role("button", name=S.PLACE_BUTTON)
            btn = await _first_visible(place)
            if btn is None or not await btn.is_enabled():
                await self._dump_sheet(f, "erro_sem_botao_fazer_aposta")
                return BetResult("unavailable", odd=cur, detail="botão 'Fazer aposta' indisponível agora")
            ok = await self.safe_click(btn, "FAZER APOSTA")
            log.info("confirmação %d: cliquei em 'Fazer aposta' (ok=%s) com odd %s", attempt, ok, cur)

            confirm = None
            for _ in range(20):                       # até ~10 s pelo pop-up "arriscar X BRL para ganhar Y"
                await asyncio.sleep(0.5)
                confirm = parse_confirm(await self._slip_text(f))
                if confirm:
                    break
            if not confirm:
                body = await self._slip_text(f)
                await self._dump_sheet(f, f"04_sem_popup_t{attempt}")
                if S.ACCEPTED_RE.search(body):        # alguns fluxos aceitam direto
                    m = S.ACCEPTED_RE.search(body)
                    return BetResult("accepted", odd=cur, stake=stake, receipt=m.group(1) or "")
                log.info("confirmação %d: pop-up não apareceu (odd mudou?); tento de novo", attempt)
                continue
            risk, _win, final_odd = confirm
            log.info("confirmação %d: pop-up diz arriscar %.2f @ %.3f", attempt, risk, final_odd)
            if abs(risk - stake) > 0.005 or final_odd + 0.006 < min_odd:
                no = await _first_visible(f.get_by_text(S.CONFIRM_NO))
                if no:
                    await self.safe_click(no, "CANCELAR")
                if abs(risk - stake) > 0.005:
                    await self.clear_slip(f, line)
                    return BetResult("failed", odd=final_odd, stake=risk, detail=f"valor errado no pop-up: R$ {risk}")
                log.info("confirmação: odd %.3f abaixo do mínimo no pop-up; volto a esperar", final_odd)
                return BetResult("odd_low", odd=final_odd, detail="odd abaixo do mínimo na confirmação")

            yes = await _first_visible(f.get_by_role("button", name=S.CONFIRM_YES)) or \
                await _first_visible(f.get_by_text(S.CONFIRM_YES))
            if yes is None:
                await self._dump_sheet(f, "erro_sem_botao_sim")
                return BetResult("failed", odd=final_odd, detail="botão SIM da confirmação não encontrado")
            ok = await self.safe_click(yes, "SIM")
            log.info("confirmação %d: cliquei em SIM (ok=%s)", attempt, ok)
            await asyncio.sleep(0.8)
            await self._dump_sheet(f, f"05_depois_do_sim_t{attempt}")

            # resultado: aceita / processando / devolvida ("Odds have changed", seleção ainda no cupom = NÃO apostou)
            deadline = time.time() + 75
            waited_back = 0
            outcome = None
            while time.time() < deadline:
                await asyncio.sleep(1.0)
                body = await self._slip_text(f)
                m = S.ACCEPTED_RE.search(body)
                if m:
                    receipt = m.group(1) or ""
                    await self._dump_sheet(f, "06_aposta_aceita")
                    await pause(0.8, 1.5)
                    await self.close_sheet(f, reason="aposta aceita")   # não mexe em mais nada do cupom
                    return BetResult("accepted", odd=final_odd, stake=risk, receipt=receipt)
                if S.REJECTED_RE.search(body) and not S.WAITING_RE.search(body):
                    await self._dump_sheet(f, "erro_aposta_recusada")
                    outcome = "recusada"
                    break
                back = (not S.WAITING_RE.search(body)) and (await self._slip_now(f, line)).get("found") and \
                    await _first_visible(f.locator("button.btn-place-bets")) is not None and not parse_confirm(body)
                waited_back = waited_back + 1 if back else 0
                if waited_back >= 4:                   # 4 s de volta ao cupom normal: não entrou
                    outcome = "devolvida"
                    break
            if outcome is None:
                # Não sabemos se entrou: NÃO tentar de novo (evita aposta dobrada). Conferir em "Minhas Apostas".
                await self._dump_sheet(f, "erro_sem_resposta")
                return BetResult("unknown", odd=final_odd, stake=risk,
                                 detail="sem resposta da casa em 75s; confira 'Minhas Apostas'")
            txt = (await self.sheet_state(f)).get("text", "")
            log.info("confirmação %d: aposta NÃO entrou (%s): %s", attempt, outcome, txt[:160])
            await asyncio.sleep(0.5)
        return BetResult("odd_low", odd=final_odd,
                         detail="a casa devolveu a aposta 5 vezes (odd mudando); sigo monitorando")

    async def _snap(self, name: str, f=None) -> None:
        """Foto + relatório do cupom em inspect_out/<name>.* (o que o robô realmente vê nesse instante)."""
        import json
        try:
            f = f or await self.frame()
            Path("inspect_out").mkdir(exist_ok=True)
            await self.page.screenshot(path=f"inspect_out/{name}.png")
            rep = await f.evaluate(js.SLIP_REPORT)
            html = rep.pop("html", "") if isinstance(rep, dict) else ""
            Path(f"inspect_out/{name}.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
            if html:
                Path(f"inspect_out/{name}.html").write_text(html, encoding="utf-8")
            if isinstance(rep, dict) and rep.get("found"):
                ins = [(i["tag"], i["type"], i["ph"] or i["aria"], i["ro"], i["vis"]) for i in rep["inputs"]]
                bts = [b["text"] for b in rep["buttons"] if b["text"]][:12]
                log.info("[snap %s] campos=%s botoes=%s", name, ins, bts)
            else:
                log.info("[snap %s] cupom NAO encontrado na tela", name)
        except Exception as exc:
            log.info("[snap %s] falhou: %s", name, exc)

