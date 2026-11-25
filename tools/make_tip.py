"""Gera um arquivo de tip no formato do grupo, para testar com um jogo AO VIVO agora.

  python -m tools.make_tip "Mirassol" "Botafogo" --score 2-1 --minute 65 --min-odd 1.80 -o tip.txt
  python main.py --test-tip tip.txt

A linha é calculada sozinha (gols do placar + 0,5), como o grupo faz.
"""
import argparse

TEMPLATE = """Live
MÉTODO 2
ENTRADA NO OVER {line} GOLS

Liga: TESTE
Jogo: {home} x {away}
Tempo decorrido: {minute}
Resultando parcial: {hg} X {ag}

{units}u @{odd}
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("home")
    ap.add_argument("away")
    ap.add_argument("--score", required=True, help="placar atual, ex: 1-1")
    ap.add_argument("--minute", type=int, default=65)
    ap.add_argument("--units", type=float, default=1.0)
    ap.add_argument("--min-odd", type=float, default=1.80)
    ap.add_argument("--line", type=float, help="linha do over (padrão: gols + 0,5). Fora do padrão só roda com --allow-line-mismatch")
    ap.add_argument("-o", "--out", default="tip.txt")
    a = ap.parse_args()
    hg, ag = (int(x) for x in a.score.split("-"))
    text = TEMPLATE.format(line=a.line if a.line is not None else hg + ag + 0.5, home=a.home, away=a.away, minute=a.minute, hg=hg, ag=ag,
                           units=f"{a.units:g}", odd=f"{a.min_odd:.2f}")
    open(a.out, "w", encoding="utf-8").write(text)
    print(f"tip gravada em {a.out}:\n{text}")


if __name__ == "__main__":
    main()
