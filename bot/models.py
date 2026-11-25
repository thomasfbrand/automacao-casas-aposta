from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GameState:
    minute: Optional[int] = None       # minuto real de jogo (2º tempo = 45 + minutos do tempo)
    home_goals: Optional[int] = None
    away_goals: Optional[int] = None
    live: bool = False
    ended: bool = False
    raw: str = ""

    @property
    def total_goals(self) -> Optional[int]:
        if self.home_goals is None or self.away_goals is None:
            return None
        return self.home_goals + self.away_goals


@dataclass
class BetResult:
    # accepted | dry_run_ok | odd_low | unavailable | unknown | failed
    status: str
    odd: Optional[float] = None
    stake: Optional[float] = None
    receipt: Optional[str] = None
    detail: str = ""
