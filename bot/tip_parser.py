"""Interpreta as mensagens do grupo.

Regras:
- só vale mensagem cuja primeira linha é "Live" (pré-jogo é ignorado);
- só vale over de gols, e a linha tem que ser (gols do placar + 0,5);
- emojis (✅ 🔄 etc.) são ignorados;
- mensagens de cancelamento ("cancelada", "apagada", "não fazer"...) são detectadas à parte.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .matching import normalize

_LIVE_RE = re.compile(r"^\W*live\b", re.I)
_METHOD_RE = re.compile(r"M[ÉE]TODO\s*(\d+)", re.I)
_LINE_RE = re.compile(r"ENTRADA\s+NO\s+(OVER|UNDER)\s+(\d+(?:[.,]\d+)?)\s*GOLS?", re.I)
_LEAGUE_RE = re.compile(r"^\s*Liga\s*:\s*(.+?)\s*$", re.I | re.M)
_GAME_RE = re.compile(r"^\s*Jogo\s*:\s*(.+?)\s*$", re.I | re.M)
_MIN_RE = re.compile(r"Tempo\s+decorrido\s*:\s*(\d+)", re.I)
_SCORE_RE = re.compile(r"Result\w*\s+parcial\s*:\s*(\d+)\s*[xX×\-]\s*(\d+)", re.I)
_STAKE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*u\s*@\s*(\d+(?:[.,]\d+)?)", re.I)

_CANCEL_RE = re.compile(
    r"\b(cancelad[ao]s?|cancelou|apagad[ao]s?|anulad[ao]s?|desconsider\w+|ignor\w+|"
    r"n[aã]o\s+(fazer|fa[cç]a|fazem|entrar|entrem|apostar|apostem|valid\w+)|"
    r"sem\s+entrada|tip\s+cancelada)\b",
    re.I,
)


@dataclass(frozen=True)
class Tip:
    method: int
    line: float
    league: str
    home: str
    away: str
    minute: int
    home_goals: int
    away_goals: int
    units: float
    min_odd: float
    raw: str

    @property
    def total_goals(self) -> int:
        return self.home_goals + self.away_goals

    @property
    def game_key(self) -> str:
        return f"{normalize(self.home)}|{normalize(self.away)}"

    def describe(self) -> str:
        return (f"{self.home} x {self.away} | over {self.line} | {self.home_goals}x{self.away_goals} "
                f"aos {self.minute}' | {self.units}u @ {self.min_odd} (método {self.method})")


@dataclass(frozen=True)
class ParseResult:
    tip: Optional[Tip]
    reason: str = "ok"

    @property
    def ok(self) -> bool:
        return self.tip is not None


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def is_cancel(text: str) -> bool:
    """Mensagem curta que cancela uma tip. Uma tip nunca é cancelamento."""
    t = (text or "").strip()
    if not t or _LIVE_RE.match(t.splitlines()[0]) or len(t) > 240:
        return False
    return bool(_CANCEL_RE.search(t))


def parse_tip(text: str, allow_line_mismatch: bool = False) -> ParseResult:
    t = (text or "").strip()
    if not t:
        return ParseResult(None, "empty")
    first = t.splitlines()[0]
    if not _LIVE_RE.match(first):
        return ParseResult(None, "not_live")

    m_line = _LINE_RE.search(t)
    if not m_line:
        return ParseResult(None, "no_market")
    if m_line.group(1).upper() != "OVER":
        return ParseResult(None, "not_over")
    line = _num(m_line.group(2))

    m_game = _GAME_RE.search(t)
    m_min = _MIN_RE.search(t)
    m_score = _SCORE_RE.search(t)
    m_stake = _STAKE_RE.search(t)
    if not (m_game and m_min and m_score and m_stake):
        return ParseResult(None, "missing_fields")

    parts = re.split(r"\s+x\s+", m_game.group(1).strip(), maxsplit=1, flags=re.I)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return ParseResult(None, "bad_game")
    home, away = parts[0].strip(), parts[1].strip()

    hg, ag = int(m_score.group(1)), int(m_score.group(2))
    if not allow_line_mismatch and abs(line - (hg + ag + 0.5)) > 1e-9:   # allow_*: SÓ para teste
        return ParseResult(None, f"line_mismatch (over {line} com placar {hg}x{ag})")

    m_method = _METHOD_RE.search(t)
    m_league = _LEAGUE_RE.search(t)
    tip = Tip(
        method=int(m_method.group(1)) if m_method else 0,
        line=line,
        league=m_league.group(1) if m_league else "",
        home=home,
        away=away,
        minute=int(m_min.group(1)),
        home_goals=hg,
        away_goals=ag,
        units=_num(m_stake.group(1)),
        min_odd=_num(m_stake.group(2)),
        raw=t,
    )
    return ParseResult(tip)
