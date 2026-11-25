#!/usr/bin/env bash
# Prepara e confere o ambiente. Rode ao abrir uma sessão de trabalho.
# Uso: ./init.sh            (confere e instala o que falta)
#      ./init.sh --check    (só confere, não instala; usado pelo make check)
set -uo pipefail
cd "$(dirname "$0")"
SO_CHECAR=${1:-}
ERROS=0
ok()   { printf '  [ok]   %s\n' "$1"; }
aviso(){ printf '  [!]    %s\n' "$1"; }
erro() { printf '  [ERRO] %s\n' "$1"; ERROS=$((ERROS+1)); }

echo "== Ambiente =="
# escolhe o primeiro python que REALMENTE roda aqui (a pasta pode ter um .venv de outro SO)
PY=""
for c in ".venv/Scripts/python.exe" ".venv/bin/python" "$HOME/venv-pinn/bin/python" python3 python; do
  if "$c" -c "import sys" >/dev/null 2>&1; then PY="$c"; break; fi
done
[ -n "$PY" ] || { erro "Python não encontrado"; exit 1; }
ok "python: $PY ($($PY -V 2>&1))"

if ! $PY -c "import telethon, playwright, dotenv, pytest" 2>/dev/null; then
  if [ "$SO_CHECAR" = "--check" ]; then
    erro "faltam dependências (rode ./init.sh sem --check)"
  else
    aviso "instalando dependências..."
    $PY -m pip install -q -r requirements.txt && ok "dependências instaladas" || erro "falha ao instalar"
  fi
else
  ok "dependências presentes (telethon, playwright, dotenv, pytest)"
fi

echo "== Configuração =="
if [ -f .env ]; then
  ok ".env existe"
  for v in TG_API_ID TG_API_HASH TG_CHANNEL PINNACLE_USER PINNACLE_PASS GMAIL_USER GMAIL_APP_PASSWORD; do
    grep -qE "^$v=.+" .env || aviso "$v vazio no .env"
  done
  MODO=$(grep -E "^DRY_RUN=" .env | cut -d= -f2)
  UNIDADE=$(grep -E "^UNIT_VALUE=" .env | cut -d= -f2)
  if [ "${MODO,,}" = "false" ]; then
    printf '  [!]    APOSTAS REAIS ligadas (DRY_RUN=false, 1u = R$ %s)\n' "${UNIDADE:-?}"
  else
    ok "DRY_RUN=$MODO (nenhuma aposta é confirmada)"
  fi
else
  erro ".env não existe (copie de .env.example e preencha)"
fi
[ -f "$(grep -E '^TG_SESSION=' .env 2>/dev/null | cut -d= -f2).session" ] \
  && ok "sessão do Telegram salva" || aviso "sem sessão do Telegram (rode: python -m tools.setup_telegram)"

echo "== Repositório =="
git rev-parse --is-inside-work-tree >/dev/null 2>&1 && ok "git iniciado" || erro "sem git"
git check-ignore -q .env 2>/dev/null && ok ".env está fora do git" || erro ".env NÃO está no .gitignore"
for f in AGENTS.md PROGRESS.md features.json docs/objetivos.md; do
  [ -f "$f" ] && ok "$f" || erro "falta $f"
done
ATIVAS=$($PY -c "import json;print(sum(1 for f in json.load(open('features.json'))['features'] if f['state']=='active'))" 2>/dev/null || echo "")
if [ -z "$ATIVAS" ]; then erro "não consegui ler features.json"
elif [ "$ATIVAS" -le 1 ]; then ok "WIP=$ATIVAS (máximo 1)"
else erro "WIP=$ATIVAS: mais de uma feature ativa ao mesmo tempo"; fi
echo "PYTHON=$PY" > .harness-python

echo
if [ "$ERROS" -gt 0 ]; then echo "$ERROS problema(s). Resolva antes de trabalhar."; exit 1; fi

# marca o inicio da sessao: o handoff usa isto para saber o que mudou
if [ "$SO_CHECAR" != "--check" ]; then
  { echo "HEAD=$(git rev-parse HEAD 2>/dev/null)"; echo "INICIO=$(date '+%d/%m/%Y %H:%M')"; } > .harness-session
  echo "Sessao iniciada. Estado atual:"
  sed -n '/## Em uma frase/,/^## Feito/p' PROGRESS.md | sed '1d;$d' | sed 's/^/  /'
  sed -n '/## Em andamento/,/^## Bloqueado/p' PROGRESS.md | sed '$d' | sed 's/^/  /'
fi
echo "Ambiente pronto. Leia PROGRESS.md e escolha UMA feature."
