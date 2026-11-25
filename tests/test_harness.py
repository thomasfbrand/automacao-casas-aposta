"""O harness também precisa de teste: se ele deixar passar, a próxima sessão começa cega."""
from pathlib import Path
import json
import os
import subprocess
import sys

RAIZ = Path(__file__).resolve().parent.parent


def test_agents_md_e_progress_cabem_no_contexto():
    """Arquivo de contexto gigante é anti-padrão: o agente ignora ou gasta janela à toa."""
    assert len(Path(RAIZ / "AGENTS.md").read_text(encoding="utf-8").splitlines()) <= 100
    assert len(Path(RAIZ / "PROGRESS.md").read_text(encoding="utf-8").splitlines()) <= 120


def test_agents_md_aponta_para_arquivos_que_existem():
    texto = (RAIZ / "AGENTS.md").read_text(encoding="utf-8")
    import re
    for caminho in set(re.findall(r"`([\w./-]+\.(?:md|json|sh|py))`", texto)):
        assert (RAIZ / caminho).exists(), f"AGENTS.md cita {caminho}, que não existe"


def test_wip_no_maximo_um():
    feats = json.loads((RAIZ / "features.json").read_text(encoding="utf-8"))["features"]
    ativas = [f["id"] for f in feats if f["state"] == "active"]
    assert len(ativas) <= 1, f"WIP>1: {ativas}"


def test_toda_feature_tem_comando_de_verificacao():
    feats = json.loads((RAIZ / "features.json").read_text(encoding="utf-8"))["features"]
    for f in feats:
        assert f.get("verify"), f"{f['id']} não diz como verificar que está pronta"
        assert f["state"] in ("not_started", "active", "blocked", "passing"), f["state"]


def _handoff():
    sys.path.insert(0, str(RAIZ / "tools"))
    import handoff
    return handoff


def test_handoff_reprova_progress_que_nao_mudou():
    """O coração do ritual: trabalho feito + PROGRESS igual = sessão não encerrada."""
    h = _handoff()
    texto = "# PROGRESS\n\n## Em andamento\n\nnada\n"
    assert h.progress_ficou_igual(texto, texto) is True
    assert h.progress_ficou_igual(texto, texto.replace("nada", "F11 parou na tela de login")) is False


def test_handoff_nao_aceita_o_proprio_bloco_automatico_como_atualizacao():
    """A ferramenta escreve o bloco de verificação; isso NÃO conta como atualizar."""
    h = _handoff()
    base = "# PROGRESS\n\n## Última verificação executada\n\n```\n2026-11-01  make check  ->  1 passed\n```\n"
    so_o_bloco = base.replace("2026-11-01  make check  ->  1 passed", "2026-11-25  make check  ->  50 passed")
    assert h.progress_ficou_igual(base, so_o_bloco) is True, "o bloco gerado não pode contar como trabalho"
    com_texto = so_o_bloco + "\n## Em andamento\n\nF11 parou no login\n"
    assert h.progress_ficou_igual(base, com_texto) is False


def test_segredos_fora_do_git():
    rastreados = subprocess.run(["git", "ls-files"], cwd=RAIZ, capture_output=True, text=True).stdout
    for proibido in (".env\n", ".session", "browser_profile/"):
        assert proibido not in rastreados, f"segredo versionado: {proibido}"
