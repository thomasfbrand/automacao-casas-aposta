"""Comparação aproximada de nomes de times.

A tip diz "Atlético-MG", a casa diz "Atlético Mineiro"; a tip diz
"Connah's Q.", a casa diz "Connahs Quay". Aqui normalizamos e comparamos por
tokens + similaridade de texto.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

# palavras que não ajudam a distinguir times
_STOP = {
    "fc", "cf", "sc", "ac", "as", "cd", "cs", "fk", "sk", "if", "bk", "ik", "sv", "vfb", "vfl",
    "club", "clube", "de", "da", "do", "dos", "das", "del", "la", "el", "the", "and", "e",
    "fr", "u17", "u18", "u19", "u20", "u21", "u23", "w", "women", "feminino",
}

# siglas de estado -> nome que as casas costumam usar
_ALIAS = {
    "mg": "mineiro",
    "pr": "paranaense",
    "go": "goianiense",
    "sp": "paulista",
    "rj": "",
    "rs": "",
}


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def tokens(name: str) -> list[str]:
    s = _strip_accents(name).lower().replace("'", "").replace("’", "")
    raw = re.findall(r"[a-z0-9]+\.?", s)
    out: list[str] = []
    for t in raw:
        clean = t.rstrip(".")
        if not clean or clean in _STOP:
            continue
        if clean in _ALIAS:
            clean = _ALIAS[clean]
            if not clean:
                continue
        # marca abreviação ("q.") para permitir casar por prefixo
        out.append(clean + ("." if t.endswith(".") else ""))
    return out


def normalize(name: str) -> str:
    return " ".join(t.rstrip(".") for t in tokens(name))


def _tok_match(a: str, b: str) -> bool:
    a_abbr, b_abbr = a.endswith("."), b.endswith(".")
    a, b = a.rstrip("."), b.rstrip(".")
    if a == b:
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    short_abbr = a_abbr if short is a else b_abbr
    if long_.startswith(short) and (len(short) >= 4 or short_abbr):
        return True
    return SequenceMatcher(None, a, b).ratio() >= 0.88


def team_similarity(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    small, large = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    matched = sum(1 for t in small if any(_tok_match(t, u) for u in large))
    token_score = matched / len(small)
    text_score = SequenceMatcher(None, " ".join(x.rstrip(".") for x in ta),
                                 " ".join(x.rstrip(".") for x in tb)).ratio()
    return round(0.6 * token_score + 0.4 * text_score, 4)


def game_similarity(tip_home: str, tip_away: str, cand_home: str, cand_away: str) -> float:
    """Menor similaridade entre os dois times (mandante x mandante, visitante x visitante).

    Também testa a ordem invertida (algumas fontes invertem) e devolve a melhor.
    """
    straight = min(team_similarity(tip_home, cand_home), team_similarity(tip_away, cand_away))
    swapped = min(team_similarity(tip_home, cand_away), team_similarity(tip_away, cand_home))
    return max(straight, swapped)
