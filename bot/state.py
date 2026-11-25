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
        # casa da aposta: o teto do dia é por casa (cada uma tem a sua moeda; R$ e US$ não se somam).
        # Bancos antigos ganham a coluna; as apostas que já existiam eram todas da Pinnacle.
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(bets)")}
        if "casa" not in cols:
            self.db.execute("ALTER TABLE bets ADD COLUMN casa TEXT DEFAULT 'pinnacle'")
        self.db.commit()

    def seen(self, msg_id: int) -> bool:
        return self.db.execute("SELECT 1 FROM seen WHERE msg_id=?", (msg_id,)).fetchone() is not None

    def mark_seen(self, msg_id: int) -> None:
        self.db.execute("INSERT OR IGNORE INTO seen(msg_id, ts) VALUES(?,?)", (msg_id, time.time()))
        self.db.commit()

    def add_bet(self, game: str, line: float, odd, stake, status: str, receipt: str = "", detail: str = "",
                casa: str = "pinnacle") -> None:
        self.db.execute(
            "INSERT INTO bets(ts, day, game, line, odd, stake, status, receipt, detail, casa)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (time.time(), date.today().isoformat(), game, line, odd, stake, status, receipt, detail, casa))
        self.db.commit()

    def spent_today(self, casa: str | None = None) -> float:
        """Só conta apostas reais (aceitas ou incertas), nunca dry-run. Com `casa`, só as daquela casa."""
        sql = "SELECT COALESCE(SUM(stake),0) FROM bets WHERE day=? AND status IN ('accepted','unknown')"
        args: tuple = (date.today().isoformat(),)
        if casa is not None:
            sql += " AND casa=?"
            args += (casa,)
        row = self.db.execute(sql, args).fetchone()
        return float(row[0] or 0.0)
