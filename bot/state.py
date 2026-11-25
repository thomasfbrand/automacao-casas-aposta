"""Memória em disco: mensagens já vistas (não reprocessa ao reiniciar) e apostas feitas."""
from __future__ import annotations

import sqlite3
import time
from datetime import date


class Store:
    def __init__(self, path: str):
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS seen(msg_id INTEGER PRIMARY KEY, ts REAL)")
        self.db.execute("""CREATE TABLE IF NOT EXISTS bets(
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, day TEXT, game TEXT, line REAL,
            odd REAL, stake REAL, status TEXT, receipt TEXT, detail TEXT)""")
        self.db.commit()

    def seen(self, msg_id: int) -> bool:
        return self.db.execute("SELECT 1 FROM seen WHERE msg_id=?", (msg_id,)).fetchone() is not None

    def mark_seen(self, msg_id: int) -> None:
        self.db.execute("INSERT OR IGNORE INTO seen(msg_id, ts) VALUES(?,?)", (msg_id, time.time()))
        self.db.commit()

    def add_bet(self, game: str, line: float, odd, stake, status: str, receipt: str = "", detail: str = "") -> None:
        self.db.execute(
            "INSERT INTO bets(ts, day, game, line, odd, stake, status, receipt, detail) VALUES(?,?,?,?,?,?,?,?,?)",
            (time.time(), date.today().isoformat(), game, line, odd, stake, status, receipt, detail))
        self.db.commit()

    def spent_today(self) -> float:
        """Só conta apostas reais (aceitas ou incertas), nunca dry-run."""
        row = self.db.execute(
            "SELECT COALESCE(SUM(stake),0) FROM bets WHERE day=? AND status IN ('accepted','unknown')",
            (date.today().isoformat(),)).fetchone()
        return float(row[0] or 0.0)
