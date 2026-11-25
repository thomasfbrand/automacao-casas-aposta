from bot.tip_parser import parse_tip, is_cancel
from bot.matching import game_similarity, team_similarity
from bot.rules import stake_for, check_limits

FOOTER = """

Canal de Tips (dando pra seguir da pinnacle) acesse aqui 👇🏼
[www.betadormachine.com.br](https://www.betadormachine.com.br)

+18 jogue com responsabilidade | Autorização SPA/MF: 2.102
Ministério da fazenda adverte: aposta não é investimento.
"""


def tip(method, line, league, game, minute, score, stake, footer=True, suffix=""):
    body = (f"Live\nMÉTODO {method}\nENTRADA NO OVER {line} GOLS\n\nLiga: {league}\nJogo: {game}\n"
            f"Tempo decorrido: {minute}\nResultando parcial: {score}\n\n{stake}{suffix}")
    return body + (FOOTER if footer else "")


def test_samples_from_group():
    samples = [
        (tip(2, "1.5", "ALEMANHA: BUNDESLIGA - RODADA 4", "Stuttgart x Dortmund", 71, "0 X 1", "1u @1.80"), 1.5, 1.0, 1.80),
        (tip(2, "2.5", "NORUEGA: ELITESERIEN", "Molde x Aalesund", 65, "0 X 2", "1u @1.80"), 2.5, 1.0, 1.80),
        (tip(1, "1.5", "SUÉCIA: DIVISÃO 2", "Farsta x Karlslund", 65, "0 X 1", "1u @1.80"), 1.5, 1.0, 1.80),
        (tip(8, "0.5", "PAÍS DE GALES", "Connah's Q. x Cardiff Metropolitan", 65, "0 X 0", "1u @1.80", footer=False), 0.5, 1.0, 1.80),
        (tip(1, "1.5", "SUÉCIA", "Herrestads AIF x Kumla", 65, "0 X 1", "1u @1.80", suffix="🔄"), 1.5, 1.0, 1.80),
        (tip(1, "1.5", "ESTÔNIA", "Viimsi JK x Tartu Welco", 65, "0 X 1", "1u @2.00", suffix="✅"), 1.5, 1.0, 2.00),
    ]
    for text, line, units, odd in samples:
        r = parse_tip(text)
        assert r.ok, (r.reason, text)
        assert r.tip.line == line and r.tip.units == units and r.tip.min_odd == odd


def test_fields():
    r = parse_tip(tip(2, "2.5", "BRASIL: BRASILEIRÃO BETANO - RODADA 28", "Atlético-MG x Chapecoense", 65, "1 X 1", "1u @1.80"))
    t = r.tip
    assert (t.home, t.away, t.minute, t.home_goals, t.away_goals, t.method) == ("Atlético-MG", "Chapecoense", 65, 1, 1, 2)


def test_line_mismatch_rejected():
    # over 1.5 com 1x1: já está ganho, linha incoerente com o placar
    r = parse_tip(tip(2, "1.5", "BRASIL", "Atlético-MG x Chapecoense", 65, "1 X 1", "1u @1.80"))
    assert not r.ok and r.reason.startswith("line_mismatch")


def test_pre_game_and_garbage_ignored():
    pre = "PRÉ-LIVE\nMÉTODO 2\nENTRADA NO OVER 2.5 GOLS\nJogo: A x B\n1u @1.80"
    assert parse_tip(pre).reason == "not_live"
    assert parse_tip("bom dia grupo").reason == "not_live"
    assert parse_tip("").reason == "empty"


def test_cancel_detection():
    for msg in ["Cancelada", "apagada, não fazer", "NÃO FAZER", "tip cancelada", "Não faça essa"]:
        assert is_cancel(msg), msg
    assert not is_cancel("boa noite pessoal")
    assert not is_cancel(tip(2, "1.5", "X", "A x B", 65, "0 X 1", "1u @1.80"))


def test_stake_math():
    assert stake_for(0.75, 350) == 262.5
    assert stake_for(1, 2) == 2.0
    assert stake_for(1.75, 350) == 612.5


def test_limits():
    assert check_limits(100, 500, 0, 2000, 1000)[0]
    assert not check_limits(600, 500, 0, 2000, 1000)[0]
    assert not check_limits(100, 500, 1950, 2000, 1000)[0]
    assert not check_limits(100, 500, 0, 2000, 41.75)[0]


def test_team_matching():
    assert team_similarity("Atlético-MG", "Atlético Mineiro") >= 0.7
    assert team_similarity("Chapecoense", "Chapecoense") >= 0.99
    assert team_similarity("Botafogo FR RJ", "Botafogo") >= 0.7
    assert team_similarity("Connah's Q.", "Connahs Quay") >= 0.7
    assert team_similarity("Atlético-MG", "Atlético Madrid") < 0.7
    assert game_similarity("Atlético-MG", "Chapecoense", "Atlético Mineiro", "Chapecoense") >= 0.7
    assert game_similarity("Sevilla", "Barcelona", "Mirassol", "Botafogo") < 0.4
    assert game_similarity("Sevilla", "Barcelona", "Barcelona", "Sevilla") >= 0.9  # ordem invertida


def test_parse_state_mobile_game_header_goals_last_column():
    from bot.casas.pinnacle.parsing import parse_state
    text = "\n".join(["Honduras - Liga Nacional", "AO VIVO", "Ao Vivo Agora", "Juticalpa", "4", "4", "0", "3",
                      "Marathon", "3", "4", "1", "2", "Popular", "Tudo", "Partida", "1x2 - Partida"])
    st = parse_state(text)
    assert (st.home_goals, st.away_goals) == (3, 2) and st.total_goals == 5 and st.live


def test_parse_state_mobile_header_scoreless():
    from bot.casas.pinnacle.parsing import parse_state
    text = "\n".join(["MÉXICO - LIGA MX", "AO VIVO", "Queretaro", "2", "0", "0", "0", "Club León", "1", "1", "0", "0"])
    st = parse_state(text)
    assert (st.home_goals, st.away_goals) == (0, 0)


def test_line_mismatch_only_allowed_in_test_mode():
    t = tip(2, "2.5", "TESTE", "Nova Caledonia x Ilhas Salomao", 8, "0 X 0", "1u @1.10")
    assert parse_tip(t).reason.startswith("line_mismatch")
    r = parse_tip(t, allow_line_mismatch=True)
    assert r.ok and r.tip.line == 2.5 and r.tip.total_goals == 0
