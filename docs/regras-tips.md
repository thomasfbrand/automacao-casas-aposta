# Regras das tips (ditadas pelo usuário)

Código: `bot/tip_parser.py` (leitura) e `bot/engine.py` (decisão). Testes: `tests/test_parser.py`.

## Formato da mensagem no grupo

```
Live
MÉTODO 2
ENTRADA NO OVER 2.5 GOLS

Liga: BRASIL: BRASILEIRÃO
Jogo: Atlético-MG x Chapecoense
Tempo decorrido: 65
Resultando parcial: 1 X 1

1u @1.80
```

## O que vale

- **Só mensagem que começa com "Live".** Qualquer outra coisa (emoji ✅ 🔄, resumo
  pós-jogo, conversa) é ignorada.
- **Só over.** "Under"/"Abaixo" não é apostado.
- **A linha tem que ser gols do placar + 0,5.** `over 2.5` com `1 X 1` é coerente;
  `over 1.5` com `1 X 1` é tip incoerente e vira aviso, não aposta.
- **A odd da tip é o MÍNIMO, não o alvo.** O robô não aposta na hora: ele seleciona a
  linha e espera a odd subir até esse valor. Pode levar 20 minutos ou nunca acontecer.
- **1u = `UNIT_VALUE` reais.** Cada tip EXTRA do mesmo jogo soma `EXTRA_TIP_UNITS`
  (0,25u). Se chegar antes da aposta, soma no valor; se chegar depois, vira aposta nova.
- **Tip com mais de `MAX_TIP_AGE_S` (10 min) é descartada**, porque o cenário já mudou.

## Cancelamento (três formas, todas valem)

1. Alguém **responde** à tip com "cancelada", "apagada", "não fazer".
2. A mensagem da tip é **editada** para algo com essas palavras.
3. O administrador **apaga** a tip. Conferido a cada ~6 s e de novo no instante da aposta.

Cancelamento sem resposta direta vale para a última tip recebida dentro de `CANCEL_WINDOW_S`.

## Quando o robô desiste de uma tip

| Situação | Comportamento |
|---|---|
| Saiu gol (placar mudou) | encerra, não aposta |
| A linha some da tela por `LINE_GONE_S` (60 s) | encerra: é gol |
| Mercado trancado por instantes | **continua esperando** (normal ao vivo) |
| Não consegue ler o placar | continua; só não aposta se faz >90 s sem confirmar |
| Passou do minuto `GIVE_UP_MINUTE` (88) | encerra |
| Passou de `MONITOR_TIMEOUT_S` monitorando | encerra |
| Aposta aceita | encerra o jogo e avisa no Telegram |
