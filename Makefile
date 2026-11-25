# Atalhos do harness. "make" sozinho mostra esta ajuda.
PY := $(shell for c in .venv/Scripts/python.exe .venv/bin/python $$HOME/venv-pinn/bin/python python3 python; do \
	if "$$c" -c "import sys" >/dev/null 2>&1; then echo $$c; break; fi; done)

.PHONY: ajuda start init test check handoff diagnose tip rodar limpar

ajuda:
	@echo "make start     - comeca a sessao: ambiente + estado + features em aberto"
	@echo "make init      - prepara/confere o ambiente"
	@echo "make test      - roda os testes"
	@echo "make check     - ambiente + contrato + testes (use antes de dizer 'pronto')"
	@echo "make handoff   - checklist de fim de sessão (reprova se faltar algo)"
	@echo "make diagnose LOG=logs/arquivo.log   - resume uma execução"
	@echo "make tip A=\"Time A\" B=\"Time B\" PLACAR=1-0 ODD=1.80 - gera tip.txt de teste"
	@echo "make rodar     - roda uma tip de teste (respeita DRY_RUN do .env)"

init:
	@./init.sh

test:
	@$(PY) -m pytest -q

check:
	@./init.sh --check
	@echo "== Testes =="
	@$(PY) -m pytest -q
	@echo "== Estado limpo =="
	@./scripts/estado_limpo.sh

handoff: check
	@$(PY) tools/handoff.py

start: init
	@echo
	@echo "Features disponiveis (escolha UMA):"
	@$(PY) -c "import json;[print('  ',f['id'],f['state'].ljust(12),f['nome']) for f in json.load(open('features.json'))['features'] if f['state']!='passing']"

diagnose:
	@$(PY) tools/diagnose.py $(LOG)

tip:
	@$(PY) -m tools.make_tip "$(A)" "$(B)" --score $(PLACAR) --min-odd $(ODD) -o tip.txt

rodar:
	@$(PY) main.py --test-tip tip.txt
