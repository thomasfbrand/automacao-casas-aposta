"""Encerra a sessão: junta os fatos, grava no diário e exige o que só a pessoa sabe.

  python tools/handoff.py            # verifica e grava
  python tools/handoff.py --check    # só verifica (não escreve)

Por que existe: PROGRESS.md escrito de memória envelhece e incha. Aqui os fatos
(commits, testes, features) são coletados automaticamente e o histórico antigo vai
para docs/diario.md, deixando o PROGRESS.md curto — que é o que a próxima sessão lê.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PROGRESS = RAIZ / "PROGRESS.md"
DIARIO = RAIZ / "docs" / "diario.md"
MARCADOR = RAIZ / ".harness-session"
LIMITE_LINHAS = 120          # PROGRESS.md acima disso para de caber no contexto com folga
MAX_SESSOES_NO_PROGRESS = 3


def git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True).stdout.strip()
    except Exception:
        return ""


def inicio_da_sessao() -> tuple[str, str]:
    if MARCADOR.exists():
        dados = dict(l.split("=", 1) for l in MARCADOR.read_text().splitlines() if "=" in l)
        return dados.get("HEAD", ""), dados.get("INICIO", "")
    return "", ""


BLOCO_AUTOMATICO = re.compile(r"```\n\d{4}-\d{2}-\d{2}\s+make check.*?```", re.S)


def sem_bloco_automatico(texto: str) -> str:
    """Texto do PROGRESS.md sem o bloco que esta ferramenta mesma escreve."""
    return re.sub(r"\s+", " ", BLOCO_AUTOMATICO.sub("", texto or "")).strip()


def progress_ficou_igual(progress_inicial: str, progress_atual: str) -> bool:
    """Regra do handoff, isolada para poder ser testada sem git nem subprocesso.

    Compara só a parte escrita à mão: o bloco de verificação que esta ferramenta
    gera é descontado, senão o handoff se auto-aprovaria.
    """
    return sem_bloco_automatico(progress_inicial) == sem_bloco_automatico(progress_atual)


def erro(msg: str, conserto: str) -> None:
    print(f"  [ERRO] {msg}\n         -> {conserto}")


def main() -> int:
    so_verificar = "--check" in sys.argv
    head_inicial, inicio = inicio_da_sessao()
    problemas = 0

    commits = git("log", "--oneline", f"{head_inicial}..HEAD") if head_inicial else ""
    lista_commits = [c for c in commits.splitlines() if c]
    pendente = git("status", "--porcelain")
    # "atualizado" = a PARTE ESCRITA À MÃO mudou. O bloco de verificação é gerado por esta
    # ferramenta, então ele é descontado — senão o handoff se auto-aprovaria.
    atual = PROGRESS.read_text(encoding="utf-8")
    inicial = git("show", f"{head_inicial}:PROGRESS.md") if head_inicial else ""
    mudou_progress = bool(inicial) and not progress_ficou_igual(inicial, atual)

    print("== Handoff ==")
    if not head_inicial:
        print("  [!]    sem marcador de sessão (./init.sh não foi rodado); verificação parcial")
    else:
        print(f"  [ok]   sessão iniciada em {inicio} ({len(lista_commits)} commit(s) desde então)")

    # 1) features: WIP<=1 e nenhuma 'active' largada sem verificação
    feats = json.loads((RAIZ / "features.json").read_text(encoding="utf-8"))["features"]
    ativas = [f for f in feats if f["state"] == "active"]
    if len(ativas) > 1:
        erro(f"{len(ativas)} features 'active' ao mesmo tempo", "WIP=1: deixe só uma")
        problemas += 1
    elif ativas:
        print(f"  [!]    feature {ativas[0]['id']} continua 'active': diga no PROGRESS.md onde parou")
    else:
        print("  [ok]   nenhuma feature pela metade (WIP=0)")

    # 2) PROGRESS.md precisa ter sido tocado se houve trabalho
    if lista_commits and not mudou_progress:
        erro("houve trabalho nesta sessão mas o PROGRESS.md continua igual",
             "escreva à mão: o que ficou pronto, o que quebrou e o próximo passo")
        problemas += 1
    elif lista_commits:
        print("  [ok]   PROGRESS.md atualizado à mão nesta sessão")
    else:
        print("  [ok]   nenhum commit nesta sessão (nada a relatar)")

    # 3) PROGRESS.md curto (contexto é recurso escasso)
    linhas = PROGRESS.read_text(encoding="utf-8").splitlines()
    if len(linhas) > LIMITE_LINHAS:
        erro(f"PROGRESS.md com {len(linhas)} linhas (máximo {LIMITE_LINHAS})",
             "mande o histórico antigo para docs/diario.md")
        problemas += 1
    else:
        print(f"  [ok]   PROGRESS.md com {len(linhas)} linhas")

    # 4) testes
    if os.environ.get("HARNESS_PULAR_TESTES"):
        # o teste do proprio harness chama esta ferramenta: sem isto, ela chamaria a suite de volta
        r, resumo = subprocess.CompletedProcess([], 0), "(pulados a pedido do chamador)"
    else:
        # sem -q aqui: o pytest.ini ja passa -q, e -qq apaga a linha de resumo
        r = subprocess.run([sys.executable, "-m", "pytest"], cwd=RAIZ, capture_output=True, text=True)
        resumo = next((l for l in reversed((r.stdout + r.stderr).splitlines())
                       if "passed" in l or "failed" in l or "error" in l), "sem saida do pytest")
        resumo = re.sub(r"\s+", " ", resumo).strip()
    resumo = re.sub(r"\s+", " ", resumo).strip()
    if r.returncode != 0:
        erro(f"testes falhando: {resumo}", "conserte ou registre como bloqueio no PROGRESS.md")
        problemas += 1
    else:
        print(f"  [ok]   testes: {resumo}")

    if so_verificar:
        return 1 if problemas else 0

    # 5) grava a sessão no diário (histórico completo, fora do contexto do dia a dia)
    hoje = datetime.now().strftime("%d/%m/%Y %H:%M")
    entrada = [f"\n## {hoje}", f"- testes: {resumo}"]
    if lista_commits:
        entrada.append("- commits:")
        entrada += [f"    - {c}" for c in lista_commits]
    else:
        entrada.append("- commits: nenhum")
    if ativas:
        entrada.append(f"- feature em andamento ao sair: {ativas[0]['id']} {ativas[0]['nome']}")
    DIARIO.parent.mkdir(exist_ok=True)
    if not DIARIO.exists():
        DIARIO.write_text("# Diário de sessões\n\nHistórico completo. O PROGRESS.md fica curto de propósito;"
                          " o que saiu de lá está aqui.\n", encoding="utf-8")
    DIARIO.write_text(DIARIO.read_text(encoding="utf-8") + "\n".join(entrada) + "\n", encoding="utf-8")

    # 6) atualiza o bloco de verificação do PROGRESS.md com o resultado REAL
    texto = PROGRESS.read_text(encoding="utf-8")
    bloco = f"```\n{datetime.now():%Y-%m-%d}  make check  ->  {resumo}\n```"
    novo = re.sub(r"```\n\d{4}-\d{2}-\d{2}\s+make check.*?```", bloco, texto, flags=re.S)
    if novo == texto:
        novo = texto.rstrip() + f"\n\n## Última verificação executada\n\n{bloco}\n"
    PROGRESS.write_text(novo, encoding="utf-8")
    print(f"  [ok]   diário atualizado (docs/diario.md) e verificação registrada no PROGRESS.md")

    print()
    if problemas:
        print(f"{problemas} pendência(s). A sessão NÃO está encerrada.")
        return 1
    print("Sessão encerrada corretamente. Falta só commitar o que o handoff escreveu:")
    print("  git add -A && git commit -m \"handoff: <resumo em uma linha>\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
