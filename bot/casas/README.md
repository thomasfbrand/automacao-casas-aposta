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

**Molde mais limpo:** `bot/casas/stakecom/` (selectors / js que só lê / parsing em Python puro / driver).
Casa em moeda ≠ R$: declare `moeda` e recuse ligar sem `<CASA>_UNIT_VALUE` etc. (DECISIONS D13).
