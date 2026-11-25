# Bugs reais enfrentados (21/09/2026) e por que o código é assim

Cada item aqui custou uma rodada de teste contra o site real. **Antes de "simplificar"
qualquer trecho citado, leia o item correspondente.** Vários desses bugs voltam sozinhos
se o código for enxugado sem contexto.

| # | Sintoma no log | Causa real | Solução no código |
|---|---|---|---|
| 1 | Digitou usuário e senha, nada aconteceu | A Pinnacle tem DOIS formulários de login; o do menu lateral fica fora da tela e `is_visible()` mente | `_on_screen()`: só elementos dentro do viewport |
| 2 | "botao nao achado, apertei Enter" | Enter não envia o formulário | Clique no botão do pop-up, com reservas |
| 3 | Código do e-mail digitado, login não completa | Tela se reorganiza entre medir e clicar; o clique cai no checkbox | `_click_stable`: espera a posição parar e confere o alvo |
| 4 | "campos de usuario/senha nao encontrados" | Zoom de 67% salvo no perfil do Chrome → página vê 660px → layout de desktop | `reset_saved_zoom()` + `enforce_viewport()` compensando zoom |
| 5 | "lista ao vivo: 0 jogos" com o jogo na tela | O robô lia o CSS da tela de carregamento como se fosse jogo | `_wait_frame_ready()` + filtro de `<style>/<script>` no JS |
| 6 | "lista ao vivo: 5 jogos" (havia 20) | A lista é **virtualizada**: só existe no HTML o que está perto da tela. Rolar até o fim e voltar apaga tudo | `find_and_open()`: rola em passos de 60% lendo a cada passo |
| 7 | Cupom "aberto" mas sem campo de valor | "Boletim De Apostas" também é o nome do item do menu de baixo | Cupom só conta como aberto se aparece "Mais de \<linha\>" |
| 8 | Clique na odd expira 6 s, 3 vezes | O painel do cupom estava aberto cobrindo a tela; o fundo escuro engole o clique | `close_sheet()` antes de clicar + `_covering()` no log |
| 9 | Painel não fechava | O botão muda de classe quando há seleção (`-btn` vs `-btn-hide`) | Seletor por `[class*="footer-page-header-btn"]` |
| 10 | "não consegui ler o placar" e desistiu | A tela do jogo mostra time + 4 colunas (escanteios, amarelos, vermelhos, GOLS), não "A 1-0 B" | `state_from_scoreboard()`: gols = última coluna |
| 11 | Reabria o jogo a cada 30 s | Rolar até a odd esconde o placar do topo → parecia tela congelada | Durante o monitor, placar e odd saem do **cupom** |
| 12 | "seleção com status ODDS_CHANGE" e limpou tudo | `ODDS_CHANGE` é normal ao vivo; só vale parar com CLOSED/SUSPENDED | Regex de status só nos estados que realmente impedem |
| 13 | Clicou SIM, nada por 75 s, aposta não entrou | A casa devolve a aposta quando a odd muda no meio | `_confirm_bet`: detecta devolução e repete até 5x |
| 14 | Campo do valor só-leitura por instantes | Fica bloqueado logo depois da odd mudar | Espera até 4 s o campo liberar |
| 15 | Mercado trancou e o robô desistiu | Indisponibilidade momentânea é normal | Só encerra se a linha sumir por `LINE_GONE_S` |

## Lições que valem para QUALQUER casa nova

1. **Clique não é clique até ser confirmado.** Sempre verifique o efeito.
2. **O que você vê num print pode não existir no HTML** (virtualização) e o que existe
   no HTML pode estar coberto (overlay).
3. **Texto do site gruda**: `textContent` devolve "o 2.51.751". Leia nó de texto por nó.
4. **O mesmo texto aparece em dois lugares** ("o 2.5" no total da partida e no total da
   equipe; "Boletim" no painel e no menu). Ancore pela estrutura, nunca só pelo texto.
5. **Quando falhar, capture**: HTML + PNG + o que cobria o alvo. Adivinhar custa rodadas.
