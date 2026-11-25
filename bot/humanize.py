"""Comportamento mais humano: pausas aleatórias, mouse com trajetória, digitação com ritmo."""
from __future__ import annotations

import asyncio
import random


async def pause(a: float = 0.4, b: float = 1.2) -> None:
    await asyncio.sleep(random.uniform(a, b))


async def human_click(page, locator, timeout: int = 8000) -> None:
    target = locator.first
    await target.wait_for(state="visible", timeout=timeout)
    try:
        await target.scroll_into_view_if_needed(timeout=timeout)
    except Exception:
        pass
    box = await target.bounding_box()
    if not box:
        await target.click(timeout=timeout)
        return
    x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
    y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
    await page.mouse.move(x + random.uniform(-60, 60), y + random.uniform(-40, 40), steps=random.randint(4, 9))
    await page.mouse.move(x, y, steps=random.randint(5, 12))
    await asyncio.sleep(random.uniform(0.06, 0.22))
    await page.mouse.click(x, y, delay=random.randint(40, 130))


async def human_type(page, text: str) -> None:
    for ch in text:
        await page.keyboard.type(ch)
        await asyncio.sleep(random.uniform(0.05, 0.18))


async def wander(page) -> None:
    """Movimento leve de mouse para não ficar parado durante o monitoramento."""
    try:
        vp = page.viewport_size or {"width": 440, "height": 900}
        await page.mouse.move(random.uniform(20, vp["width"] - 20), random.uniform(120, vp["height"] - 120),
                              steps=random.randint(6, 16))
    except Exception:
        pass
