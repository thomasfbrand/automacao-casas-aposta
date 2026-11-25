# stake.com — como o site se comporta (mapeado em 25/11/2026)

## BLOQUEIO: a casa barra o navegador automatizado (25/11/2026)

Com o Playwright controlando o navegador (Chromium headless **e** Chrome instalado com janela), a API do
site `POST /_api/v1/graphql` responde **403**. A página em si carrega (o HTML vem pronto do servidor), mas
tudo que depende da API não funciona: o card da seleção no cupom fica eterno em carregamento
(`aria-busy="true"`, só esqueletos `bet-summary-*-skeleton`), o widget da Sportradar não carrega, e a
aposta não teria como ser enviada. No navegador do app (sem Playwright) o mesmo cupom carrega normal:
o bloqueio é contra a automação, não contra a conexão nem contra estar deslogado.

**Não contornar** (disfarçar o navegador, falsificar impressão digital, chamar a API por fora): ver
`docs/objetivos.md` › fora de escopo. É decisão do usuário. Diagnóstico reproduzível: abrir um jogo,
clicar numa odd e listar respostas >= 400 (o robô vê `aria-busy` no card do cupom).

## Estrutura (sem iframe, tudo com data-testid)

- **Lista ao vivo** `/sports/live/soccer`: um `[data-testid="fixture-preview"]` por jogo.
  - times: `[role="group"][aria-label="<time>"]` (o `competitor-item` vem VAZIO);
  - link do jogo: `a[href]` terminando em `/<id>-<times>`; ignore o que termina em `/sgm` e o link da liga;
  - o HTML do servidor às vezes traz prefixo de idioma (`/pl/sports/...`): use só o caminho `/sports/...`;
  - placar: dois `[data-testid="score-ticker-item"]`; minuto em `<span>45<span>'</span></span>`.
- **Página do jogo** `/sports/soccer/<país>/<liga>/<id>-<times>`: os mercados já vêm no HTML do servidor.
  - placar: o nativo (`fixture-scoreboard`, várias colunas sem rótulo — escanteios, cartões, 1º tempo — e
    o **total de gols é o último par**) é trocado, depois que a página carrega, pelo widget da Sportradar:
    `.sr-lmt-plus-scb__result-team.srm-team1/2`, relógio `.sr-lmt-plus-scb__clock` ("83:39" = tempo TOTAL,
    também no 2º tempo) e período `.sr-lmt-plus-scb__s-cap` ("1st"/"2nd"). Ler os dois, nessa ordem.
  - mercados: blocos `.secondary-accordion`, título no primeiro `<span>`.
  - **o mercado da tip é o "Asian Total"** (não há "Total" comum ao vivo). Em linha .5 é igual ao over comum.
  - odd: `button[data-testid="fixture-outcome"][aria-label="Over 2.5"]` > `[data-testid="fixture-odds"]`.
    Selecionado = classe `selected`. Suspenso = `disabled` / texto "Suspended".
  - **ARMADILHA:** "`<Time>` Total" (total da equipe) tem botões `aria-label="Over 1.5"` iguais. Ancore no
    título exato `Asian Total`/`Total`.
- **Cupom** (barra lateral, layout desktop 1280px): seleção com `[data-testid="betslip-bet-remove"]`, nome em
  `<p>` ("Over 2.5"), mercado em `<p>` ("Asian Total"), odd em `[data-testid="betslip-odds-payout"]`;
  valor em `input[aria-label="Stake"]` (`data-bet-amount-active-currency="usdt"`); "Total Stake".
  Deslogado o botão final é **"Register to Bet"**.

## A linha da tip nem sempre existe

A casa mostra ~3 linhas asiáticas em volta da linha principal (ex.: 2.25 / 2.5 / 2.75). A linha gols+0,5
da tip apareceu em 5 de 12 jogos ao vivo no 1º tempo; no fim de jogo ela costuma ser a principal.
Por isso `line_missing_for()` só conta **depois** de a linha ter aparecido: "ainda não oferecida" não é gol.

## Dinheiro

Valores em **US$** (cripto/USDT). O driver se recusa a ligar sem `STAKECOM_UNIT_VALUE`,
`STAKECOM_MAX_STAKE` e `STAKECOM_DAILY_MAX_TOTAL` no `.env` (o `UNIT_VALUE` em reais nunca vale aqui).

## Não mapeado (precisa estar logado — e hoje está bloqueado, ver acima)

Texto do botão de apostar ("Place Bet"?), recibo/ID da aposta, aviso de odd mudada, saldo, e o ajuste
"aceitar mudança de odd" da conta (precisa ser "não aceitar" ou "só maiores": nunca apostar abaixo do mínimo).
`selectors.py` tem regex largas para isso e o resultado não reconhecido vira `unknown` (não repete).
