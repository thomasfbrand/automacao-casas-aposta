"""Textos, URLs e seletores da Pinnacle num lugar só.

Tudo foi mapeado olhando o site (17-19/09/2026). Se a Pinnacle mudar algo,
ajuste AQUI (use tools/inspect_frame.py para ver o HTML atual).
"""
import re

HOME_URL = "https://pinnacle.bet.br/"
SPORTSBOOK_URL = "https://pinnacle.bet.br/sportsbook/standard/soccer"

# iframe onde ficam odds, jogos, busca e cupom (domínio diferente da página de fora)
SPORTS_FRAME_URL_RE = re.compile(r"sports\d*\.pinnacle\.", re.I)

# --- Pop-ups que aparecem em ordem variável (página de fora e dentro do iframe) ---
# (regex do texto que identifica o pop-up, regex do botão a clicar)
OVERLAYS = [
    ("idade", re.compile(r"mais de 18 anos", re.I), re.compile(r"^\s*sim\s*$", re.I)),
    ("localizacao", re.compile(r"Permiss[aã]o de Localiza[cç][aã]o", re.I),
     re.compile(r"continuar usando a localiza[cç][aã]o via endere[cç]o ip", re.I)),
    ("cookies", re.compile(r"Usamos cookies", re.I), re.compile(r"aceitar todos os cookies", re.I)),
    ("app", re.compile(r"nova vers[aã]o para celular", re.I), re.compile(r"^\s*ok\s*$", re.I)),
    # aparece ao clicar numa odd DESLOGADO: sinal de que a sessão caiu
    ("login_primeiro", re.compile(r"Please login first|Fa[cç]a (o )?login primeiro", re.I), re.compile(r"^\s*ok\s*$", re.I)),
]

# --- Login (na página de fora) ---
LOGIN_USER_PLACEHOLDER = re.compile(r"Usu[aá]rio", re.I)
LOGIN_PASS_PLACEHOLDER = re.compile(r"Senha", re.I)
LOGGED_IN_JS = r"() => /(^|\n)\s*SAIR\s*(\n|$)/i.test(document.body.innerText || '')"
# a página já carregou a ponto de saber se há login? (tem o botão ENTRAR ou o menu de conta)
AUTH_KNOWN_JS = r"() => /(^|\n)\s*(ENTRAR|CADASTRO|SAIR)\s*(\n|$)/i.test(document.body.innerText || '')"
BALANCE_JS = r"""
() => {
  const m = (document.body.innerText || '').match(/R\$\s*([\d.]+,\d{2}|[\d,]+\.\d{2})/);
  return m ? m[1] : null;
}
"""
GUEST_DELAY_TEXT = re.compile(r"atraso nas probabilidades", re.I)

# --- Cupom ---
SLIP_TITLE = re.compile(r"Boletim De Apostas", re.I)
STAKE_INPUT_CANDIDATES = [
    'input[placeholder*="Aposta" i]',
    'input[aria-label*="Aposta" i]',
    'input[placeholder*="Stake" i]',
    'input[inputmode="decimal"]',
    'input[type="number"]',
    'input[type="text"]',
]
SLIP_REMOVE_CANDIDATES = [
    '[aria-label*="remov" i]',
    '[aria-label*="delet" i]',
    '[aria-label*="fechar" i]',
    '[aria-label*="close" i]',
    '[class*="remove" i]',
    '[class*="delete" i]',
    '[data-testid*="remove" i]',
    '[data-testid*="delete" i]',
]
PLACE_BUTTON = re.compile(r"FAZER\s+(\d+)\s+APOSTAS?", re.I)
CONFIRM_TEXT = re.compile(r"arriscar\s+([\d.,]+)\s*BRL\s+para\s+ganhar\s+([\d.,]+)", re.I)
CONFIRM_YES = re.compile(r"^\s*SIM\s*$", re.I)
CONFIRM_NO = re.compile(r"^\s*CANCELAR\s*$", re.I)
TOTAL_STAKE_RE = re.compile(r"Total Stake\s*([\d.,]+)\s*BRL", re.I)

ACCEPTED_RE = re.compile(r"Bet Accepted\s*#?\s*(\d+)|Aposta\s+(aceita|realizada)", re.I)
WAITING_RE = re.compile(r"Please wait while your bet is being processed|Aguarde", re.I)
REJECTED_RE = re.compile(r"(bet|aposta)\s+(was\s+)?(rejected|rejeitada|recusada|declined)|n[aã]o foi (aceita|poss[ií]vel)|"
                         r"could not be placed|suspens", re.I)
UNAVAILABLE_RE = re.compile(r"indispon[ií]vel|unavailable", re.I)
ODDS_CHANGED_RE = re.compile(r"Odds have changed from\s*(\d+\.\d+)\s*to\s*(\d+\.\d+)", re.I)

# Abas do sportsbook (parte de baixo e de cima)
LIVE_TAB = re.compile(r"^\s*AO VIVO\s*$", re.I)

LOGIN_FIRST_RE = re.compile(r"Please login first|Fa[cç]a (o )?login primeiro", re.I)
