"""Funções puras (testáveis sem navegador) que leem os textos da Pinnacle."""
from __future__ import annotations

import re
from typing import Optional, Tuple

from ...models import GameState

_HEADER_WORDS = re.compile(
    r"^(partida|1x2|hdp|ou|handicap|vencedor|ao vivo|ocultar|mais mercados|ver |todas|estat|escanteios|"
    r"total|acima|abaixo|menos|dupla|ambas|popular|tudo|ht$|ft$|intervalo)", re.I)
_CAPS_LEAGUE = re.compile(r"^[A-ZÀ-Ú0-9 .'’\-/]+\s-\s[A-ZÀ-Ú0-9 .'’\-/]+$")


def parse_money(s: str) -> Optional[float]:
    """'41.75' | '41,75' | '1.234,56' | '12,855.00' -> float."""
    if s is None:
        return None
    s = s.strip()
    if not s:
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_card_teams(lines: list[str]) -> Optional[Tuple[str, str]]:
    """Dos textos de um card da lista ao vivo, tira (mandante, visitante)."""
    cands: list[str] = []
    for ln in lines:
        t = ln.strip()
        if not t or not re.search(r"[A-Za-zÀ-ú]", t):
            continue
        if _HEADER_WORDS.match(t) or _CAPS_LEAGUE.match(t):
            continue
        if re.match(r"^[ou]\s*\d", t, re.I) or re.match(r"^\d[Hh]\b", t) or t.startswith("+"):
            continue
        cands.append(t)
        if len(cands) == 2:
            break
    return (cands[0], cands[1]) if len(cands) == 2 else None


def parse_state(text: str) -> GameState:
    head = (text or "")[:2500]
    lines = [ln.strip() for ln in head.splitlines() if ln.strip()]
    st = GameState(raw="\n".join(lines[:25]))
    st.live = bool(re.search(r"\bAO VIVO\b", head))
    st.ended = bool(re.search(r"\b(encerrad[oa]|finalizad[oa]|fim de jogo|full time|terminad[oa])\b", head, re.I))

    m = re.search(r"(\d)\s*[ºo°ª]?\s*Tempo\D{0,8}(\d{1,3})\s*['’′]?", head, re.I)
    if m:
        half, mm = int(m.group(1)), int(m.group(2))
        st.minute = 45 + mm if half == 2 else mm
    else:
        m2 = re.search(r"\b(\d)H\s*(\d{1,3})\s*['’′]", head)
        if m2:
            half, mm = int(m2.group(1)), int(m2.group(2))
            st.minute = 45 + mm if half == 2 else mm
        elif re.search(r"\b(intervalo|HT)\b", head, re.I):
            st.minute = 45

    for ln in lines[:60]:
        if re.search(r"Tempo", ln, re.I):
            continue
        ms = re.match(r"^(.+?)\s+(\d{1,2})\s*[-–]\s*(\d{1,2})\s+(.+)$", ln)
        if ms:
            st.home_goals, st.away_goals = int(ms.group(2)), int(ms.group(3))
            break
    if st.home_goals is None:
        rows = _parse_team_rows(lines[:80])
        if rows:
            st.home_goals, st.away_goals = rows
    return st


_NOT_TEAM = re.compile(r"^(ao vivo|ao vivo agora|popular|tudo|partida|todas|ocultar|bem-vindo|entrar|cadastro|"
                       r"h[aá] um atraso|fa[cç]a login|pesquisar|boletim)", re.I)


def _parse_team_rows(lines: list[str]) -> Optional[Tuple[int, int]]:
    """Cabeçalho da tela do jogo da Pinnacle (celular): cada time numa linha seguida de colunas numéricas
    [escanteios, amarelos, vermelhos, GOLS]; o placar é o ÚLTIMO número de cada time.
      Juticalpa | 4 | 4 | 0 | 3 | Marathon | 3 | 4 | 1 | 2   ->  (3, 2)"""
    found: list[int] = []
    i = 0
    while i < len(lines) and len(found) < 2:
        t = lines[i]
        if re.search(r"[A-Za-zÀ-ú]", t) and not _NOT_TEAM.match(t) and " - " not in t and not re.match(r"^\d", t):
            nums: list[int] = []
            j = i + 1
            while j < len(lines) and re.fullmatch(r"\d{1,2}", lines[j]) and len(nums) < 6:
                nums.append(int(lines[j]))
                j += 1
            if len(nums) >= 2 or (len(nums) == 1 and len(found) == 1):
                found.append(nums[-1])
                i = j
                continue
        i += 1
    return (found[0], found[1]) if len(found) == 2 else None


def parse_confirm(text: str) -> Optional[Tuple[float, float, float]]:
    """'arriscar 2.00 BRL para ganhar 4.78 BRL' -> (stake, lucro, odd implícita)."""
    m = re.search(r"arriscar\s+([\d.,]+)\s*BRL\s+para\s+ganhar\s+([\d.,]+)", text or "", re.I)
    if not m:
        return None
    risk, win = parse_money(m.group(1)), parse_money(m.group(2))
    if not risk or win is None:
        return None
    return risk, win, round(1 + win / risk, 3)


def parse_slip_odd(text: str, line: float) -> Optional[float]:
    """Odd do 'Mais de <linha>' no cupom (usa o valor novo se houve mudança)."""
    ch = re.search(r"Odds have changed from\s*(\d+\.\d+)\s*to\s*(\d+\.\d+)", text or "", re.I)
    if ch:
        return float(ch.group(2))
    m = re.search(rf"Mais de\s*{re.escape(str(line))}\s+(\d+\.\d{{2,3}})", text or "", re.I)
    return float(m.group(1)) if m else None


def state_from_scoreboard(sb: Optional[dict]) -> Optional[GameState]:
    """Estado a partir do placar estruturado (js.READ_SCOREBOARD).
    Linha de cada time: [escanteios, amarelos, vermelhos, GOLS] -> gols = última coluna numérica."""
    if not sb or len(sb.get("teams") or []) < 2:
        return None
    goals = []
    for t in sb["teams"][:2]:
        nums = [c for c in (t.get("cols") or []) if re.fullmatch(r"\d{1,2}", c or "")]
        if not nums:
            return None
        goals.append(int(nums[-1]))
    clock = sb.get("clock") or ""
    st = parse_state(clock)           # reaproveita a leitura de minuto ("1º Tempo - 12'", "Intervalo")
    st.home_goals, st.away_goals = goals
    st.live = bool(sb.get("live")) or st.live
    st.raw = f"{clock} | " + " | ".join(f"{t.get('name')} {t.get('cols')}" for t in sb["teams"][:2])
    return st
