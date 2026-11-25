import asyncio
import dataclasses

import pytest

HTML = """<html><body style="margin:0;font-family:sans-serif">
<button type=button style="position:absolute;left:266px;top:24px" onclick="dlg.style.display='block'">ENTRAR</button>
<mat-mdc-dialog-container id=dlg style="display:none;position:absolute;left:40px;top:220px;width:340px"><form onsubmit="return false">
<div id=s1><input placeholder="Usuário"><input type=password placeholder="Senha">
<button type=button onclick="window.s1=1;s1.style.display='none';s2.style.display='block';setTimeout(()=>{dlg.style.top='60px'},400)">ENTRAR</button></div>
<div id=s2 style="display:none"><p>Digite o código enviado ao seu e-mail</p><input id=c placeholder="Código" oninput="b.disabled=this.value.length<6">
<p style="margin-top:60px"><label><input type=checkbox id=trust checked> Confiar neste dispositivo</label></p>
<button type=button id=b disabled onclick="window.code=c.value;window.trust=trust.checked;document.body.setAttribute('data-ok','1')">ENTRAR</button></div>
</form></mat-mdc-dialog-container>
<script>const s1=document.getElementById('s1'),s2=document.getElementById('s2'),dlg=document.getElementById('dlg'),b=document.getElementById('b');
// a tela "pula" depois de o código ser digitado: o botão muda de posição
document.getElementById('c').addEventListener('input',e=>{if(e.target.value.length==6)setTimeout(()=>{document.querySelector('p[style]').style.marginTop='0px';dlg.style.top='30px'},700)});
</script></body></html>"""


def test_click_survives_layout_shift(monkeypatch, tmp_path):
    playwright = pytest.importorskip("playwright.async_api")
    from bot.config import Config
    from bot.casas.pinnacle import driver as drv

    monkeypatch.chdir(tmp_path)
    cfg = dataclasses.replace(Config.load("/nonexistent"), pinnacle_user="u", pinnacle_pass="p",
                              gmail_user="a@gmail.com", gmail_app_password="x" * 16)
    monkeypatch.setattr("bot.email_code.fetch_code", lambda *a, **k: "405685")

    async def run():
        async def notify(m):
            pass
        d = drv.PinnacleDriver(cfg, notify)

        async def logged(page):
            return bool(await page.evaluate("document.body.getAttribute('data-ok')==='1'"))
        d.is_logged_in = logged
        async with playwright.async_playwright() as pw:
            try:
                b = await pw.chromium.launch()
            except Exception:
                pytest.skip("sem Chromium")
            pg = await b.new_page(viewport={"width": 440, "height": 940})
            await pg.set_content(HTML)
            await d.ensure_logged_in(pg)
            res = await pg.evaluate("[window.s1, window.code, window.trust]")
            await b.close()
            return res

    s1, code, trust = asyncio.run(run())
    assert s1 == 1 and code == "405685" and trust is True


def test_enforce_viewport_returns_to_mobile_size(monkeypatch, tmp_path):
    playwright = pytest.importorskip("playwright.async_api")
    from bot.config import Config
    from bot.casas.pinnacle import driver as drv

    monkeypatch.chdir(tmp_path)
    cfg = Config.load("/nonexistent")

    async def run():
        async def notify(m):
            pass
        d = drv.PinnacleDriver(cfg, notify)
        async with playwright.async_playwright() as pw:
            try:
                b = await pw.chromium.launch()
            except Exception:
                pytest.skip("sem Chromium")
            pg = await b.new_page(viewport={"width": 1100, "height": 800})   # "virou desktop"
            await pg.set_content("<html><body>x</body></html>")
            await d.enforce_viewport(pg)
            size = await pg.evaluate("[innerWidth, innerHeight]")
            await b.close()
            return size

    w, h = asyncio.run(run())
    assert (w, h) == (440, 940)


def test_reset_saved_zoom_clears_only_zoom(tmp_path):
    import json
    from bot.casas.pinnacle.driver import reset_saved_zoom
    d = tmp_path / "prof" / "Default"
    d.mkdir(parents=True)
    prefs = {"partition": {"per_host_zoom_levels": {"x": {"pinnacle.bet.br": {"zoom_level": -2.22}}}, "other": 1},
             "profile": {"default_zoom_level": -1.0, "name": "keep"}, "intl": {"a": "b"}}
    (d / "Preferences").write_text(json.dumps(prefs), encoding="utf-8")
    assert reset_saved_zoom(str(tmp_path / "prof")) is True
    out = json.loads((d / "Preferences").read_text(encoding="utf-8"))
    assert out["partition"]["per_host_zoom_levels"] == {} and out["partition"]["other"] == 1
    assert out["profile"]["default_zoom_level"] == 0.0 and out["profile"]["name"] == "keep" and out["intl"] == {"a": "b"}
    assert reset_saved_zoom(str(tmp_path / "prof")) is False          # já limpo
    assert reset_saved_zoom(str(tmp_path / "nao_existe")) is False


def test_tag_games_ignores_style_text():
    playwright = pytest.importorskip("playwright.async_api")
    from bot.casas.pinnacle import js

    html = """<html><body><style>.app-loading { width: 100vw; } +3 &gt;</style>
    <div class=card><div>2H 50'</div><div>Juticalpa</div><div>3</div><div>Marathon</div><div>2</div><div>+ 5 &gt;</div><div>Mais Mercados</div></div></body></html>"""

    async def run():
        async with playwright.async_playwright() as pw:
            try:
                b = await pw.chromium.launch()
            except Exception:
                pytest.skip("sem Chromium")
            pg = await b.new_page()
            await pg.set_content(html)
            res = await pg.evaluate(js.TAG_GAMES)
            await b.close()
            return res

    cards = asyncio.run(run())
    assert len(cards) == 1
    assert not any("app-loading" in ln for ln in cards[0]["lines"])
    assert "Juticalpa" in cards[0]["lines"]


CARD_HTML = """<html><body style="margin:0;font-family:sans-serif"><div class=hdr>Futebol - Partida</div>
<div class=liga><div class=title>HONDURAS - LIGA NACIONAL</div>
<div class=card><div class=clock>2H 50'</div><div class=cols><span>Partida 1X2</span><span>Partida HDP</span><span>Partida OU</span></div>
<div class=row><span>Juticalpa</span><b>3</b><span>1</span><b>1.113</b><span>0</span><b>2.150</b><span>o 5.5</span><b>3.200</b></div>
<div class=row><span>Marathon</span><b>2</b><i>1</i><span>2</span><b>23.740</b><span>0</span><b>1.613</b><span>u 5.5</span><b>1.292</b></div>
<div class=more>+ 4 <svg width=8 height=8></svg></div></div></div></body></html>"""


def test_tag_games_single_card_without_mais_mercados():
    playwright = pytest.importorskip("playwright.async_api")
    from bot.casas.pinnacle import js
    from bot.casas.pinnacle.parsing import parse_card_teams

    async def run():
        async with playwright.async_playwright() as pw:
            try:
                b = await pw.chromium.launch()
            except Exception:
                pytest.skip("sem Chromium")
            pg = await b.new_page(viewport={"width": 440, "height": 940})
            await pg.set_content(CARD_HTML)
            res = await pg.evaluate(js.TAG_GAMES)
            marked = await pg.evaluate("document.querySelectorAll('[data-bot-plus]').length")
            await b.close()
            return res, marked

    cards, marked = asyncio.run(run())
    assert len(cards) == 1 and marked == 1
    assert parse_card_teams(cards[0]["lines"]) == ("Juticalpa", "Marathon")
