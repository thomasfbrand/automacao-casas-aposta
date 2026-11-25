"""Contrato que TODA casa de apostas precisa cumprir.

O motor (bot/engine.py) não sabe nada sobre Pinnacle, Stake ou qualquer outra casa:
ele só conhece os dois protocolos abaixo. Para apoiar uma casa nova, crie
`bot/casas/<nome>/driver.py` com uma classe que implemente `Casa` (e a sua `Aba`),
registre em `bot/casas/__init__.py` e pronto — nada no motor muda.

Leia `bot/casas/README.md` antes de escrever uma casa nova.
"""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from ..models import BetResult, GameState


@runtime_checkable
class Aba(Protocol):
    """Uma aba do navegador dedicada a UM jogo."""

    async def open_game(self, home: str, away: str, attempts: int = 3) -> bool:
        """Acha o jogo na lista ao vivo (nomes aproximados) e abre a tela dele.
        Devolve False se não achou depois de `attempts` tentativas."""

    async def watch(self, line: float) -> tuple[GameState, Optional[float]]:
        """Modo monitor: devolve (estado do jogo, odd atual do 'Mais de <line>').

        REGRA DE OURO: este método é chamado a cada 2-4 s e NÃO pode mexer na tela
        (nada de rolar, recarregar ou clicar). A linha deve ficar selecionada no cupom
        e a casa atualiza odd e placar sozinha. odd=None significa "indisponível agora",
        que é normal ao vivo e não é motivo para desistir.
        """

    async def read_state(self) -> GameState:
        """Estado do jogo sem depender do cupom (usado antes de selecionar a linha)."""

    async def read_over_odd(self, line: float) -> Optional[float]:
        """Odd do 'Mais de <line>' na seção de total da PARTIDA (não a de total por equipe).
        None = linha ausente, bloqueada ou suspensa."""

    def line_missing_for(self) -> float:
        """Há quantos segundos a linha não existe nem no cupom nem na tela (0 = existe).
        O motor encerra a tip quando passa de LINE_GONE_S — é o sinal de gol."""

    def stalled_for(self) -> float:
        """Segundos sem NENHUMA mudança (placar, minuto ou odd). Tela congelada."""

    async def place_bet(self, line: float, stake: float, min_odd: float, dry_run: bool) -> BetResult:
        """Aposta `stake` reais no 'Mais de <line>' se a odd final for >= `min_odd`.

        Obrigações:
        - conferir a odd DE NOVO no pop-up de confirmação e abortar se caiu;
        - nunca repetir uma aposta cujo resultado seja desconhecido (status 'unknown');
        - devolver status 'odd_low' SEM limpar o cupom (o motor continua monitorando);
        - com dry_run=True, montar tudo e NÃO confirmar.
        """

    async def recover(self) -> bool:
        """Recarrega e reabre o jogo depois de erro/tela congelada."""

    async def maintain(self) -> None:
        """Manutenção leve entre leituras (fechar pop-ups). Não pode mexer na página."""


@runtime_checkable
class Casa(Protocol):
    """A casa de apostas: dona do navegador e da sessão logada."""

    ui_lock: object        # asyncio.Lock — o cupom é único na conta: uma aposta por vez

    async def ensure_started(self) -> None:
        """Abre o navegador e faz login SE ainda não estiver aberto (chamado na 1ª tip)."""

    async def stop(self) -> None:
        """Fecha o navegador e limpa o perfil temporário."""

    async def close_if_idle(self, idle_s: float) -> bool:
        """Fecha o navegador se não há jogo em andamento há `idle_s` segundos."""

    async def read_balance(self, page=None) -> Optional[float]:
        """Saldo em reais, ou None se não der para ler (não bloqueia a aposta)."""

    def open_tab(self):
        """Context manager assíncrono que entrega uma `Aba` e fecha no fim."""
