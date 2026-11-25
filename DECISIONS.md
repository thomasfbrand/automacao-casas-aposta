# Decisões

Formato: **decisão** / por quê / alternativa descartada / o que isso restringe.

## D1 — Playwright controlando o Chrome, não a API da casa
A Pinnacle não oferece API pública para apostar. *Descartado:* chamar os endpoints
internos do site (quebra a cada deploy e é mais fácil de detectar).
*Restringe:* precisa de navegador aberto; tudo depende de HTML que pode mudar.

## D2 — Conta pessoal do Telegram (Telethon), não bot
Bot não lê grupo de terceiro sem ser adicionado por um admin. *Descartado:* bot
oficial. *Restringe:* o arquivo `.session` é a sua conta — nunca versionar.
*Consequência:* avisos vão para Mensagens Salvas e não notificam o celular (ver backlog).

## D3 — A odd da tip é mínimo, e o robô espera
Pedido explícito do usuário em 19/09. Apostar na hora pegaria odd pior.
*Restringe:* uma tip ocupa uma aba por até `MONITOR_TIMEOUT_S`.

## D4 — Monitorar pelo cupom, não pela página
Rolar até a seção de odds esconde o placar e fazia o robô achar que a tela congelou
(bug 11). Com a linha selecionada, a casa atualiza odd e placar dentro do cupom.
*Restringe:* `watch()` nunca pode mexer na tela.

## D5 — Indisponibilidade momentânea não encerra a tip
Pedido do usuário em 21/09: trancar mercado é normal ao vivo. O sinal de gol é a
**linha sumir** por `LINE_GONE_S`. *Descartado:* encerrar ao não ler o placar.

## D6 — Nunca repetir aposta com resultado desconhecido
Se a casa não responde em 75 s, o robô marca `unknown` e para. *Por quê:* repetir
pode apostar duas vezes. *Custo aceito:* uma aposta pode ter entrado sem o robô saber;
ele avisa para conferir em "Minhas Apostas".

## D7 — Navegador sob demanda, não ligado o dia todo
Pedido do usuário em 22/09. Abre na primeira tip e fecha após `IDLE_CLOSE_MIN`.
*Restringe:* a primeira tip do período paga ~40 s de login.

## D8 — `FRESH_SESSION=true` (Chrome limpo a cada execução)
Pedido do usuário: não quer sessão logada persistente. *Custo:* a casa pede o código
por e-mail toda vez, e por isso o Gmail por IMAP é obrigatório.

## D9 — Uma pasta por casa, um motor só (22/09)
Para apoiar Stake e outras sem duplicar o motor. Contrato em `bot/casas/base.py`.
*Descartado:* um script por casa (toda correção teria que ser feita N vezes).

## D10 — Harness no repositório (25/11)
Documentos de contexto, lista de features, verificação executável e handoff limpo,
seguindo "harness engineering". *Por quê:* o conhecimento estava todo no chat; sessão
nova recomeçava do zero e repetia bugs já resolvidos.

## D12 — A Stake se chama `stakecom` no código (25/11)
O teste de contrato reprova o motor que cita nome de casa, e "stake" (valor apostado) já é variável do
motor. *Descartado:* afrouxar o teste. *Bônus:* separa da stake.bet.br, que é outro site.

## D13 — Dinheiro por casa: moeda, valores e teto do dia (25/11)
A stake.com aposta em US$ (cripto). A casa declara `moeda`; `<CASA>_UNIT_VALUE`, `_MAX_STAKE`,
`_DAILY_MAX_TOTAL` têm prioridade no `.env`; o teto do dia soma só a casa atual (coluna `casa` no SQLite).
Casa com moeda ≠ R$ **não liga** sem os valores próprios. *Descartado:* converter R$→US$ por câmbio (outra
fonte de erro, escolha do usuário). *Restringe:* casa nova em outra moeda precisa da mesma recusa.

## D14 — stake.com com perfil persistente, login feito pelo usuário (25/11)
A conta entra pelo Google, que o robô não deve automatizar. Você loga uma vez na janela; a sessão fica no
perfil (`STAKECOM_PROFILE_DIR`, `STAKECOM_FRESH_SESSION=false`) e o robô avisa no Telegram quando cair.
*Descartado:* e-mail+senha no `.env` (mais toques: captcha e código a cada login).

## D15 — Sem técnicas para disfarçar automação na casa nova (25/11)
O driver da stake.com não usa `humanize` nem flags que escondem o Playwright. Quando a stake.com barrou
(403), o trabalho parou e virou decisão do usuário (`docs/objetivos.md`). *Restringe:* F11 bloqueada.

## D11 — Handoff verificado por programa, não por boa vontade (25/11)
A instrução "atualize o PROGRESS.md" sozinha não sobrevive a uma sessão apertada.
`tools/handoff.py` compara o PROGRESS.md com a versão do início da sessão e reprova
se só o bloco gerado mudou. *Restringe:* toda sessão precisa começar com `make start`
(é ele que grava o marcador); sem marcador, a verificação é parcial e avisa.
