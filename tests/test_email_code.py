import dataclasses
import time
from datetime import datetime, timezone

import pytest

from bot import email_code as ec

MAIL = """Código de Login
Foi feito um login a partir de um novo dispositivo. Por favor, use este código para aprovar futuros logins neste dispositivo.
Aqui está seu código de aprovação de login:
405685
Se este pedido não tiver sido feito por você, altere imediatamente a senha de sua conta para evitar mais acessos não autorizados. 123456 (ruído)
"""


def test_extract_code_prefers_approval_code():
    assert ec.extract_code(MAIL) == "405685"


def test_extract_code_html():
    html_body = "<div><p>Aqui está seu código de aprovação de login:</p><h1>  405685 </h1><p>Ref 999999</p></div>"
    assert ec.extract_code(ec.html_to_text(html_body)) == "405685"


def test_extract_none():
    assert ec.extract_code("sem codigo aqui 12345 e 1234567") is None


def test_pick_code_uses_newest_within_30_minutes():
    now = time.time()
    d = lambda off: datetime.fromtimestamp(now + off, timezone.utc)
    P = "Suporte Pinnacle Brasil <suporte@pinnacle.bet.br>"
    msgs = [
        ("Código de Validação", P, d(-3600), "código de aprovação de login: 111111"),   # 1h atrás: vencido
        ("Código de Validação", P, d(-600), "código de aprovação de login: 222222"),    # 10 min atrás: vale
        ("Promo", "Outro <x@spam.com>", d(30), "código de aprovação de login: 999999"),  # outro remetente
    ]
    assert ec.pick_code(msgs, since_ts=now) == "222222"      # já enviado nos últimos 30 min: esse vale
    assert ec.pick_code(msgs[:1], since_ts=now) is None       # só tem e-mail de 1h atrás
    msgs.append(("Código de Validação", P, d(20), "código de aprovação de login: 333333"))
    assert ec.pick_code(msgs, since_ts=now) == "333333"      # chegou um mais novo: esse ganha


def test_pick_code_real_email_parsing():
    import email
    raw = ("From: Suporte Pinnacle Brasil <suporte@pinnacle.bet.br>\r\nTo: thomasfbbrand@gmail.com\r\n"
           "Subject: =?utf-8?q?C=C3=B3digo_de_Valida=C3=A7=C3=A3o?=\r\nDate: Sun, 20 Sep 2026 23:42:00 -0300\r\n"
           "MIME-Version: 1.0\r\nContent-Type: text/html; charset=utf-8\r\n\r\n"
           "<html><body><h1>C&oacute;digo de Login</h1><p>Aqui est&aacute; seu c&oacute;digo de aprova&ccedil;&atilde;o de login:</p>"
           "<p><b>405685</b></p></body></html>").encode()
    subject, sender, dt, body = ec._decode(email.message_from_bytes(raw))
    assert subject == "Código de Validação" and "pinnacle" in sender
    assert ec.pick_code([(subject, sender, dt, body)], since_ts=dt.timestamp() - 10) == "405685"


LOGIN_HTML = """<html><body style="margin:0;font-family:sans-serif">
<form style="position:absolute;left:-278px;top:314px;width:236px"><input id=username-mobile-sidebar placeholder="Usuário"><input type=password placeholder="Senha"><button type=submit>ENTRAR</button></form>
<button id=top type=button style="position:absolute;left:266px;top:24px" onclick="document.getElementById('dlg').style.display='block'">ENTRAR</button>
<mat-mdc-dialog-container id=dlg style="display:none;position:absolute;left:60px;top:180px;width:300px"><form onsubmit="return false">
<div id=step1><input id=u placeholder="Usuário"><input id=p type=password placeholder="Senha">
<button type=button id=go onclick="window.step1=[u.value,p.value];step1el.style.display='none';step2.style.display='block'"><span>entrar</span></button><button type=button>CADASTRO</button></div>
<div id=step2 style="display:none"><p>Digite o código de aprovação enviado ao seu e-mail</p><input id=c placeholder="Código"><button type=button>Reenviar</button>
<button type=button onclick="window.code=c.value;document.body.setAttribute('data-ok','1')">Confirmar</button></div>
</form></mat-mdc-dialog-container>
<script>const step1el=document.getElementById('step1'),step2=document.getElementById('step2');</script></body></html>"""


def test_login_with_email_code_on_mock(monkeypatch, tmp_path):
    playwright = pytest.importorskip("playwright.async_api")
    import asyncio
    from bot.config import Config
    from bot.casas.pinnacle import driver as drv

    monkeypatch.chdir(tmp_path)
    cfg = dataclasses.replace(Config.load("/nonexistent"), pinnacle_user="user1", pinnacle_pass="Pa55word",
                              gmail_user="a@gmail.com", gmail_app_password="x" * 16)
    calls = {}

    def fake_fetch(user, pw, since_ts, timeout):
        calls["args"] = (user, since_ts)
        return "405685"

    monkeypatch.setattr("bot.email_code.fetch_code", fake_fetch)

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
            await pg.set_content(LOGIN_HTML)
            await d.ensure_logged_in(pg)
            res = await pg.evaluate("[window.step1, window.code]")
            await b.close()
            return res

    step1, code = asyncio.run(run())
    assert step1 == ["user1", "Pa55word"]
    assert code == "405685"
    assert calls["args"][0] == "a@gmail.com"
