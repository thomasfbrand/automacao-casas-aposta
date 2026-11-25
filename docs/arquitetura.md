# Arquitetura

```
Telegram (sua conta)                    Casa de apostas (navegador)
      │                                           ▲
      ▼                                           │
telegram_client.py ──► engine.py ──► bot/casas/<casa>/driver.py
                          │                (implementa bot/casas/base.py)
                          ├──► tip_parser.py   (texto da tip -> Tip)
                          ├──► matching.py     ("Redditch" == "Redditch United"?)
                          ├──► rules.py        (unidades -> reais, tetos)
                          ├──► state.py        (SQLite: msgs vistas, apostas)
                          └──► notifier.py     (avisos no Telegram)
```

**A regra que sustenta tudo:** o motor não sabe o nome de nenhuma casa. Ele conversa
por 11 métodos descritos em `bot/casas/base.py`. Casa nova = pasta nova, zero mudança
no motor. Quem quebrar isso (colocar `if casa == "pinnacle"` no motor) quebra o projeto.

## Fluxo de uma tip, do começo ao fim

1. `telegram_client` recebe a mensagem e chama `engine.on_message`.
2. `tip_parser` valida (Live? over? linha = gols+0,5?). Inválida vira aviso.
3. O motor cria uma `Session` com um `Lot` (unidades + odd mínima) e abre uma aba.
4. `open_game` acha o jogo pelo nome dos times, rolando a lista ao vivo em passos.
5. A linha é selecionada no cupom **uma vez**; daí em diante só `watch()` a cada 2-4 s.
6. Quando `odd >= odd mínima`, `place_bet`: valor, confirmar, conferir a odd do pop-up, SIM.
7. Aceita → grava no SQLite, avisa no Telegram, encerra o jogo.

## Decisões estruturais que não devem ser desfeitas

- **O navegador só abre quando chega tip** (`ensure_started`), e fecha após
  `IDLE_CLOSE_MIN` sem jogo. Robô ligado o dia todo não significa navegador aberto.
- **Uma aba por jogo, mas um cupom só por conta**: `driver.ui_lock` serializa apostas.
- **O estado do jogo vem do cupom durante o monitor**, não da página: ler a página
  exigiria rolar, e rolar quebra o monitor (ver `docs/historico-bugs.md`).
- **Toda ação crítica é verificada depois**: clicou na odd? confere se entrou no cupom.
  Digitou o valor? confere o "Total Stake". Confirmou? espera "Bet Accepted".
