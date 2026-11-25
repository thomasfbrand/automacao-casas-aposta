# pinnacle-bot

> **Trabalhando neste repositório (pessoa ou agente)? Comece por [AGENTS.md](AGENTS.md)
> e depois [PROGRESS.md](PROGRESS.md).** Este README descreve o produto; o AGENTS.md
> descreve como trabalhar nele.

Lê as tips do canal do Telegram e aposta o **over de gols ao vivo** na Pinnacle quando a odd chega ao mínimo da tip.
Roda no **seu computador** (usa o seu Telegram e o seu login da Pinnacle; nada disso sai da sua máquina).

## O que ele faz

1. Escuta o canal com a sua conta do Telegram.
2. Só considera mensagens que **começam com "Live"**, são **over** e cuja linha bate com o placar (gols + 0,5). Emojis (✅ 🔄) e edições pós-jogo são ignorados.
3. Abre o jogo na Pinnacle procurando pelo **nome dos times** (comparação aproximada: "Atlético-MG" = "Atlético Mineiro"), sem depender do nome da liga.
4. Fica **lendo a odd** do "Mais de X" sem recarregar a página. Só aposta quando `odd >= odd da tip`.
5. Antes de confirmar confere: a tip ainda existe no grupo, o jogo está ao vivo, o minuto está abaixo do limite, o **placar da tela é o da tip**, limites de valor e saldo, e a **odd final do pop-up de confirmação**.
6. Valor: `1u = UNIT_VALUE`. Se o mesmo jogo apitar em outro método, soma `+0,25u` por tip extra (antes da aposta: junta tudo numa aposta; depois: faz uma aposta adicional de 0,25u).
7. **Cancelamentos:** resposta "cancelada / apagada / não fazer" à tip, mensagem logo após a tip (janela `CANCEL_WINDOW_S`), edição para "cancelada" ou a tip **apagada** do grupo (checada a cada ~6s e de novo no instante da aposta).
8. Te avisa em "Mensagens Salvas" do Telegram de tudo: aposta feita, tip ignorada, jogo não achado, 2FA pedido, erro.

## Casos que travam o avanço (e o que o robô faz)

| Situação | Tratamento |
|---|---|
| Pop-up "mais de 18 anos?" | clica em Sim |
| "Permissão de Localização Negada" | clica em "Continuar usando a localização via endereço IP" |
| Banner de cookies (página e iframe) | Aceitar todos os cookies |
| Aviso "nova versão para celular" | OK |
| Deslogado (odds atrasadas para convidados) | faz login sozinho com o `.env`; nunca lê odd deslogado |
| 2FA / e-mail / verificação facial / senha errada | avisa no Telegram e **espera você resolver** na janela (`MANUAL_INTERVENTION_TIMEOUT_S`) |
| Sportsbook num iframe de outro domínio | entra no iframe automaticamente |
| Seleção "indisponível" / mercado bloqueado | continua monitorando, não aposta |
| "Odds have changed" | reconfere; só segue se a odd final >= mínimo |
| Aposta ao vivo "Waiting → Running" | espera até 75s pelo "Bet Accepted" |
| Sem resposta da casa | marca como **incerta**, avisa e **não repete** (evita aposta em dobro) |
| Tela congelada / sessão caída | recarrega, reloga e reabre o jogo |
| Placar mudou / jogo acabou / minuto limite / tempo limite | encerra sem apostar |
| Tip velha, linha incoerente, pré-jogo | ignora com aviso |

## Instalação (Windows)

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium     # se tiver o Chrome instalado, CHROME_CHANNEL=chrome já basta
copy .env.example .env          # e preencha
```

### Código de login por e-mail (Gmail)
Em dispositivo novo a Pinnacle manda um "Código de Login" de 6 dígitos para o seu e-mail. O robô lê esse e-mail sozinho (só leitura) e digita o código.
1. Google → Conta → Segurança → ative a **Verificação em duas etapas** (se ainda não estiver).
2. Abra https://myaccount.google.com/apppasswords, crie uma senha de app (nome qualquer, ex.: "robo") e copie as 16 letras.
3. No `.env`: `GMAIL_USER=seu@gmail.com` e `GMAIL_APP_PASSWORD=as16letras` (sem aspas; espaços são ignorados).
Sem isso o robô só avisa e espera você digitar o código na janela. Depois de aprovado uma vez, o perfil do navegador (`browser_profile`) mantém o dispositivo aprovado.

### Telegram (assistente que faz tudo)
1. Em https://my.telegram.org → *API development tools* crie o app (nome e nome curto quaisquer) e copie `api_id` e `api_hash`.
2. Rode `python -m tools.setup_telegram`. Ele: cria o `.env`, pede o `api_id`/`api_hash`, faz o login da sua conta
   (o código chega no app do Telegram), procura o grupo **Soltaram Bets / Betador Machine**, confere as últimas mensagens
   (quantas tips ele reconhece), grava `TG_CHANNEL` e manda um teste nas suas Mensagens Salvas.

## Como testar (nesta ordem)

1. `DRY_RUN=true` e `UNIT_VALUE=2` no `.env`.
2. Escolha um jogo que esteja **ao vivo agora** e gere uma tip de teste:
   `python -m tools.make_tip "Mirassol" "Botafogo" --score 2-1 --min-odd 1.80 -o tip.txt`
3. `python main.py --test-tip tip.txt` — o robô abre a Pinnacle, faz login, acha o jogo, lê a odd, monta o cupom, digita o valor e **limpa sem confirmar** (avisa "DRY_RUN: apostaria…").
4. Repita com `DRY_RUN=false` e `UNIT_VALUE=2` para uma aposta real de R$ 2 (com o `--min-odd` baixo o suficiente para a odd atual).
5. `python main.py` para escutar o Telegram de verdade. Só depois suba `UNIT_VALUE` para 350.

## Se algo falhar

`python -m tools.inspect_frame "Time A" "Time B"` salva `inspect_out/frame.html`, `frame.txt` e `tela.png` do que o robô está vendo.
Os textos/seletores da Pinnacle ficam em `bot/pinnacle/selectors.py` e `bot/pinnacle/js.py` — ajustando ali, o resto continua igual.

## Limites honestos

- Os seletores foram mapeados pelo **texto visível** do site em 17–19/09/2026 (o iframe é de outro domínio, então não deu para ler o HTML). A lógica foi testada com páginas simuladas e testes unitários (`pytest`), mas o **primeiro contato com o site real** (principalmente digitar o valor e limpar o cupom) pode exigir um ajuste em `selectors.py`. Por isso o modo `DRY_RUN` vem ligado.
- Automatizar apostas pode violar os termos da casa; há risco de limitação ou bloqueio da conta.
- Nada aqui é recomendação financeira.

## Segurança

- `.env` e `browser_profile/` e `*.session` contêm credenciais/sessões: **não compartilhe**.
- Tetos: `MAX_STAKE` (por aposta) e `DAILY_MAX_TOTAL` (por dia). Saldo é conferido antes de cada aposta real.
- Para pausar: feche a janela/terminal. Tips já confirmadas continuam válidas na casa.
