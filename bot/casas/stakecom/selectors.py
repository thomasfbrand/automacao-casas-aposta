"""URLs, textos e seletores da stake.com num lugar só.

Mapeado em 25/11/2026 olhando o site DESLOGADO (lista ao vivo, página do jogo, cupom).
O que depende de estar logado (botão de apostar, recibo, saldo, ajuste de mudança de odd)
está marcado como NÃO MAPEADO: confira com capturas reais antes da primeira aposta de verdade.
Armadilhas e o porquê de cada escolha: CONSTRAINTS.md.
"""
import re

HOME_URL = "https://stake.com/sports/home"
LIVE_SOCCER_URL = "https://stake.com/sports/live/soccer"

# o layout mapeado é o de desktop (cupom na barra lateral direita)
VIEWPORT = {"width": 1280, "height": 900}

# --- sessão ---
LOGIN_LINK = '[data-testid="login-link"]'        # só existe DESLOGADO
REGISTER_LINK = '[data-testid="register-link"]'
COOKIE_ACCEPT = '[data-testid="accept-cookie-consent"]'

# --- lista ao vivo ---
CARD = '[data-testid="fixture-preview"]'

# --- página do jogo ---
OUTCOME = '[data-testid="fixture-outcome"]'
MARKET_BLOCK = ".secondary-accordion"
# mercado da tip: total de gols DA PARTIDA. Na stake.com ao vivo ele se chama "Asian Total"; em linha .5 é
# idêntico ao over comum (não existe devolução). "Total" puro é aceito se um dia aparecer.
# NUNCA aceitar "<Time> Total" (total da equipe): tem os mesmos botões "Over 1.5".
MATCH_TOTAL_TITLE = re.compile(r"^\s*(Asian\s+)?Total\s*$", re.I)

# --- cupom (betslip) ---
SLIP_REMOVE = '[data-testid="betslip-bet-remove"]'
SLIP_ODD = '[data-testid="betslip-odds-payout"]'
SLIP_COUNT = '[data-testid="bet-slip-count-badge"]'
STAKE_INPUT = 'input[aria-label="Stake"]'
# NÃO MAPEADO (logado): texto do botão final. Deslogado ele diz "Register to Bet".
PLACE_BUTTON = re.compile(r"^\s*(Place\s+Bet|Fazer\s+aposta|Apostar)\s*$", re.I)
REGISTER_BUTTON = re.compile(r"Register to Bet", re.I)

# NÃO MAPEADO (logado): mensagens depois de clicar em apostar. Regex largas de propósito; a decisão é conservadora
# (o que não for reconhecido vira "unknown" e o robô NÃO repete a aposta).
ACCEPTED_RE = re.compile(r"Bet\s+(was\s+)?(placed|accepted)|Aposta\s+(feita|realizada|aceita)", re.I)
ODDS_CHANGED_RE = re.compile(r"odds?\s+(have\s+)?changed|odds?\s+mud", re.I)
REJECTED_RE = re.compile(r"insufficient|saldo insuficiente|not\s+available|rejected|recusad|error|limit", re.I)
