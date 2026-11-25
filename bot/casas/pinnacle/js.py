"""Trechos JavaScript executados DENTRO do iframe do sportsbook.

Nada aqui depende de classes CSS da Pinnacle (elas mudam): tudo é achado pelo
TEXTO visível, que é o que vimos no mapeamento manual.
"""

# Marca o botão "+N >" (abre todos os mercados) de cada jogo ao vivo e devolve o texto de cada card.
TAG_GAMES = r"""
() => {
  const TXT_FILTER = { acceptNode: n => /^(SCRIPT|STYLE|NOSCRIPT)$/.test((n.parentElement || {}).tagName || '') ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT };
  document.querySelectorAll('[data-bot-plus]').forEach(e => e.removeAttribute('data-bot-plus'));
  const all = [...document.querySelectorAll('body *')];
  const leafText = el => {
    const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, TXT_FILTER);
    const parts = []; let n;
    while ((n = w.nextNode())) { const t = n.nodeValue.replace(/\s+/g, ' ').trim(); if (t) parts.push(t); }
    return parts.join(' ');
  };
  const shortEls = (all, max) => all.filter(e => (e.textContent || '').length <= max);
  const plusRe = /^\+\s*\d+\s*[>›»]?$/;
  const linesOf = el => {
    const out = []; const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, TXT_FILTER); let n;
    while ((n = w.nextNode())) { const t = n.nodeValue.replace(/\s+/g, ' ').trim(); if (t) out.push(t); }
    return out;
  };
  // um card de jogo tem o relógio ("2H 50'", "Intervalo") e/ou o cabeçalho "Partida 1X2"
  const headRe = /(\b\d[Hh]\s*\d{1,3}(\+\d+)?\s*['’′`´]|\bIntervalo\b|Partida\s*(1X2|Vencedor))/i;
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const candidates = shortEls(all, 14).filter(e => plusRe.test(leafText(e)) && vis(e));
  const cardOf = pe => {
    let c = pe;
    while (c.parentElement && c.parentElement !== document.body && !headRe.test(linesOf(c).join(' '))) c = c.parentElement;
    return headRe.test(linesOf(c).join(' ')) ? c : null;
  };
  // um "+N >" por card (o do rodapé: o último na ordem do documento; "+1" de handicap não vale)
  const byCard = new Map();
  for (const pe of candidates) {
    const c = cardOf(pe);
    if (c) byCard.set(c, pe);
  }
  return [...byCard.entries()].map(([card, pe], i) => {
    pe.setAttribute('data-bot-plus', String(i));
    return { i, lines: linesOf(card) };
  });
}
"""

# Rola tudo até o fim para carregar todos os jogos e volta ao topo.
SCROLL_ALL = r"""
(toTop) => {
  const els = [document.scrollingElement,
    ...[...document.querySelectorAll('*')].filter(e => {
      const s = getComputedStyle(e);
      return /(auto|scroll)/.test(s.overflowY) && e.scrollHeight > e.clientHeight + 20;
    })];
  els.forEach(e => { if (e) e.scrollTop = toTop ? 0 : e.scrollHeight; });
  return els.length;
}
"""

_SECTION_HELPERS = r"""
const TXT_FILTER = { acceptNode: n => /^(SCRIPT|STYLE|NOSCRIPT)$/.test((n.parentElement || {}).tagName || '') ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT };
const norm = s => (s || '').replace(/\s+/g, ' ').trim();
const all = [...document.querySelectorAll('body *')];
const leafText = el => {
  const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, TXT_FILTER);
  const parts = []; let n;
  while ((n = w.nextNode())) { const t = n.nodeValue.replace(/\s+/g, ' ').trim(); if (t) parts.push(t); }
  return parts.join(' ');
};
const shortEls = (all, max) => all.filter(e => (e.textContent || '').length <= max);

const hdrRe = /^[^\n]{3,60}\s-\s(Partida|1[ºo°]\s*Tempo|2[ºo°]\s*Tempo)[^\n]{0,30}$/i;
const isHdr = e => { const t = (e.innerText || '').trim(); return t.length < 70 && !t.includes('\n') && hdrRe.test(t); };
const hdrs = all.filter(e => isHdr(e) && ![...e.children].some(isHdr));
const precedingHeader = r => {
  let h = null;
  for (const x of hdrs) { if (x.compareDocumentPosition(r) & 4) h = x; else break; }
  return h;
};
const isOuPartida = h => h && /^Acima\/Abaixo/i.test(h.innerText.trim()) && /-\s*Partida/i.test(h.innerText);
"""

# Lê a odd do "Mais de <linha>" no bloco "Acima/Abaixo - Partida" e marca o elemento para clicar.
READ_OVER = "(line) => {" + _SECTION_HELPERS + r"""
  document.querySelectorAll('[data-bot-over]').forEach(e => e.removeAttribute('data-bot-over'));
  const rowRe = new RegExp('^o\\s*' + String(line).replace('.', '\\.') + '\\s+(\\d+\\.\\d{2,3})$', 'i');
  const rows = shortEls(all, 24).filter(e => rowRe.test(leafText(e)));
  const deepest = rows.filter(e => ![...e.querySelectorAll('*')].some(c => rows.includes(c)));
  let sectionFound = hdrs.some(isOuPartida);
  for (const r of deepest) {
    if (isOuPartida(precedingHeader(r))) {
      r.setAttribute('data-bot-over', '1');
      return { found: true, odd: parseFloat(rowRe.exec(leafText(r))[1]), sectionFound };
    }
  }
  return { found: false, odd: null, sectionFound };
}
"""

# Marca o "Ver Tudo" do bloco "Acima/Abaixo - Partida" (para mostrar todas as linhas).
TAG_VER_TUDO = "() => {" + _SECTION_HELPERS + r"""
  document.querySelectorAll('[data-bot-vertudo]').forEach(e => e.removeAttribute('data-bot-vertudo'));
  const h = hdrs.find(isOuPartida);
  if (!h) return { found: false, section: false };
  const idx = hdrs.indexOf(h);
  const next = hdrs[idx + 1] || null;
  const cands = all.filter(e => /^ver (tudo|menos)$/i.test(norm(e.innerText)) && e.children.length <= 2
    && (h.compareDocumentPosition(e) & 4) && (!next || (next.compareDocumentPosition(e) & 2)));
  if (!cands.length) return { found: false, section: true };
  const c = cands[0];
  c.setAttribute('data-bot-vertudo', '1');
  return { found: true, section: true, expanded: /menos/i.test(norm(c.innerText)) };
}
"""

# Achata o cabeçalho do jogo (minuto/placar) e o começo da página.
HEAD_TEXT = r"""
() => (document.body.innerText || '').slice(0, 2500)
"""

BODY_TEXT = r"""
() => document.body.innerText || ''
"""

# Marca botão de remover seleção do cupom (heurísticas; ajuste em selectors.py se precisar).
TAG_SLIP_REMOVE = r"""
(cssList) => {
  document.querySelectorAll('[data-bot-slip-x]').forEach(e => e.removeAttribute('data-bot-slip-x'));
  const title = [...document.querySelectorAll('body *')].find(e =>
    /^Boletim De Apostas/i.test((e.innerText || '').trim()) && (e.innerText || '').trim().length < 40);
  let root = title;
  for (let i = 0; i < 6 && root && root.parentElement; i++) {
    root = root.parentElement;
    if (/Mais de|Menos de|Acima|Abaixo/i.test(root.innerText || '')) break;
  }
  if (!root) return { found: false };
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  for (const css of cssList) {
    const el = [...root.querySelectorAll(css)].filter(vis)[0];
    if (el) { el.setAttribute('data-bot-slip-x', '1'); return { found: true, via: css }; }
  }
  // último recurso: elemento com texto "×"/"✕"/"x" curto
  const x = [...root.querySelectorAll('*')].filter(e => vis(e) && /^(×|✕|✖|x|X)$/.test((e.innerText || '').trim()))[0];
  if (x) { x.setAttribute('data-bot-slip-x', '1'); return { found: true, via: 'text-x' }; }
  return { found: false };
}
"""

# Marca o campo "Aposta" (valor) do cupom: procura o rótulo "Aposta" e o input mais próximo.
TAG_STAKE_INPUT = r"""
() => {
  document.querySelectorAll('[data-bot-stake]').forEach(e => e.removeAttribute('data-bot-stake'));
  const labels = [...document.querySelectorAll('body *')].filter(e =>
    (e.innerText || '').trim() === 'Aposta' && e.children.length === 0);
  for (const l of labels) {
    let p = l;
    for (let i = 0; i < 4 && p; i++, p = p.parentElement) {
      const inp = p.querySelector('input');
      if (inp) { inp.setAttribute('data-bot-stake', '1'); return { input: true }; }
    }
    l.setAttribute('data-bot-stake', '1');
    return { input: false };
  }
  return null;
}
"""


# Diagnóstico do cupom: o que existe de campos/botões/textos + HTML (para eu ver o que o robô vê de verdade).
SLIP_REPORT = r"""
() => {
  const TXT = { acceptNode: n => /^(SCRIPT|STYLE|NOSCRIPT)$/.test((n.parentElement || {}).tagName || '') ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT };
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const box = e => { const r = e.getBoundingClientRect(); return [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)]; };
  const desc = e => ({ tag: e.tagName, type: e.type || '', id: e.id || '', name: e.name || '', ph: e.placeholder || '',
    aria: e.getAttribute('aria-label') || '', inputmode: e.getAttribute('inputmode') || '', ro: !!e.readOnly, dis: !!e.disabled,
    cls: String(e.className || '').slice(0, 80), val: e.value === undefined ? '' : String(e.value).slice(0, 30),
    text: (e.innerText || '').trim().slice(0, 40), box: box(e), vis: vis(e) });
  const title = [...document.querySelectorAll('body *')].find(e => /^Boletim De Apostas/i.test((e.innerText || '').trim()) && (e.innerText || '').trim().length < 40);
  let root = title;
  for (let i = 0; i < 8 && root && root.parentElement; i++) { root = root.parentElement; if (/Mais de|Menos de/i.test(root.innerText || '')) break; }
  if (!root) return { found: false, body: (document.body.innerText || '').slice(0, 1500) };
  const lines = []; const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, TXT); let n;
  while ((n = w.nextNode())) { const t = n.nodeValue.replace(/\s+/g, ' ').trim(); if (t) lines.push(t); }
  return {
    found: true,
    inputs: [...root.querySelectorAll('input,textarea,[contenteditable],[role=textbox]')].map(desc),
    buttons: [...root.querySelectorAll('button,[role=button]')].map(desc),
    lines: lines.slice(0, 80),
    html: root.outerHTML.slice(0, 14000),
  };
}
"""

# Fallback: acha o campo de valor no cupom quando não existe o rótulo "Aposta".
TAG_STAKE_FALLBACK = r"""
() => {
  document.querySelectorAll('[data-bot-stake]').forEach(e => e.removeAttribute('data-bot-stake'));
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const title = [...document.querySelectorAll('body *')].find(e => /^Boletim De Apostas/i.test((e.innerText || '').trim()) && (e.innerText || '').trim().length < 40);
  let root = title;
  for (let i = 0; i < 8 && root && root.parentElement; i++) { root = root.parentElement; if (/Mais de|Menos de/i.test(root.innerText || '')) break; }
  if (!root) return null;
  const inputs = [...root.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([type=radio]),textarea,[contenteditable=true],[role=textbox]')].filter(vis);
  if (!inputs.length) return null;
  // o campo de valor costuma ser o que tem placeholder/aria ligado a aposta/stake/valor; senão o primeiro
  const pick = inputs.find(e => /aposta|stake|valor|amount/i.test((e.placeholder || '') + (e.getAttribute('aria-label') || '') + (e.id || '') + (e.name || ''))) || inputs[0];
  pick.setAttribute('data-bot-stake', '1');
  return { input: pick.tagName === 'INPUT' || pick.tagName === 'TEXTAREA', via: 'fallback' };
}
"""


# =====================================================================================================
# Estrutura REAL da tela do jogo (lida do HTML salvo pelo robô logado, 21/09/2026):
#   placar  : .score-board > .score-row > .team-name-section + 4x .score-column (escanteios, amarelos,
#             vermelhos, GOLS)  ;  relógio em .time-live ("AO VIVO" + "1º Tempo - 12'")
#   mercados: .section-container > .section-content > .section-header > .header-name ("Acima/Abaixo - Partida")
#             botões de odd: button.odd-button ("o 2.5" + "1.751"); as seções são virtualizadas (renderIfVisible)
#             e os botões são recriados a cada mudança de odd (classes odd-up / odd-down).
#   cupom   : painel que sobe de baixo (.slide-container) com título "Boletim De Apostas" e botão de recolher
#             .footer-page-header-btn. Quando aberto ele cobre a página inteira (as odds não recebem clique).
# =====================================================================================================

_COMMON = r"""
const norm = s => (s || '').replace(/\s+/g, ' ').trim();
const vis = e => { if (!e) return false; const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
const SKIP = /^(SCRIPT|STYLE|NOSCRIPT|TEMPLATE)$/;
// texto "de verdade": só nós de texto fora de script/style, separados por espaço (textContent gruda "o 2.5"+"1.751")
const leafText = el => {
  if (!el) return '';
  const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, { acceptNode: n =>
      SKIP.test((n.parentElement || {}).tagName || '') ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT });
  const out = []; let n;
  while ((n = w.nextNode())) { const t = n.nodeValue.replace(/\s+/g, ' ').trim(); if (t) out.push(t); }
  return out.join(' ');
};
const sheetInfo = () => {
  const H = innerHeight;
  const titles = [...document.querySelectorAll('body *')].filter(e => vis(e) && e.children.length <= 4 &&
     /^Boletim De Apostas/i.test(leafText(e)) && leafText(e).length < 60);
  let best = null;
  for (const t of titles) {
    const r = t.getBoundingClientRect();
    if (r.top < H - 120 && (!best || r.top < best.r.top)) best = { t, r };
  }
  if (!best) return { open: false, root: null, top: null, H };
  const root = best.t.closest('.slide-container') ||
    (() => { let p = best.t; for (let i = 0; i < 8 && p.parentElement; i++) { p = p.parentElement;
               if (p.getBoundingClientRect().height > 200) return p; } return best.t.parentElement; })();
  return { open: true, root, top: Math.round(best.r.top), H };
};
// botão "o <linha>" SÓ da seção "Acima/Abaixo - Partida" (existe outro "o 2.5" em "Total da equipe")
const overRx = line => new RegExp('^o\\s*' + String(line).replace('.', '\\.') + '\\s*(\\d+\\.\\d{2,3})$', 'i');
const findOver = line => {
  const rx = overRx(line);
  const secs = [...document.querySelectorAll('.section-container, .section-content')].filter(sc => {
    const h = sc.querySelector('.header-name');
    return h && /^Acima\s*\/\s*Abaixo\s*-\s*Partida$/i.test(leafText(h));
  });
  for (const sc of secs)
    for (const b of sc.querySelectorAll('button')) { const m = rx.exec(leafText(b)); if (m) return { b, odd: parseFloat(m[1]), secs: secs.length }; }
  return { b: null, odd: null, secs: secs.length };
};
const navSlip = () => {
  const own = e => [...e.childNodes].filter(n => n.nodeType === 3).map(n => n.nodeValue).join(' ');
  const el = [...document.querySelectorAll('body *')].filter(e => vis(e) && /Boletim/i.test(own(e)) &&
      e.getBoundingClientRect().top > innerHeight - 140)[0];
  return el ? (el.closest('a,button,li,[role=button],[class*=item],[class*=tab]') || el.parentElement || el) : null;
};
"""

# Estado do painel do cupom.
SHEET_STATE = "() => {" + _COMMON + r"""
  const s = sheetInfo();
  const text = s.root ? leafText(s.root) : '';
  const inputs = s.root ? [...s.root.querySelectorAll('input,textarea,[contenteditable=true],[role=textbox]')].filter(vis).length : 0;
  return { open: s.open, top: s.top, H: s.H, empty: /No bet selected|Nenhuma aposta|Tap on odds/i.test(text),
           inputs, text: text.slice(0, 500) };
}
"""

# Marca o botão de recolher do painel (data-bot-close) para o Playwright clicar; devolve como achou.
TAG_SHEET_CLOSE = "() => {" + _COMMON + r"""
  document.querySelectorAll('[data-bot-close]').forEach(e => e.removeAttribute('data-bot-close'));
  const s = sheetInfo();
  if (!s.open) return null;
  const SEL = '[class*="footer-page-header-btn"]';
  const inRoot = [...(s.root || document).querySelectorAll(SEL)].filter(vis);
  const any = [...document.querySelectorAll(SEL)].filter(b => vis(b) && b.getBoundingClientRect().top < s.H - 100);
  let b = inRoot[0] || any[0];
  let via = b ? 'footer-page-header-btn' : null;
  if (!b) {   // botão na mesma faixa do título, do lado direito
    b = [...(s.root || document).querySelectorAll('button,[role=button]')].filter(x => {
      if (!vis(x)) return false; const r = x.getBoundingClientRect();
      return Math.abs(r.top - s.top) < 40 && r.left > innerWidth * 0.6 &&
             !x.closest('[id^="bet-slip-single-selections"],[class*="SelectionCard"]') && !/delete|remove|trash/i.test(x.className + (x.innerHTML.match(/data-name="([^"]+)"/) || [,''])[1]); })[0];
    via = b ? 'botao-na-linha-do-titulo' : null;
  }
  if (!b) return null;
  b.setAttribute('data-bot-close', '1');
  return via;
}
"""

# Placar/relógio lidos direto da estrutura do placar (não depende do texto da página inteira).
READ_SCOREBOARD = r"""
() => {
  const norm = s => (s || '').replace(/\s+/g, ' ').trim();
  const sb = document.querySelector('.score-board');
  if (!sb) return null;
  const tl = sb.querySelector('.time-live');
  const rows = [...sb.querySelectorAll('.score-row')].filter(r => r.querySelector('.team-name-section'));
  return {
    clock: tl ? norm(tl.textContent) : '',
    live: !!sb.querySelector('.live-icon'),
    teams: rows.map(r => ({ name: norm(r.querySelector('.team-name-section').textContent),
                            cols: [...r.querySelectorAll('.score-column')].map(c => norm(c.textContent)) })),
  };
}
"""

# Há seleção no cupom para a linha? (várias evidências, para NUNCA clicar de novo e desmarcar sem querer)
SELECTION_STATE = "(line) => {" + _COMMON + r"""
  const L = String(line).replace('.', '\\.');
  const s = sheetInfo();
  const sheetText = s.root ? leafText(s.root) : '';
  const maisDe = new RegExp('(Mais de|Over)\\s*' + L + '(?![\\d])', 'i');
  const nav = navSlip();
  let badge = null;
  if (nav) { const m = leafText(nav).match(/(\d+)/); badge = m ? parseInt(m[1]) : 0; }
  const o = findOver(line);
  return {
    sheetOpen: s.open,
    sheetEmpty: /No bet selected|Nenhuma aposta|Tap on odds/i.test(sheetText),
    inSheet: s.open && maisDe.test(sheetText),
    inBody: maisDe.test(document.body.innerText || ''),
    badge,
    btnCls: o.b ? String(o.b.className) : null,
    btnPressed: o.b ? (o.b.getAttribute('aria-pressed') || o.b.getAttribute('aria-selected') || null) : null,
  };
}
"""

# Lê a odd do "o <linha>" SÓ dentro da seção cujo título é exatamente "Acima/Abaixo - Partida" e marca o botão.
READ_OVER_DOM = "(line) => {" + _COMMON + r"""
  document.querySelectorAll('[data-bot-over]').forEach(e => e.removeAttribute('data-bot-over'));
  const o = findOver(line);
  if (!o.b) return { found: false, section: o.secs > 0 };
  o.b.setAttribute('data-bot-over', '1');
  return { found: true, section: true, odd: o.odd, cls: String(o.b.className),
           locked: !!o.b.disabled || /\b(lock|locked|disabled|suspend)/i.test(String(o.b.className)) };
}
"""

# Campo do valor DENTRO do painel do cupom.
TAG_STAKE_IN_SHEET = "() => {" + _COMMON + r"""
  document.querySelectorAll('[data-bot-stake]').forEach(e => e.removeAttribute('data-bot-stake'));
  const s = sheetInfo();
  const root = s.root || document.body;
  const ins = [...root.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([type=radio]),textarea,[contenteditable=true],[role=textbox],[role=spinbutton]')].filter(vis);
  const lab = e => (e.placeholder || '') + ' ' + (e.getAttribute('aria-label') || '') + ' ' + (e.id || '') + ' ' + (e.name || '');
  let pick = ins.find(e => e.matches('input.stake, input[id$="-stake"]')) ||
             ins.find(e => /aposta|stake|valor|amount|risco|risk/i.test(lab(e) + ' ' + (e.parentElement && e.parentElement.getAttribute('data-placeholder') || ''))) || ins[0];
  if (pick) { pick.setAttribute('data-bot-stake', '1');
              return { input: pick.tagName === 'INPUT' || pick.tagName === 'TEXTAREA', via: 'input', ro: !!pick.readOnly,
                       desc: pick.tagName + ' ' + lab(pick).trim() }; }
  // sem input: um rótulo "Aposta"/"Stake" que abre o teclado numérico ao ser tocado
  const l = [...root.querySelectorAll('*')].filter(e => vis(e) && e.children.length === 0 &&
      /^(aposta|stake|valor)$/i.test(norm(e.textContent)))[0];
  if (l) { l.setAttribute('data-bot-stake', '1'); return { input: false, via: 'rotulo', ro: true, desc: norm(l.textContent) }; }
  return null;
}
"""

# Tecla do teclado numérico na tela (dentro do painel): a mais baixa com o texto exato.
TAG_KEYPAD = "(ch) => {" + _COMMON + r"""
  document.querySelectorAll('[data-bot-key]').forEach(e => e.removeAttribute('data-bot-key'));
  const s = sheetInfo();
  const root = s.root || document.body;
  const cands = [...root.querySelectorAll('button,[role=button],div,span')].filter(e => vis(e) &&
      norm(e.textContent) === ch && [...e.children].every(c => norm(c.textContent) === ch || !norm(c.textContent)));
  if (!cands.length) return false;
  cands.sort((a, b) => b.getBoundingClientRect().top - a.getBoundingClientRect().top);
  const k = cands[0].closest('button,[role=button]') || cands[0];
  k.setAttribute('data-bot-key', '1');
  return true;
}
"""

# Remover a seleção dentro do painel (lixeira / x / "Remover tudo").
TAG_SHEET_REMOVE = "() => {" + _COMMON + r"""
  document.querySelectorAll('[data-bot-slip-x]').forEach(e => e.removeAttribute('data-bot-slip-x'));
  const s = sheetInfo();
  if (!s.open || !s.root) return null;
  const root = s.root;
  const byText = [...root.querySelectorAll('button,[role=button],a,span,div')].filter(e => vis(e) && e.children.length <= 2 &&
      /^(remover tudo|limpar( tudo)?|clear all|remove all|excluir tudo)$/i.test(norm(e.textContent)))[0];
  const byAttr = [...root.querySelectorAll('[aria-label*="remov" i],[aria-label*="delet" i],[aria-label*="excluir" i],' +
      '[class*="remove" i],[class*="delete" i],[class*="trash" i],[data-name*="delete" i],[data-name*="trash" i],[data-name*="close" i]')]
      .filter(e => vis(e) && !e.closest('.footer-page-header-btn'));
  const trash = [...root.querySelectorAll('button.delete-icon')].filter(vis)[0];
  let el = trash || byText || byAttr[0];
  if (!el) return null;
  el = el.closest('button,[role=button]') || el;
  el.setAttribute('data-bot-slip-x', '1');
  return trash ? 'lixeira' : (byText ? 'texto' : 'atributo');
}
"""

# HTML COMPLETO do painel do cupom (para diagnóstico: é o que precisamos ver se algo falhar).
SHEET_HTML = "() => {" + _COMMON + r"""
  const s = sheetInfo();
  const root = s.root;
  if (!root) return null;
  const c = root.cloneNode(true);
  c.querySelectorAll('svg path').forEach(p => p.removeAttribute('d'));
  return c.outerHTML.slice(0, 120000);
}
"""

# Marca o item "Boletim De Apostas" do menu de baixo (abre o painel do cupom).
TAG_NAV_SLIP = "() => {" + _COMMON + r"""
  document.querySelectorAll('[data-bot-nav]').forEach(e => e.removeAttribute('data-bot-nav'));
  const n = navSlip();
  if (!n) return null;
  n.setAttribute('data-bot-nav', '1');
  return leafText(n).slice(0, 40);
}
"""


# Pop-up (modal) aberto por cima: "Limpar boletim de apostas", "Please login first", etc.
MODAL_STATE = "() => {" + _COMMON + r"""
  const ovs = [...document.querySelectorAll('[class*="ModalOverlay"], [role="dialog"], [class*="modal-overlay" i]')].filter(vis);
  if (!ovs.length) return null;
  const ov = ovs[ovs.length - 1];
  return { text: leafText(ov).slice(0, 300),
           buttons: [...ov.querySelectorAll('button,[role=button]')].filter(vis).map(b => leafText(b) || (b.getAttribute('aria-label') || '') || b.className.slice(0, 40)),
           html: ov.outerHTML.slice(0, 20000) };
}
"""

# Marca um botão do modal pelo texto (regex em string).
TAG_MODAL_BUTTON = "(pat) => {" + _COMMON + r"""
  document.querySelectorAll('[data-bot-modal]').forEach(e => e.removeAttribute('data-bot-modal'));
  const ovs = [...document.querySelectorAll('[class*="ModalOverlay"], [role="dialog"], [class*="modal-overlay" i]')].filter(vis);
  if (!ovs.length) return null;
  const ov = ovs[ovs.length - 1];
  const rx = new RegExp(pat, 'i');
  const b = [...ov.querySelectorAll('button,[role=button]')].filter(vis).find(x => rx.test(leafText(x)));
  if (!b) return null;
  b.setAttribute('data-bot-modal', '1');
  return leafText(b);
}
"""

# Odd e status da seleção DENTRO do cupom (a odd de verdade, que vale para a aposta).
SLIP_SELECTION = "(line) => {" + _COMMON + r"""
  const s = sheetInfo();
  const root = s.root || document;
  const L = String(line);
  const cards = [...root.querySelectorAll('[class*="SelectionCard"], #bet-slip-single-selections > div')];
  const all = [];
  for (const c of cards) {
    const name = leafText(c.querySelector('.selection-name'));
    if (!new RegExp('Mais de\\s*' + L.replace('.', '\\.') + '(?![\\d])', 'i').test(name)) continue;
    const ov = c.querySelector('.odd-value');
    const inp = c.querySelector('input.stake');
    all.push({ found: true, name, odd: ov ? parseFloat(leafText(ov)) : null,
             status: inp ? inp.getAttribute('data-status') : null,
             minStake: inp ? parseFloat(inp.getAttribute('data-min-stake')) : null,
             maxStake: inp ? parseFloat(inp.getAttribute('data-max-stake')) : null,
             event: leafText(c.querySelector('.event-name')),
             live: /AO VIVO|LIVE/i.test(leafText(c.querySelector('.first-line') || c)),
             score: (leafText(c.querySelector('.event-name')).match(/\[(\d{1,2})\s*-\s*(\d{1,2})\]/) || []).slice(1).map(Number),
             sig: leafText(c).slice(0, 200) });
  }
  if (!all.length) return { found: false, cards: cards.length, all: [] };
  return Object.assign({}, all[0], { all, cards: cards.length });
}
"""

# ---------------------------------------------------------------- lista ao vivo (rolagem em passos)
# A lista é VIRTUALIZADA: só os jogos perto da tela existem no HTML. Rolar até o fim e voltar ao topo (o que o
# robô fazia) deixa só os primeiros ~5 jogos desenhados. Por isso rolamos em passos e lemos a cada passo.
SCROLL_STEP = r"""
(frac) => {
  const cands = [document.scrollingElement, ...[...document.querySelectorAll('*')].filter(e => {
      const s = getComputedStyle(e); return /(auto|scroll)/.test(s.overflowY) && e.scrollHeight > e.clientHeight + 40; })];
  let sc = null, best = -1;
  for (const e of cands) { if (!e) continue; const room = e.scrollHeight - e.clientHeight; if (room > best) { best = room; sc = e; } }
  if (!sc) return null;
  const before = sc.scrollTop;
  if (frac === 'top') sc.scrollTop = 0;
  else sc.scrollTop = Math.min(sc.scrollHeight - sc.clientHeight, before + sc.clientHeight * frac);
  return { before: Math.round(before), top: Math.round(sc.scrollTop), max: Math.round(sc.scrollHeight - sc.clientHeight),
           h: Math.round(sc.clientHeight), el: sc === document.scrollingElement ? 'document' : (sc.tagName + '.' + String(sc.className).slice(0, 40)) };
}
"""

# Ligas recolhidas / botões "ver mais" na lista (para expandir). Marca com data-bot-expand e devolve os textos.
TAG_LIST_EXPANDERS = "() => {" + _COMMON + r"""
  document.querySelectorAll('[data-bot-expand]').forEach(e => e.removeAttribute('data-bot-expand'));
  const out = [];
  // botões de "carregar/ver/mostrar mais"
  for (const b of document.querySelectorAll('button,[role=button],a,span,div')) {
    if (!vis(b) || b.children.length > 3) continue;
    const t = leafText(b);
    if (/^(ver|mostrar|carregar|exibir) mais|^load more|^show more|^mostrar tudo$/i.test(t)) {
      (b.closest('button,[role=button],a') || b).setAttribute('data-bot-expand', String(out.length)); out.push('mais:' + t); }
  }
  // (ligas recolhidas NÃO são clicadas: na Pinnacle a classe "collapsed" aparece também em seções ABERTAS,
  //  e clicar fecharia a liga. Se faltar jogo, o HTML da lista é salvo para ajustarmos.)
  return out;
}
"""

# HTML da lista (diagnóstico), sem os desenhos dos ícones.
LIST_HTML = r"""
() => { const c = document.body.cloneNode(true);
  c.querySelectorAll('svg, script, style').forEach(e => e.remove());
  return c.innerHTML.slice(0, 400000); }
"""

# Lixeira do card de UM jogo (quando o cupom tem seleções de mais de um jogo).
TAG_CARD_DELETE = "(eventText) => {" + _COMMON + r"""
  document.querySelectorAll('[data-bot-slip-x]').forEach(e => e.removeAttribute('data-bot-slip-x'));
  const s = sheetInfo();
  const root = s.root || document;
  for (const c of root.querySelectorAll('[class*="SelectionCard"], #bet-slip-single-selections > div')) {
    if (leafText(c.querySelector('.event-name')) !== eventText) continue;
    const b = c.querySelector('button.delete-icon');
    if (b) { b.setAttribute('data-bot-slip-x', '1'); return true; }
  }
  return false;
}
"""
