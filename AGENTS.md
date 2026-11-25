# AGENTS.md — leia isto primeiro

Robô que lê tips de over gols num grupo do Telegram e aposta sozinho numa casa de
apostas, esperando a odd chegar ao mínimo da tip. Python 3.10+, Playwright, Telethon.
**Ele aposta dinheiro real.** Erro aqui custa dinheiro, não só tempo.
Casas (`CASA=` no `.env`): `pinnacle` (funcionou; site fora do ar em 25/11) e `stakecom`.

## Comandos

```bash
make start                # ABRE a sessão: ambiente + estado atual + features em aberto
make handoff              # FECHA a sessão: verifica tudo e grava o diário (reprova se faltar algo)
make check                # verificação completa: contrato + testes + estado limpo
make test                 # só os testes (pytest) — sem os de navegador da Pinnacle
pytest -m pinnacle        # testes de navegador da Pinnacle (fora do padrão por ora; 2 falham, ver backlog)
make diagnose LOG=logs/robo-2026-09-21.log   # resume um log de execução
make tip CASA_A="Time A" CASA_B="Time B" PLACAR=1-0 ODD=1.80   # gera tip de teste
python main.py --test-tip tip.txt            # roda UMA tip (respeita DRY_RUN)
python main.py                               # modo automático: escuta o Telegram
```

## Regras rígidas (não negocie com elas)

1. **WIP = 1.** Uma única feature `active` em `features.json`. Só ative a próxima
   quando a atual estiver `passing` com o comando de verificação dela executado.
2. **Não declare pronto sem rodar.** "O código parece certo" não é evidência.
   Evidência é a saída do comando de verificação colada no PROGRESS.md.
3. **Não mexa no que não foi pedido.** Nada de refatorar de passagem. Melhoria que
   você enxergou vira linha em `docs/backlog.md`, não commit.
4. **Dinheiro:** só altere `DRY_RUN`, `UNIT_VALUE`, `MAX_STAKE` ou `DAILY_MAX_TOTAL`
   se o usuário pedir, nesta sessão, com o valor explícito.
5. **Segredos:** `.env`, `*.session` e `browser_profile/` nunca entram no git nem
   aparecem em log, print ou resposta.
6. **Um teste que falha é informação, não obstáculo.** Nunca "conserte" apagando,
   pulando (`skip`) ou afrouxando a asserção sem o usuário mandar.
7. **Toda sessão termina limpa:** veja "Handoff" abaixo.

## Onde está o quê

| Preciso de… | Arquivo |
|---|---|
| O que o robô deve e **não** deve fazer | `docs/objetivos.md` |
| Regras das tips (formato, unidades, cancelamento) | `docs/regras-tips.md` |
| Como motor e casa se encaixam | `docs/arquitetura.md` + `bot/casas/base.py` |
| Armadilhas do site da Pinnacle | `bot/casas/pinnacle/CONSTRAINTS.md` |
| Bugs reais já enfrentados e por que o código é assim | `docs/historico-bugs.md` |
| Como rodar, variáveis do `.env`, agendamento | `docs/operacao.md` |
| Níveis de teste e como criar um novo | `docs/testes.md` |
| Decisões tomadas e alternativas descartadas | `DECISIONS.md` |
| Estado atual, o que fazer agora | `PROGRESS.md` ← **leia sempre** |
| Lista de features e seu estado | `features.json` |

## Ritual da sessão

**Ao abrir:** `make start`. Ele mostra o estado e marca o commit de partida.
**Ao fechar:** `make handoff`. Ele REPROVA se os testes falham, se há mais de uma
feature ativa, se o `PROGRESS.md` passou de 120 linhas ou se você fez commits sem
atualizar à mão o `PROGRESS.md` (o bloco automático não conta). Depois de passar,
ele grava a sessão em `docs/diario.md` e sobra só o `git commit`.

O `PROGRESS.md` é curto de propósito: é o que a próxima sessão lê. Histórico longo
vai para `docs/diario.md`. Se a janela de contexto chegar a ~60%, pare a feature onde
está, rode o handoff e avise o usuário.

## Fatos que economizam seu tempo

- A **Pinnacle roda num iframe** de outro domínio (`sports*.pinnacle.bet.br`): o HTML
  só é alcançável por dentro do frame, e todo clique importante precisa ser conferido
  depois (a tela se redesenha a cada mudança de odd).
- **Nada de testar contra o site real sem necessidade.** Existem páginas que imitam a
  Pinnacle em `tests/` e capturas de HTML real em `tests/fixtures/`. Teste primeiro ali.
- No Windows do usuário o `.venv` deste repo tem o Chromium do Playwright: os testes de navegador
  RODAM (não pulam). Não há `make` nem bash no PATH do PowerShell: use `.venv\Scripts\python -m pytest`
  ou o Git Bash. Teste pulado por "sem Chromium" ali é defeito de ambiente, não "esperado".
- **Dinheiro por casa:** cada casa declara `moeda`; `<CASA>_UNIT_VALUE/_MAX_STAKE/_DAILY_MAX_TOTAL`
  valem sobre os gerais; casa em US$ não liga sem eles (DECISIONS D13).
- O usuário fala português. Mensagens do robô, logs e documentos em português.
