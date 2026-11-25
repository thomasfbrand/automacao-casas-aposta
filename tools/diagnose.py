"""Resume uma execução do robô: o que aconteceu, onde parou, o que olhar.

  python tools/diagnose.py                      # o log mais recente de logs/
  python tools/diagnose.py logs/robo_2026-09-21.log
  python tools/diagnose.py teste28.log

Serve para não precisar ler 500 linhas de log à mão a cada teste.
"""
from __future__ import annotations

import glob
import os
import re
import sys
from datetime import datetime

# (rótulo, regex) — a ordem é a do fluxo, para a linha do tempo ficar legível
MARCOS = [
    ("login", r"login conclu\S+do"),
    ("codigo-email", r"c\S+digo encontrado no e-mail"),
    ("tip", r"Nova tip: (.+?)(?:\||$)"),
    ("jogo-achado", r"lista: (?:achei|abri) \((.+?)\)"),
    ("jogo-nao-achado", r"nenhum bate com"),
    ("monitorando", r"Monitorando (.+?) \("),
    ("selecao", r"sele\S+o confirmada"),
    ("aposta-tentativa", r"confirma\S+o \d+: cliquei em SIM"),
    ("aposta-aceita", r"APOSTA REALIZADA|Bet Accepted"),
    ("aposta-devolvida", r"aposta N\S+O entrou"),
    ("encerrou", r"Encerrei (.+?):"),
    ("falhou", r"Falha ao apostar[^:]*: (.+?)(?:\(tentativa|$)"),
    ("desistiu", r"Desisti de"),
]
ERRO_RE = re.compile(r"(WARNING|ERROR|Traceback|Timeout \d+ms exceeded|N[AÃ]O (abriu|entrou))", re.I)
ODD_RE = re.compile(r"monitor: over ([\d.]+) odd=([\d.]+|None) status=(\w+)")
CAPTURA_RE = re.compile(r"\[(?:snap|painel) ([\w.]+)\]|screenshot salvo em \S*?([\w.]+)\.png")
HORA_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")


def ler(caminho: str) -> str:
    bruto = open(caminho, "rb").read()
    texto = bruto.decode("utf-16") if bruto[:2] in (b"\xff\xfe", b"\xfe\xff") else bruto.decode("utf-8", "replace")
    # o PowerShell injeta o eco do comando como se fosse erro
    texto = re.sub(r"At line:1.*?NativeCommandError\s*\n", "", texto, flags=re.S)
    return re.sub(r"Call log:.*?(?=\n\d{4}-\d{2}-\d{2}|\Z)", "[call log omitido]\n", texto, flags=re.S)


def hora(linha: str) -> str:
    m = HORA_RE.match(linha)
    return m.group(1)[11:] if m else "  :  :  "


def main() -> int:
    alvo = sys.argv[1] if len(sys.argv) > 1 else None
    if not alvo:
        cands = sorted(glob.glob("logs/*.log") + glob.glob("teste*.log"), key=os.path.getmtime)
        if not cands:
            print("Nenhum log encontrado em logs/ nem teste*.log"); return 1
        alvo = cands[-1]
    if not os.path.exists(alvo):
        print(f"Não achei {alvo}"); return 1

    texto = ler(alvo)
    linhas = texto.splitlines()
    print(f"== {alvo}  ({len(linhas)} linhas, {datetime.fromtimestamp(os.path.getmtime(alvo)):%d/%m %H:%M}) ==\n")

    print("-- linha do tempo --")
    vistos = 0
    for ln in linhas:
        for rotulo, padrao in MARCOS:
            m = re.search(padrao, ln)
            if m:
                extra = (m.group(1)[:60] if m.groups() and m.group(1) else "")
                print(f"  {hora(ln)}  {rotulo:18} {extra}")
                vistos += 1
                break
    if not vistos:
        print("  (nenhum marco conhecido — log muito curto ou de outro formato)")

    odds = [(hora(ln), *ODD_RE.search(ln).groups()) for ln in linhas if ODD_RE.search(ln)]
    if odds:
        validas = [float(o[2]) for o in odds if o[2] != "None"]
        print(f"\n-- monitor da odd ({len(odds)} leituras) --")
        print(f"  linha over {odds[0][1]}  |  primeira {odds[0][2]}  última {odds[-1][2]}"
              + (f"  |  mín {min(validas):.3f}  máx {max(validas):.3f}" if validas else "")
              + f"  |  {sum(1 for o in odds if o[2]=='None')} leitura(s) indisponível")

    erros = [ln for ln in linhas if ERRO_RE.search(ln) and "call log" not in ln]
    print(f"\n-- avisos e erros ({len(erros)}) --")
    for ln in erros[-8:]:
        print("  " + re.sub(r"\s+", " ", ln.strip())[:150])
    if not erros:
        print("  nenhum")

    capturas = {m.group(1) or m.group(2) for ln in linhas for m in [CAPTURA_RE.search(ln)] if m}
    if capturas:
        print(f"\n-- capturas salvas (olhe em inspect_out/) --")
        print("  " + ", ".join(sorted(capturas)[:12]))

    print("\n-- conclusão --")
    if re.search(r"APOSTA REALIZADA|Bet Accepted", texto):
        print("  Aposta ACEITA. Confira o bilhete na mensagem do Telegram.")
    elif "sem resposta da casa" in texto:
        print("  Resultado INCERTO: a casa não respondeu. Confira 'Minhas Apostas' ANTES de repetir.")
    elif re.search(r"Encerrei .*?: a linha", texto):
        print("  Encerrou porque a linha sumiu (provável gol). Comportamento esperado.")
    elif "Desisti de" in texto or "Falha ao apostar" in texto:
        print("  FALHOU antes de apostar. Veja os erros acima e o HTML da captura correspondente.")
    elif "Monitorando" in texto:
        print("  Ficou monitorando e a odd não chegou ao mínimo (ou a execução foi interrompida).")
    else:
        print("  Não chegou a monitorar nenhum jogo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
