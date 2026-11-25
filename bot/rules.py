from __future__ import annotations

from typing import Tuple


def stake_for(units: float, unit_value: float) -> float:
    """1u = unit_value reais. 0,75u x 350 = 262,50."""
    return round(units * unit_value, 2)


def check_limits(stake: float, max_stake: float, spent_today: float, daily_max_total: float,
                 balance: float | None) -> Tuple[bool, str]:
    if stake <= 0:
        return False, "valor da aposta zerado"
    if stake > max_stake + 1e-9:
        return False, f"aposta de R$ {stake:.2f} passa do teto por aposta (R$ {max_stake:.2f})"
    if spent_today + stake > daily_max_total + 1e-9:
        return False, (f"aposta de R$ {stake:.2f} estouraria o teto do dia "
                       f"(já apostado R$ {spent_today:.2f} de R$ {daily_max_total:.2f})")
    if balance is not None and stake > balance + 1e-9:
        return False, f"saldo insuficiente (saldo R$ {balance:.2f}, aposta R$ {stake:.2f})"
    return True, "ok"
