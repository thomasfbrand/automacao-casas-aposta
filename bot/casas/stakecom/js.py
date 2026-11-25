"""Trechos de JavaScript que LEEM a página da stake.com e devolvem dados crus (sem decidir nada).

Cada trecho é testado contra HTML real capturado (tests/fixtures/stake/) em tests/test_stakecom_fixtures.py.
A decisão (qual jogo, qual odd, se pode apostar) fica em parsing.py, que é Python puro.
"""

# Cards da lista ao vivo: times, link do jogo, placar, minuto, período.
LIST_CARDS = r"""
() => {
  const txt = e => (e && (e.innerText || e.textContent) || '').trim();
  return [...document.querySelectorAll('[data-testid="fixture-preview"]')].map(c => {
    const teams = [...c.querySelectorAll('[role="group"][aria-label]')].map(g => g.getAttribute('aria-label').trim());
    const hrefs = [...c.querySelectorAll('a[href]')].map(a => a.getAttribute('href'));
    const href = hrefs.find(h => /\/\d+-[^\/]+$/.test(h)) || null;   // jogo, não "/sgm" nem a liga
    const score = [...c.querySelectorAll('[data-testid="score-ticker-item"]')].map(e => txt(e));
    const spans = [...c.querySelectorAll('span')].map(e => txt(e));
    const minute = spans.map(s => s.match(/^(\d{1,3})\s*'$/)).find(Boolean);
    const period = spans.find(s => /half|interval|break|tempo/i.test(s)) || '';
    return {teams, href, score, minute: minute ? +minute[1] : null, period,
            live: /\bLive\b/.test(txt(c)), suspended: /Suspended/.test(txt(c))};
  });
}
"""

# Página do jogo: placar (Sportradar ou nativo), relógio e as linhas do total de gols DA PARTIDA.
READ_GAME = r"""
() => {
  const txt = e => (e && (e.innerText || e.textContent) || '').trim();
  const out = {score: null, source: null, clock: null, period: null, minuteHeader: null,
               market: null, overs: [], teamTotals: 0};
  // 1) placar da Sportradar (é o que aparece depois que a página termina de carregar)
  const sr = [...document.querySelectorAll('.sr-lmt-plus-scb__result-team')].map(e => txt(e));
  if (sr.length === 2 && sr.every(s => /^\d+$/.test(s))) {
    out.score = sr.map(Number); out.source = 'sportradar';
    out.clock = txt(document.querySelector('.sr-lmt-plus-scb__clock')) || null;
    out.period = txt(document.querySelector('.sr-lmt-plus-scb__s-cap')) || null;
  } else {
    // 2) placar nativo: colunas sem rótulo (escanteios, cartões, 1º tempo...) e o TOTAL é o último par
    const sb = document.querySelector('[data-testid="fixture-scoreboard"]');
    const items = sb ? [...sb.querySelectorAll('[data-testid="score-ticker-item"]')].map(e => txt(e)) : [];
    if (items.length >= 2 && items.slice(-2).every(s => /^\d+$/.test(s))) {
      out.score = items.slice(-2).map(Number); out.source = 'nativo';
    }
  }
  const sb = document.querySelector('[data-testid="fixture-scoreboard"]');
  const m = sb && txt(sb).match(/(^|\n)\s*(\d{1,3})\s*'/);
  out.minuteHeader = m ? +m[2] : null;
  // 3) mercado: SÓ o bloco cujo título é exatamente "Asian Total" ou "Total" (nunca "<Time> Total")
  const blocks = [...document.querySelectorAll('.secondary-accordion')];
  const title = b => { const s = b.querySelector('span'); return txt(s); };
  out.teamTotals = blocks.filter(b => /\S+\s+Total$/i.test(title(b)) && !/^(Asian\s+)?Total$/i.test(title(b))).length;
  const blk = blocks.find(b => /^Total$/i.test(title(b))) || blocks.find(b => /^Asian\s+Total$/i.test(title(b)));
  if (blk) {
    out.market = title(blk);
    for (const b of blk.querySelectorAll('[data-testid="fixture-outcome"]')) {
      const lab = (b.getAttribute('aria-label') || '').match(/^\s*Over\s+([\d.]+)\s*$/i);
      if (!lab) continue;
      const oddTxt = txt(b.querySelector('[data-testid="fixture-odds"]'));
      const odd = parseFloat(oddTxt);
      out.overs.push({line: parseFloat(lab[1]), odd: isFinite(odd) ? odd : null,
                      suspended: b.disabled || /suspend|locked/i.test(txt(b)) || /\b(suspended|locked|disabled)\b/.test(b.className || ''),
                      selected: /\bselected\b/.test(b.className || '')});
    }
  }
  return out;
}
"""

# Marca o botão "Over <linha>" do total da PARTIDA para o Python clicar nele com segurança.
TAG_OVER = r"""
(line) => {
  document.querySelectorAll('[data-bot-over]').forEach(e => e.removeAttribute('data-bot-over'));
  const txt = e => (e && (e.innerText || e.textContent) || '').trim();
  const title = b => txt(b.querySelector('span'));
  const blocks = [...document.querySelectorAll('.secondary-accordion')];
  const blk = blocks.find(b => /^Total$/i.test(title(b))) || blocks.find(b => /^Asian\s+Total$/i.test(title(b)));
  if (!blk) return {found: false, why: 'sem mercado de total da partida'};
  const want = 'over ' + String(line);
  const b = [...blk.querySelectorAll('[data-testid="fixture-outcome"]')]
    .find(x => (x.getAttribute('aria-label') || '').trim().toLowerCase() === want);
  if (!b) return {found: false, why: 'linha não oferecida'};
  b.setAttribute('data-bot-over', '1');
  return {found: true, selected: /\bselected\b/.test(b.className || ''), disabled: !!b.disabled};
}
"""

# Cupom: seleções, odd, campo de valor e o botão final.
READ_SLIP = r"""
() => {
  const txt = e => (e && (e.innerText || e.textContent) || '').trim();
  const removes = [...document.querySelectorAll('[data-testid="betslip-bet-remove"]')];
  const sels = removes.map(rm => {
    // sobe até o card da seleção (o que tem a odd dele)
    let c = rm; for (let i = 0; i < 8 && c && !c.querySelector('[data-testid="betslip-odds-payout"]'); i++) c = c.parentElement;
    const ps = c ? [...c.querySelectorAll('p')].map(e => txt(e)).filter(Boolean) : [];
    const ev = c && c.querySelector('a[href]');
    const odd = parseFloat(txt(c && c.querySelector('[data-testid="betslip-odds-payout"]')));
    return {event: txt(ev), href: ev ? ev.getAttribute('href') : null, name: ps[0] || '', market: ps[1] || '',
            odd: isFinite(odd) ? odd : null};
  });
  const input = document.querySelector('input[aria-label="Stake"]');
  // o painel do cupom: menor ancestral do campo de valor que também tem o botão final
  let panel = input; for (let i = 0; i < 25 && panel && !/Total Stake/i.test(txt(panel)); i++) panel = panel.parentElement;
  const buttons = panel ? [...panel.querySelectorAll('button')].map(b => ({text: txt(b), disabled: !!b.disabled}))
                            .filter(b => b.text) : [];
  const total = panel && txt(panel).match(/Total Stake\s*\$?\s*([\d.,]+)/i);
  return {count: sels.length, selections: sels,
          input: input ? {value: input.value, currency: input.getAttribute('data-bet-amount-active-currency') || ''} : null,
          totalStake: total ? total[1] : null, buttons, text: panel ? txt(panel).slice(0, 600) : ''};
}
"""

# Marca o botão final do cupom (texto vem de selectors.PLACE_BUTTON, passado como fonte de regex).
TAG_PLACE = r"""
(src) => {
  document.querySelectorAll('[data-bot-place]').forEach(e => e.removeAttribute('data-bot-place'));
  const re = new RegExp(src, 'i');
  const input = document.querySelector('input[aria-label="Stake"]');
  let panel = input; for (let i = 0; i < 25 && panel && !/Total Stake/i.test(panel.innerText || ''); i++) panel = panel.parentElement;
  const b = panel && [...panel.querySelectorAll('button')].find(x => re.test((x.innerText || '').trim()));
  if (!b) return {found: false};
  b.setAttribute('data-bot-place', '1');
  return {found: true, disabled: !!b.disabled};
}
"""

LOGGED_OUT = r"""() => !!document.querySelector('[data-testid="login-link"]')"""
SESSION_KNOWN = r"""() => !!document.querySelector('[data-testid="login-link"], [data-testid="neo-top-bar"]')"""
