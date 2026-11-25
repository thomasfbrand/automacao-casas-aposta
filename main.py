"""Ponto de entrada.

  python main.py                      # escuta o Telegram e aposta (respeita DRY_RUN)
  python main.py --test-tip tip.txt   # injeta UMA tip de um arquivo (sem Telegram) para testar a Pinnacle
"""
from __future__ import annotations

import argparse
import datetime
import asyncio
import logging
import time
from pathlib import Path

from bot.config import Config
from bot.engine import Engine
from bot.notifier import Notifier
from bot.casas import get_casa
from bot.state import Store


async def run_telegram(cfg: Config, until: str | None = None) -> None:
    """Modo automático: escuta o grupo e dispara o fluxo sozinho a cada tip 'Live'."""
    from bot import telegram_client as tg

    log = logging.getLogger("main")
    notifier = Notifier(cfg.tg_notify)
    store = Store(cfg.state_db)
    client = await tg.connect(cfg)
    notifier.attach(client)
    entity = await tg.resolve_channel(client, cfg)
    log.info("escutando o grupo: %s", getattr(entity, "title", None) or cfg.tg_channel)

    # O navegador NÃO abre agora: só quando chegar a 1ª tip (abre, loga com o código do e-mail e segue o fluxo).
    driver = get_casa(cfg.casa)(cfg, notifier)
    engine = Engine(cfg, driver, notifier, store, alive_check=tg.make_alive_check(client, entity))
    tg.register_handlers(client, entity, engine)

    mode = "DRY_RUN (não confirma apostas)" if cfg.dry_run else "APOSTAS REAIS"
    await notifier.send(f"🤖 Robô no ar em modo {mode} ({cfg.casa}). "
                        f"1u = {getattr(driver, 'moeda', 'R$')} {cfg.unit_value:.2f}. "
                        f"Escutando: {getattr(entity, 'title', cfg.tg_channel)}. "
                        f"A casa só abre quando chegar uma tip.")
    stopper = asyncio.create_task(_stop_at(until, engine, notifier, client)) if until else None
    closer = asyncio.create_task(_idle_closer(driver, cfg.idle_close_min * 60))
    try:
        await client.run_until_disconnected()
    finally:
        closer.cancel()
        if stopper:
            stopper.cancel()
        await notifier.send("⏹️ Robô desligado.")
        await driver.stop()


async def _idle_closer(driver, idle_s: int) -> None:
    while True:
        await asyncio.sleep(60)
        try:
            await driver.close_if_idle(idle_s)
        except Exception as exc:
            logging.getLogger("main").warning("fechar navegador ocioso: %s", exc)


def next_time(hhmm: str, now: datetime.datetime | None = None) -> datetime.datetime:
    """Próxima ocorrência de HH:MM (ex.: '01:00' às 08:00 -> 01:00 de amanhã)."""
    now = now or datetime.datetime.now()
    h, m = (int(x) for x in hhmm.split(":"))
    t = now.replace(hour=h, minute=m, second=0, microsecond=0)
    return t if t > now else t + datetime.timedelta(days=1)


async def _stop_at(until: str, engine, notifier, client, grace_min: int = 20) -> None:
    """No horário de parar: não aceita tip nova, espera os jogos em andamento (até grace_min) e desliga."""
    log = logging.getLogger("main")
    end = next_time(until)
    log.info("vai parar sozinho às %s", end.strftime("%d/%m %H:%M"))
    await asyncio.sleep(max(0.0, (end - datetime.datetime.now()).total_seconds()))
    engine.accepting = False
    busy = [s for s in engine.sessions.values() if not s.finished]
    await notifier.send(f"🌙 Horário encerrado ({until}). Não pego tips novas."
                        + (f" Termino {len(busy)} jogo(s) em andamento (até {grace_min} min)." if busy else ""))
    try:
        await asyncio.wait_for(engine.wait_idle(), timeout=grace_min * 60)
    except asyncio.TimeoutError:
        log.warning("jogos ainda em andamento após %d min; desligando mesmo assim", grace_min)
    await client.disconnect()


async def run_test_tip(cfg: Config, path: str, allow_line_mismatch: bool = False) -> None:
    notifier = Notifier(cfg.tg_notify)
    store = Store(cfg.state_db)
    driver = get_casa(cfg.casa)(cfg, notifier)
    engine = Engine(cfg, driver, notifier, store, alive_check=None)
    engine.allow_line_mismatch = allow_line_mismatch   # só no modo de teste
    client = None
    try:   # conecta o Telegram só para mandar os avisos (sessão já salva pelo setup_telegram)
        from bot import telegram_client as tg
        client = await tg.connect(cfg)
        notifier.attach(client)
    except BaseException as exc:
        logging.getLogger("main").warning("sem Telegram no teste (avisos só no log): %s", exc)
    try:
        text = Path(path).read_text(encoding="utf-8")
        await engine.on_message(int(time.time()), text, None, None)
        await engine.wait_idle()
    finally:
        await driver.stop()
        if client is not None:
            await client.disconnect()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test-tip", help="arquivo .txt com uma tip (formato do grupo) para testar sem Telegram")
    ap.add_argument("--allow-line-mismatch", action="store_true",
                    help="SÓ PARA TESTE: aceita linha diferente de gols+0,5 (ex.: over 2.5 num 0x0)")
    ap.add_argument("--ate", help="horário para desligar sozinho, ex.: 01:00 (usado pelo agendador)")
    ap.add_argument("--env", default=".env")
    args = ap.parse_args()
    cfg = Config.load(args.env)
    Path("logs").mkdir(exist_ok=True)
    logfile = Path("logs") / time.strftime("robo_%Y-%m-%d.log")
    logging.basicConfig(level=getattr(logging, cfg.log_level.upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(logfile, encoding="utf-8")])
    if args.test_tip:
        asyncio.run(run_test_tip(cfg, args.test_tip, args.allow_line_mismatch))
    else:
        asyncio.run(run_telegram(cfg, args.ate))


if __name__ == "__main__":
    main()
