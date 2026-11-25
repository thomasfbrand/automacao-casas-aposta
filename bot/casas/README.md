# Como apoiar uma casa nova

1. Leia `base.py`: é o contrato completo (11 métodos).
2. Crie `bot/casas/<nome>/` com `driver.py` (classe `Casa` + classe `Aba`),
   e, se ajudar, `js.py`, `selectors.py`, `parsing.py` como a Pinnacle faz.
3. Registre em `bot/casas/__init__.py`.
4. Escreva `bot/casas/<nome>/CONSTRAINTS.md` enquanto mapeia o site: cada armadilha
   descoberta vira uma linha lá na hora, não depois.
5. Crie a página simulada em `tests/<nome>_mock.html` imitando a estrutura REAL
   (copie trechos do HTML capturado) e um teste de fluxo completo como
   `tests/test_place_bet_mock.py`.
6. `make check` tem que passar: o teste de contrato cobre automaticamente a casa nova.

**Ordem que funciona** (aprendida na Pinnacle, ver `docs/historico-bugs.md`):
**0. a casa aceita navegador automatizado?** (5 min: Playwright abre um jogo, clica numa odd, o cupom
carrega e não há 403 — a stake.com falhou aqui, ver `stakecom/CONSTRAINTS.md`) → mapear logado com
capturas → escrever o driver → página simulada → teste com `DRY_RUN` no site real → aposta real
mínima. Pular etapa custa mais tempo do que economiza.

**Molde mais limpo:** `bot/casas/stakecom/` (selectors / js que só lê / parsing em Python puro / driver).
Casa em moeda ≠ R$: declare `moeda` e recuse ligar sem `<CASA>_UNIT_VALUE` etc. (DECISIONS D13).
