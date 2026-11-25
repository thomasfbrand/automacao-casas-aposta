"""Diagnóstico: abre a Pinnacle (logada pelo seu perfil) e salva o HTML/texto do iframe do sportsbook.

Use quando um passo do robô falhar ou a Pinnacle mudar o site. Envie a pasta 'inspect_out' para ajustar
os seletores em bot/pinnacle/selectors.py.

  python -m tools.inspect_frame               # lista ao vivo
  python -m tools.inspect_frame "Mirassol" "Botafogo"   # abre o jogo e salva a página do jogo
"""
import asyncio
import logging
import sys
from pathlib import Path

from bot.config import Config
from bot.notifier import Notifier
from bot.casas.pinnacle.driver import PinnacleDriver


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    cfg = Config.load()
    out = Path("inspect_out")
    out.mkdir(exist_ok=True)
    drv = PinnacleDriver(cfg, Notifier(cfg.tg_notify))
    await drv.start()
    try:
        async with drv.open_tab() as tab:
            if len(sys.argv) >= 3:
                ok = await tab.open_game(sys.argv[1], sys.argv[2])
                print("jogo aberto:", ok)
            else:
                await tab.open_live_list()
            f = await tab.frame()
            (out / "frame.html").write_text(await f.content(), encoding="utf-8")
            (out / "frame.txt").write_text(await f.evaluate("() => document.body.innerText"), encoding="utf-8")
            await tab.page.screenshot(path=str(out / "tela.png"))
            print("salvo em", out.resolve())
    finally:
        await drv.stop()


if __name__ == "__main__":
    asyncio.run(main())
