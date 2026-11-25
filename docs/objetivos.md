# Objetivos e limites

## O que este projeto é

Um robô que, sem ninguém olhando, transforma uma tip do grupo do Telegram numa
aposta de over gols ao vivo, respeitando a odd mínima da tip.

## Critério de pronto (o projeto inteiro)

1. Liga sozinho, escuta o grupo e não depende de ninguém durante o dia.
2. Cada tip "Live" válida vira aposta na odd certa, ou um aviso explicando por que não virou.
3. Nunca aposta duas vezes a mesma tip, nem abaixo da odd mínima, nem com o placar errado.
4. Avisa no Telegram tudo que fez.

## Fora de escopo (não faça, nem "de brinde")

- **Escolher tips.** O robô obedece ao grupo; não filtra por qualidade, liga ou histórico.
- **Prever resultado, calcular valor esperado, "melhorar" a estratégia.**
- **Gestão de banca esperta** (Kelly, progressão, stop loss dinâmico). Unidade é valor fixo.
- **Cash out, apostas múltiplas, outros mercados** (handicap, escanteios, 1x2).
- **Interface gráfica, painel web, dashboard.** O robô fala por Telegram e por log.
- **Reescrever o que funciona** porque "daria para ficar mais elegante".
- **Burlar proteção de casa de aposta** (captcha, bloqueio de automação, IP). Se a casa
  barrar, isso é informação para o usuário decidir, não um problema para contornar.

## Decisões que são do usuário, nunca suas

Valor da unidade, ligar ou desligar o `DRY_RUN`, apostar de verdade num teste, mudar
tetos de valor, cadastrar conta ou cartão em qualquer serviço, e escolher casa nova.

## Ordem de prioridade quando algo conflita

Não perder dinheiro > não apostar errado > apostar quando devia > ser rápido > ser bonito.
