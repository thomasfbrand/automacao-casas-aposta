#!/usr/bin/env bash
# Checklist de estado limpo (lecture 12): roda no make check / make handoff.
set -uo pipefail
cd "$(dirname "$0")/.."
ERROS=0
ok(){ printf '  [ok]   %s\n' "$1"; }
erro(){ printf '  [ERRO] %s\n' "$1"; ERROS=$((ERROS+1)); }

LIXO=$(grep -rn "print(\"DEBUG\|print('DEBUG\|breakpoint()\|pdb.set_trace\|XXX TEMP" \
  --include=*.py bot tools main.py 2>/dev/null | head -5)
[ -z "$LIXO" ] && ok "sem código de depuração solto" || { erro "código de depuração:"; echo "$LIXO"; }

SEGREDO=$(git ls-files | grep -E "^\.env$|\.session$|browser_profile[^/]*/" | head -3)
[ -z "$SEGREDO" ] && ok "nenhum segredo versionado" || { erro "segredo no git: $SEGREDO"; }

SUJO=$(git status --porcelain | head -5)
[ -z "$SUJO" ] && ok "tudo commitado" || { printf '  [!]    arquivos não commitados:\n'; echo "$SUJO" | sed 's/^/           /'; }

grep -q "$(date +%Y)" PROGRESS.md && ok "PROGRESS.md atualizado neste ano" \
  || erro "PROGRESS.md parece velho"

exit $ERROS
