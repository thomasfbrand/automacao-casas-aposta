"""Decisões sobre o que js.py leu da stake.com. Python puro: testável sem navegador."""
from __future__ import annotations

import re
from typing import Optional

from ...matching import game_similarity
from ...models import GameState


def minute_from(clock: Optional[str], period: Optional[str], header: Optional[int]) -> Optional[int]:
    """Minuto de jogo. O relógio da Sportradar conta o tempo TOTAL ("83:39" no 2º tempo), então basta
    a parte dos minutos. Sem relógio, usa o "73'" do cabeçalho."""
    if clock:
        m = re.match(r"^\s*(\d{1,3}):\d{2}\s*$", clock)
        if m:
            return int(m.group(1))
    return header


def state_from_game(info: dict) -> GameState:
    """GameState a partir de js.READ_GAME."""
    score = info.get("score") or None
    period = (info.get("period") or "").strip().lower()
    st = GameState(raw=str({k: info.get(k) for k in ("score", "clock", "period", "minuteHeader")}))
    if score and len(score) == 2:
        st.home_goals, st.away_goals = int(score[0]), int(score[1])
    st.minute = minute_from(info.get("clock"), info.get("period"), info.get("minuteHeader"))
    st.ended = period in ("ended", "ft", "fim", "full time")
    st.live = (st.minute is not None or period in ("1st", "2nd", "ht")) and not st.ended
    return st


def pick_over(overs: list[dict], line: float) -> Optional[dict]:
    """A linha exata da tip no total da partida, ou None se a casa não está oferecendo essa linha agora."""
    for o in overs or []:
        if o.get("line") is not None and abs(float(o["line"]) - line) < 1e-9:
            return o
    return None


def usable_odd(over: Optional[dict]) -> Optional[float]:
    """Odd que vale para decidir: None se a linha não existe, está suspensa ou sem número."""
    if not over or over.get("suspended"):
        return None
    odd = over.get("odd")
    return float(odd) if odd else None


def teams_of(card: dict) -> tuple[str, str] | None:
    t = card.get("teams") or []
    return (t[0], t[1]) if len(t) >= 2 else None


def best_card(cards: list[dict], home: str, away: str, threshold: float) -> tuple[Optional[dict], float]:
    """O card da lista ao vivo que mais parece o jogo da tip (nomes aproximados). (card, similaridade)."""
    best, best_sim = None, 0.0
    for c in cards or []:
        t = teams_of(c)
        if not t or not c.get("href"):
            continue
        sim = game_similarity(home, away, t[0], t[1])
        if sim > best_sim:
            best, best_sim = c, sim
    if best is not None and best_sim >= threshold:
        return best, best_sim
    return None, best_sim


def game_path(href: str) -> str:
    """Caminho canônico do jogo, sem prefixo de idioma (o HTML do servidor às vezes vem com /pl/, /pt/...)."""
    m = re.search(r"(/sports/soccer/.+/\d+-[^/?#]+)", href or "")
    return m.group(1) if m else (href or "")


def slip_selection(slip: dict, line: float, home: str, away: str, threshold: float) -> Optional[dict]:
    """A seleção "Over <linha>" do total da partida DESTE jogo no cupom."""
    want = f"over {line:g}"
    for s in slip.get("selections") or []:
        name = (s.get("name") or "").strip().lower()
        market = (s.get("market") or "").strip()
        if name != want or not re.match(r"^(Asian\s+)?Total$", market, re.I):
            continue
        parts = re.split(r"\s+-\s+|\s+vs\.?\s+", s.get("event") or "", maxsplit=1)
        if len(parts) == 2 and game_similarity(home, away, parts[0], parts[1]) >= threshold:
            return s
    return None


def parse_amount(text: Optional[str]) -> Optional[float]:
    """'1,234.50' / '$0.00' / '12.5' -> float."""
    if not text:
        return None
    m = re.search(r"\d[\d,]*(\.\d+)?", text)
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def format_stake(value: float) -> str:
    """Valor digitado no campo (US$ com 2 casas, ponto decimal)."""
    return f"{value:.2f}"
