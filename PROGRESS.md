# PROGRESS — estado atual

> Última atualização: 25/11/2026. **Leia antes de qualquer coisa** e atualize ao sair.

## Em uma frase

O robô funciona ponta a ponta na Pinnacle (3 apostas reais aceitas em 21/09).
O repositório acabou de ganhar git, estrutura multi-casa e harness.

## Feito e verificado

- Fluxo completo na Pinnacle: lê tip → acha jogo → espera a odd → aposta → avisa.
  Evidência: bilhetes #3127382746, #3127385565 (Aldosivi x Tucuman) e #3127405810
  (Redditch x Warwick), todos R$ 1, gravados em `state.sqlite3`.
- Login automático com código do Gmail; disparo automático pelo grupo do Telegram;
  agendamento no Windows (08:00–01:00); navegador sob demanda.
- Harness: git, `bot/casas/` com contrato, AGENTS.md, docs/, features.json, init.sh,
  Makefile, diagnóstico de log, testes de contrato, de capturas reais e E2E.
- Ritual de sessão verificado por programa: `make start` marca o início,
  `make handoff` reprova PROGRESS.md desatualizado/inchado e grava `docs/diario.md`.

## Em andamento (WIP = 1)

Nada ativo. Escolha UMA feature `not_started` em `features.json` antes de começar.

## Bloqueado / esperando o usuário

- **Servidor na nuvem**: decidir entre Oracle grátis (São Paulo) e Hostinger (~R$ 30).
  Precisa de conta e cartão do usuário. Ver `docs/operacao.md`.
- **Stake como segunda casa**: falta o usuário dizer se tem conta e como é o login
  (código por e-mail, SMS ou aplicativo).
- **`UNIT_VALUE` continua 1** (R$ 1 por unidade). Só o usuário decide subir para 350.
- **GitHub**: o repositório é local (2 commits). Falta o usuário criar o repositório
  privado e fazer o primeiro `push` autenticado (ver docs/operacao.md › GitHub).

## Última verificação executada

```
2026-11-25  make check  ->  51 passed, 25 skipped in 6.91s
```

## Próximo passo sugerido

Rodar `make check` no Windows do usuário (lá os 17 testes de navegador rodam de
verdade) e confirmar que o robô ainda liga depois da reorganização de pastas:
`python main.py --test-tip tip.txt` com `DRY_RUN=true`.
