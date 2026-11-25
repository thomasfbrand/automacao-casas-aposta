# Testes

Três níveis, nesta ordem. Mudança que cruza componentes **exige** o terceiro.

| Nível | Onde | O que pega | Roda onde |
|---|---|---|---|
| Unidade | `test_parser.py`, `test_engine.py`, `test_email_code.py` | regras, leitura de texto, decisões do motor | em qualquer lugar, <2 s |
| Regressão de HTML real | `test_fixtures_reais.py` + `tests/fixtures/*.html` | mudança que quebra a leitura do site real já capturado | em qualquer lugar |
| Fluxo completo (E2E) | `test_place_bet_mock.py`, `test_live_list.py` com `tests/*_mock.html` | clique perdido, painel cobrindo, odd mudando, aposta devolvida | precisa do Chromium do Playwright |
| Contrato | `test_contrato_casas.py` | casa que não cumpre `bot/casas/base.py` | em qualquer lugar |
| E2E sem navegador | `test_e2e_tip_ate_aposta.py` | defeito de fronteira entre telegram, motor, casa, avisos e banco | em qualquer lugar |
| Do próprio harness | `test_harness.py` | contexto inchado, WIP>1, segredo versionado, handoff frouxo | em qualquer lugar |

`make test` roda tudo que der. No Linux desta pasta o Chromium não instala (rede
bloqueada), então os testes de navegador são **pulados** — rode-os no Windows.

## Como transformar uma falha real em teste (faça SEMPRE)

1. O robô salva `inspect_out/<nome>.html` no instante do erro.
2. Copie para `tests/fixtures/<assunto>.html` (sem dados pessoais: saldo, usuário).
3. Acrescente um caso em `tests/test_fixtures_reais.py` afirmando o que deveria
   ser lido daquele HTML (odd, placar, status, botão encontrado).
4. Só então corrija o código. O teste tem que falhar antes e passar depois.

## O que NÃO fazer

- Marcar teste como `skip` para a suíte ficar verde.
- Testar só com página simulada quando a mudança foi por causa do site real.
- Rodar aposta real para "ver se funciona" sem `DRY_RUN` antes.
