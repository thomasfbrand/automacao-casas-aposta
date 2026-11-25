# Pinnacle — como o site se comporta (mapeado em 21/09/2026)

## Estrutura

- Tudo que importa está num **iframe de outro domínio**: `sports\d*\.pinnacle\.` —
  exceto `member-auth`. Só dá para ler por dentro do frame (`get_sports_frame`).
- O layout usado é o de **celular** (viewport 440x940). Acima de ~575px o site troca
  para desktop e todo o mapeamento quebra.
- **Placar** (`.score-board`): uma `.score-row` por time, com `.team-name-section` e
  4 `.score-column` = escanteios, amarelos, vermelhos, **gols** (a última).
  Relógio em `.time-live` ("AO VIVO" + "1º Tempo - 12'"); às vezes não aparece.
- **Mercados**: `.section-container` > `.header-name` com o título exato
  `Acima/Abaixo - Partida`. Cuidado: `Total da equipe - Partida` tem "o 2.5" também.
- **Odds**: `button.odd-button`, recriados a cada mudança de odd (classes `odd-up`,
  `odd-down`, `odd-selected`). Qualquer marcação feita neles some.
- **Cupom** (`.slide-container`): sobe de baixo e **cobre a tela inteira**.
  - fechar: `[class*="footer-page-header-btn"]` (muda de nome quando há seleção);
  - seleção: `#bet-slip-single-selections > div`, com `.selection-name` ("Mais de 2.5"),
    `.odd-value`, `.event-name` ("A vs B [1-0]" ← placar vem daqui!) e `button.delete-icon`;
  - valor: `input.stake` (atributos `data-status`, `data-min-stake`, `data-max-stake`);
  - teclado numérico próprio quando o campo é só-leitura;
  - apostar: `button.btn-place-bets`.
- **Pop-ups** (`[class*="ModalOverlay"]`): "Limpar boletim de apostas" (Sim/Cancelar) e
  "Please login first." (sessão caiu). Ficam por cima e engolem cliques.

## Login

Usuário e senha no pop-up do ENTRAR do topo (o formulário do menu lateral está fora da
tela). Dispositivo novo → "Novo dispositivo detectado" com código de 6 dígitos por e-mail,
lido no Gmail por IMAP (`bot/email_code.py`). O e-mail dos últimos 30 min vale.

## Status da seleção (`data-status`)

`OK` e `ODDS_CHANGE` → pode apostar. `CLOSED`, `SUSPENDED`, `UNAVAILABLE` → esperar.

## Valores

Aposta mínima vista: R$ 0,75. Máxima varia por jogo (`data-max-stake`).
