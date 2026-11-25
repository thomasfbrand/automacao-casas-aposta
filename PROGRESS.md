# PROGRESS — estado atual

> Última atualização: 25/11/2026. **Leia antes de qualquer coisa** e atualize ao sair.

## Em uma frase

O motor é multi-casa de verdade (moeda, valores e teto por casa). O driver da stake.com está pronto e
testado, mas **a stake.com barra o navegador automatizado** (403 na API): apostar lá está bloqueado.

## Feito e verificado

- Pinnacle: fluxo completo funcionou (3 apostas reais aceitas em 21/09, bilhetes em `state.sqlite3`).
  Site fora do ar em 25/11; testes de navegador dela fora da suíte padrão (`pytest -m pinnacle`).
- Repositório migrado para `automacao-casas-aposta` (GitHub, branch `main`), com `.venv` próprio e
  Chromium do Playwright instalado no Windows: os testes de navegador rodam de verdade.
- stake.com (`CASA=stakecom`, F11): mapeada deslogada com capturas reais em `tests/fixtures/stake/`;
  driver em `bot/casas/stakecom/` (lista ao vivo, abrir jogo pelo nome, placar Sportradar/nativo,
  "Asian Total" sem cair no total da equipe, cupom, DRY_RUN, aposta real com recusa/odd mudada/silêncio).
  Contra o site real em DRY_RUN: achou o jogo, leu placar/minuto/linhas/odd e pôs a seleção no cupom;
  parou porque o cupom não carrega (API 403).
- Motor: `moeda` vem da casa; `<CASA>_UNIT_VALUE/_MAX_STAKE/_DAILY_MAX_TOTAL/_PROFILE_DIR/_FRESH_SESSION`
  no `.env`; teto do dia por casa (coluna `casa` no SQLite, banco antigo migra sozinho).

## Em andamento (WIP = 1)

Nada ativo. F11 está `blocked` (ver abaixo).

## Bloqueado / esperando o usuário

- **stake.com barra automação** (D15): decidir entre (a) outra casa, (b) stake.bet.br (outro site, outra
  proteção — testar igual antes de investir), (c) robô só AVISA no Telegram quando a odd chega e você
  aposta à mão. Contornar a proteção está fora de escopo.
- Não mapeado na stake.com (precisa de login e de a API responder): botão de apostar, recibo, saldo,
  ajuste "aceitar mudança de odd".
- **Grupo do Telegram** das tips ainda não definido (`TG_CHANNEL`).
- Servidor na nuvem (F10) e `UNIT_VALUE` continuam como antes: decisão do usuário.

## Última verificação executada

```
2026-11-25  make check  ->  79 passed, 28 deselected in 50.31s
```

## Próximo passo sugerido

O usuário escolhe o caminho do bloqueio da stake.com. Se for outra casa: copiar o molde de
`bot/casas/stakecom/` (é o mais limpo) e, antes de escrever driver, repetir o teste de 403 em 5 min.
