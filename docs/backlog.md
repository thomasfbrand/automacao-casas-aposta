# Backlog (ideias que NÃO devem virar trabalho sem o usuário pedir)

Quem enxergar uma melhoria durante uma sessão escreve aqui e segue a tarefa atual.

- Bot do Telegram para notificação chegar no celular (hoje vai para Mensagens Salvas,
  e o Telegram não notifica mensagem de você para você mesmo). Precisa de `TG_BOT_TOKEN`.
- Subir `MONITOR_TIMEOUT_S` de 45 min para 2 h (tip que demora a bater a odd).
- Segunda casa: stake.com está bloqueada (403 para navegador automatizado, ver
  `bot/casas/stakecom/CONSTRAINTS.md`). O driver e os testes servem de base para outra casa.
- **Pinnacle, testes de navegador fora da suíte padrão** (`pytest -m pinnacle`). Em 25/11, com o Chromium
  instalado, 2 falham contra HTML real capturado: `test_le_selecao_odd_e_placar_do_cupom_real` (lê odd 2.02,
  esperado 1.819) e `test_painel_do_cupom_aberto_e_vazio_e_detectado` (painel vazio não detectado).
- Em DRY_RUN a sessão não termina depois do "apostaria" (lote fica ativo até o tempo limite).
- `bet_games` (jogo já apostado) só existe em memória: reiniciar no meio do dia volta a valer 1u.
- Mesma tip em várias casas, escolhendo a melhor odd (aumenta risco de limitação).
- Resumo diário no Telegram (apostas, odd média, valor total).
- `logs/` cresce sem limite: rotação por data.
