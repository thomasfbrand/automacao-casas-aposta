# Operação

## Ligar

| Como | Quando usar |
|---|---|
| `iniciar_robo.bat` (2 cliques) | ligar agora, na mão |
| `agendar.bat` (1 vez) | cria a tarefa do Windows: 08:00 todo dia, até 01:00 |
| `python main.py` | igual ao .bat, pelo terminal |
| `python main.py --test-tip tip.txt` | testar UMA tip sem depender do grupo |

Logs do dia: `logs/robo_AAAA-MM-DD.log`. Quedas e reinícios: `logs/reinicios.log`.

## `.env` (o arquivo real nunca vai para o git; o modelo é `.env.example`)

| Variável | Hoje | O que faz |
|---|---|---|
| `CASA` | pinnacle | qual casa usar |
| `DRY_RUN` | false | **true = nunca confirma aposta** |
| `UNIT_VALUE` | 1 | quanto vale 1u em reais |
| `EXTRA_TIP_UNITS` | 0.25 | tip extra do mesmo jogo |
| `MAX_STAKE` / `DAILY_MAX_TOTAL` | 500 / 2000 | tetos de segurança |
| `MIN_ODD` vem da tip | — | o robô nunca aposta abaixo |
| `LINE_GONE_S` | 60 | linha sumida por esse tempo = gol |
| `MONITOR_TIMEOUT_S` | 2700 | teto de monitoramento por tip |
| `GIVE_UP_MINUTE` | 88 | para de apostar depois desse minuto |
| `IDLE_CLOSE_MIN` | 20 | fecha o navegador sem jogo em andamento |
| `FRESH_SESSION` | true | Chrome limpo a cada execução (pede código por e-mail) |
| `HEADLESS` | false | com janela; em servidor use xvfb ou true |
| `TG_*` | — | conta do Telegram e grupo das tips |
| `GMAIL_USER` / `GMAIL_APP_PASSWORD` | — | leitura do código de login (senha de app) |

## Teste manual com um jogo ao vivo

```bash
python -m tools.make_tip "Time A" "Time B" --score 1-0 --min-odd 1.80 -o tip.txt
python main.py --test-tip tip.txt            # com DRY_RUN=true primeiro
```
`--allow-line-mismatch` aceita linha fora da regra (SÓ para teste).

## Se algo falhar

1. `make diagnose LOG=logs/<arquivo>.log` — resume onde parou.
2. Olhe as capturas em `inspect_out/` (HTML + PNG do instante do erro).
3. Se o HTML mostrar estrutura nova do site, atualize
   `bot/casas/pinnacle/CONSTRAINTS.md` e crie um teste em `tests/fixtures/`.

## Servidor na nuvem (pendente)

A casa confere a localização pelo IP: o servidor **precisa estar no Brasil**.
Opções levantadas: Oracle Cloud grátis (região São Paulo, pode faltar vaga),
Hostinger KVM1 (~R$ 30/mês, datacenter em São Paulo), Vultr/Lightsail por hora.
Em servidor sem tela, rode o Chromium do Playwright sob `xvfb-run` e deixe
`CHROME_CHANNEL` vazio.

## stake.com (`CASA=stakecom`) — bloqueada por enquanto

Valores em **US$**: `STAKECOM_UNIT_VALUE`, `STAKECOM_MAX_STAKE`, `STAKECOM_DAILY_MAX_TOTAL` (sem eles
o robô não liga). Login: você entra uma vez na janela do robô (pode ser pelo Google); a sessão fica em
`STAKECOM_PROFILE_DIR` com `STAKECOM_FRESH_SESSION=false`. Hoje a casa responde 403 para o navegador
automatizado e o cupom não carrega: ver `bot/casas/stakecom/CONSTRAINTS.md`.

## GitHub

Repositório: `automacao-casas-aposta`, branch `main` (o antigo `pinnacle-bot/v2` foi copiado sem
alterações em 25/11; o histórico de 5 commits ficou lá). O `.env`, a sessão do Telegram e os perfis do
Chrome (`browser_profile*/`) ficam de fora pelo `.gitignore`; confira com
`git ls-files | findstr .env` (só pode aparecer `.env.example`).
