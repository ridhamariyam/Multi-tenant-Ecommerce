import { RUNWAY_COPY } from './config';
import type { RunwayLook, RunwayPiece } from './load';

/**
 * The runway section as one HTML string.
 *
 * The `<runway-section>` custom element clones, moves and restyles its own
 * nodes, so React must never reconcile inside it. Rendering it through
 * dangerouslySetInnerHTML keeps React's hands off: a refresh with the same
 * data yields the same string, and React leaves the DOM alone.
 */

const SID = 'cliq-runway';

const esc = (s: unknown) =>
  String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

/** JSON inside <script type="application/json"> must not close the tag. */
const json = (v: unknown) => JSON.stringify(v).replace(/</g, '\\u003c');

const pieceCount = (n: number) => `${n} ${n === 1 ? 'piece' : 'pieces'}`;
const label = (look: RunwayLook, i: number) => `Look ${i + 1}: ${look.name}`;
const pad = (n: number) => String(n).padStart(2, '0');

const SVG = {
  plus: '<svg class="rw__ico-plus" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.3" aria-hidden="true"><path d="M12 4v16M4 12h16"/></svg>',
  check: '<svg class="rw__ico-check" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4.5 12.5l5 5L19.5 7"/></svg>',
  spin: '<svg class="rw__ico-spin" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><path d="M12 3a9 9 0 1 1-9 9"/></svg>',
  x: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><path d="M5 5l14 14M19 5L5 19"/></svg>',
  prev: '<svg width="26" height="14" viewBox="0 0 26 14" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M25 7H1M7 1L1 7l6 6"/></svg>',
  next: '<svg width="26" height="14" viewBox="0 0 26 14" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1 7h24M19 1l6 6-6 6"/></svg>',
  play: '<svg class="rw__ico-play" width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 4.5v15l12.5-7.5z"/></svg>',
  pause: '<svg class="rw__ico-pause" width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M6.5 4.5h3.5v15H6.5zM14 4.5h3.5v15H14z"/></svg>',
  arrow: '<svg class="rw__cta-arrow" width="22" height="12" viewBox="0 0 26 14" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1 7h24M19 1l6 6-6 6"/></svg>',
  ctaSpin: '<svg class="rw__cta-spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><path d="M12 3a9 9 0 1 1-9 9"/></svg>',
};

const TOKENS =
  '--rw-c-stage:#ffffff;--rw-c-panel:#ffffff;--rw-c-text:#151413;--rw-c-muted:#66625c;--rw-c-accent:#0e0e0e;--rw-c-on-accent:#ffffff;--rw-c-line:#c8c8c8;--rw-card:#DFDFDF;--rw-hf:var(--font-heading--family, inherit);--rw-hw:400;--rw-h-d:46px;--rw-h-m:24px;--rw-sub-d:12px;--rw-sub-m:12px;--rw-eyebrow-d:11px;--rw-eyebrow-m:10px;--rw-label-d:10px;--rw-label-m:9px;--rw-chip-d:17px;--rw-chip-m:18px;--rw-ph-d:18px;--rw-ph-m:16px;--rw-pt-size-d:13px;--rw-pt-size-m:12px;--rw-price-d:12px;--rw-price-m:12px;--rw-opt-d:11px;--rw-opt-m:11px;--rw-total-d:16px;--rw-total-m:16px;--rw-thumb-d:92px;--rw-thumb-m:62px;--rw-tag-top:18px;--rw-tag-left:0px;--rw-thumb-radius:0px;--rw-morph:900ms;--rw-bar-r:20px;--rw-panel-w:380px;--rw-panel-pad-d:32px;--rw-radius:0px;--rw-max:none;--rw-speed:5s;--rw-ax:40%;--rw-btn-radius:0px;--rw-pill-radius:30px;--rw-add-radius:20px';

function modelImg(look: RunwayLook): string {
  const { src, srcLarge } = look.model;
  return `<img src="${esc(src)}" srcset="${esc(src)} 640w, ${esc(srcLarge)} 1080w" sizes="(min-width: 1800px) 540px, (min-width: 750px) 420px, 320px" loading="eager" decoding="async" width="1100" height="1956" draggable="false" data-model-image alt="${esc(look.name)}">`;
}

function pins(look: RunwayLook): string {
  return look.pieces
    .map((p, j) => {
      const n = j + 1;
      return `<button type="button" class="rw__pin" data-rw-pin="${n}" data-tip="${esc(p.name)}" style="left:${p.pin[0]}%; top:${p.pin[1]}%; --pi:${n}" aria-label="${n}: ${esc(p.name)}" tabindex="-1"><span class="rw__pin-dot">${n}</span></button>`;
    })
    .join('');
}

function picker(look: RunwayLook, key: string, p: RunwayPiece, n: number): string {
  const pid = `Picker-${SID}-look_${key}-${n}`;
  const fieldsets = p.options
    .map((opt, oi) => {
      /* Pre-check the first value, in display order, that an available variant offers. */
      const checked = opt.values.find(v => p.variants.some(x => x.a && x.o[oi] === v)) ?? opt.values[0];
      const name = `Opt-${SID}-look_${key}-${n}-${oi + 1}`;
      const pills = opt.values
        .map(
          v =>
            `<label class="rw__pill"><input type="radio" name="${esc(name)}" value="${esc(v)}" data-rw-option="${oi}"${v === checked ? ' checked' : ''}><span class="rw__pill-label">${esc(v)}</span></label>`,
        )
        .join('');
      return `<fieldset class="rw__opt"><legend class="rw__opt-name">${esc(opt.name)}</legend><div class="rw__opt-values">${pills}</div></fieldset>`;
    })
    .join('');
  const thumb = p.image
    ? `<img class="rw__picker-thumb" src="${esc(p.image)}" width="160" height="200" loading="lazy" decoding="async" alt="">`
    : '<span class="rw__picker-thumb"></span>';
  return `<div class="rw__picker" id="${pid}" data-rw-picker hidden><div class="rw__picker-head">${thumb}<div class="rw__picker-info"><span class="rw__picker-title">${esc(p.name)}</span><span class="rw__picker-price">${esc(p.priceLabel)}</span></div><button type="button" class="rw__pick-x" data-rw-pick-close aria-label="Close">${SVG.x}</button></div>${fieldsets}<button type="button" class="rw__confirm" data-rw-confirm><span data-rw-confirm-label data-add="Add to bag">Add to bag</span><span class="rw__sr"> — ${esc(p.name)}</span></button><script type="application/json" data-rw-variants>${json(p.variants)}</script></div>`;
}

function item(look: RunwayLook, key: string, p: RunwayPiece, j: number): string {
  const n = j + 1;
  const hasPicker = !p.directVariantId && !p.soldOut;
  const pid = `Picker-${SID}-look_${key}-${n}`;
  const media = p.image
    ? `<img src="${esc(p.image)}" width="400" height="500" loading="lazy" decoding="async" alt="">`
    : '';
  const addAttrs = p.soldOut
    ? `disabled aria-label="Sold out: ${esc(p.name)}"`
    : hasPicker
      ? `aria-expanded="false" aria-controls="${pid}" aria-label="Add to bag: ${esc(p.name)}"`
      : `aria-label="Add to bag: ${esc(p.name)}"`;
  const price = p.soldOut ? `<span>${esc(p.priceLabel)}</span><span class="rw__soldout">Sold out</span>` : `<span>${esc(p.priceLabel)}</span>`;

  return `<li class="rw__item${p.soldOut ? ' is-soldout' : ''}" data-rw-card="${n}" style="--i:${n}" data-title="${esc(p.name)}"${p.directVariantId ? ` data-variant-id="${esc(p.directVariantId)}"` : ''}>${
    p.tag ? `<span class="rw__tag"><span class="rw__tag-text">${esc(p.tag)}</span></span>` : ''
  }<a class="rw__media" href="${esc(p.url)}" tabindex="-1" aria-hidden="true">${media}<span class="rw__num">${n}</span></a><div class="rw__info"><span class="rw__type">${esc(p.vendor)}</span><a class="rw__name" href="${esc(p.url)}">${esc(p.name)}</a><span class="rw__price">${price}</span></div><button type="button" class="rw__add" data-rw-add ${addAttrs} data-added-label="Added to bag: ${esc(p.name)}">${SVG.plus}${SVG.check}${SVG.spin}</button>${
    hasPicker ? picker(look, key, p, n) : ''
  }</li>`;
}

function panel(look: RunwayLook, i: number): string {
  const key = pad(i + 1);
  const count = pieceCount(look.pieces.length);
  const buyable = look.pieces.some(p => !p.soldOut);
  const list = look.pieces.length
    ? `<ul class="rw__items" role="list">${look.pieces.map((p, j) => item(look, key, p, j)).join('')}</ul>`
    : '<p class="rw__empty">The pieces for this look are on their way.</p>';
  const total = look.totalLabel
    ? `<div class="rw__bundle-price"><strong>${esc(look.totalLabel)}</strong></div>`
    : '';
  const bundle = look.pieces.length
    ? `<div class="rw__bundle has-rule"><p class="rw__msg" data-rw-msg role="status" aria-live="polite"></p><div class="rw__bundle-row"><div class="rw__bundle-copy"><span class="rw__bundle-title">Complete the look</span><span class="rw__bundle-note">${esc(count)}</span></div>${total}</div><button type="button" class="rw__cta" data-rw-all${buyable ? '' : ' disabled'}><span class="rw__cta-add">${buyable ? 'Add full look to bag' : 'Sold out'}</span><span class="rw__cta-m">${buyable ? `Add full look${look.totalLabel ? ` — ${esc(look.totalLabel)}` : ''}` : 'Sold out'}</span><span class="rw__cta-done">Full look in your bag</span>${SVG.arrow}${SVG.ctaSpin}</button></div>`
    : '';

  return `<div class="rw__look-panel${i === 0 ? ' is-in' : ''}" data-rw-panel="${i}"${i === 0 ? '' : ' hidden'}><div class="rw__mhead"><span class="rw__mhead-title">${esc(look.name)}</span><span class="rw__label">${esc(count)}</span></div>${list}${bundle}<template data-rw-pieces-text>${esc(count)}</template></div>`;
}

export function renderRunwayMarkup(looks: RunwayLook[]): string {
  const bodies = looks
    .map(
      (l, i) =>
        `<div class="rw__model" data-rw-model data-index="${i}" aria-hidden="true"><span class="rw__shadow"></span><div class="rw__figure" style="--rw-ar: 0.5625"><div class="rw__art">${modelImg(l)}<button type="button" class="rw__hit" data-rw-go="${i}" aria-label="${esc(label(l, i))}" tabindex="-1"></button></div></div></div>`,
    )
    .join('');

  const heroes = looks
    .map(
      (l, i) =>
        `<div class="rw__hero${i === 0 ? ' is-on' : ''}" data-rw-hero data-index="${i}" data-name="${esc(l.name)}" data-label="${esc(label(l, i))}" data-probe="${esc(l.model.src)}" aria-hidden="${i === 0 ? 'false' : 'true'}"><div class="rw__morph"><span class="rw__shadow"></span><div class="rw__figure" style="--rw-ar: 0.5625"><div class="rw__art">${modelImg(l)}<button type="button" class="rw__zoom" data-rw-zoom aria-label="View look: ${esc(l.name)}" tabindex="-1"></button><div class="rw__pins">${pins(l)}</div></div></div></div></div>`,
    )
    .join('');

  const ticks = looks
    .map(
      (l, i) =>
        `<button type="button" class="rw__tick" data-rw-tick="${i}" aria-current="${i === 0 ? 'true' : 'false'}" aria-label="${esc(label(l, i))}"><span class="rw__tick-bar"></span><span class="rw__tick-label">${pad(i + 1)}<span class="rw__tick-name">&nbsp;&nbsp;${esc(l.name)}</span></span></button>`,
    )
    .join('');

  return `<runway-section id="Runway-${SID}" class="rw rw--add-icon rw--popup rw--list has-dividers has-border" data-feel="balanced" data-blur="true" data-mblur="true" data-style="ring" data-mstyle="classic" data-fit="true" data-height-mode="original" data-height-vh="100" data-mheight-mode="custom" data-mheight-vh="109" data-reflect="false" data-autoplay="true" data-speed="5000" data-after-add="stay" data-bundle-code="" data-msg-choose="Pick a size for: [items]" data-msg-error="Couldn’t add to bag. Please try again." data-msg-soldout="Sold out" style="${TOKENS}"><div class="rw__sticky"><div class="rw__grid"><div class="rw__left"><div class="rw__head"><div class="rw__intro"><h2 class="rw__title">${esc(RUNWAY_COPY.title)}</h2><p class="rw__sub">${esc(RUNWAY_COPY.subtitle)}</p></div><span class="rw__sr" aria-live="polite" aria-atomic="true" data-rw-live></span></div><div class="rw__stage" data-rw-stage tabindex="0" role="region" aria-roledescription="carousel" aria-label="${esc(RUNWAY_COPY.title)} — use arrow keys or swipe to change look"><div class="rw__actors" data-rw-actors>${bodies}</div><div class="rw__heroes" data-rw-heroes>${heroes}</div><span class="rw__sweep"></span><span class="rw__cursor" data-rw-cursor><span class="rw__cursor-in"><span class="rw__cursor-label rw__cursor-drag">Drag</span><span class="rw__cursor-label rw__cursor-view">View</span></span></span><span class="rw__walk"><span class="rw__walk-line"></span></span></div><div class="rw__controls"><button type="button" class="rw__icon" data-rw-prev aria-label="Previous look">${SVG.prev}</button><div class="rw__ticks">${ticks}</div><button type="button" class="rw__icon rw__auto" data-rw-auto aria-pressed="false" aria-label="Autoplay">${SVG.play}${SVG.pause}</button><button type="button" class="rw__icon" data-rw-next aria-label="Next look">${SVG.next}</button></div><div class="rw__lb" data-rw-lb data-word="Look" role="region" aria-label="View look" aria-hidden="true"><div class="rw__lb-stage" data-rw-lb-stage></div><div class="rw__lb-top"><p class="rw__lb-cap"><span class="rw__lb-kicker" data-rw-lb-kicker></span><span class="rw__lb-name" data-rw-lb-name></span></p><button type="button" class="rw__lb-close" data-rw-zoom-close aria-label="Close">${SVG.x}</button></div><p class="rw__lb-hint">Tap a dot to shop the piece</p></div></div><aside class="rw__panel has-rule"><div class="rw__panel-inner"><div class="rw__panel-head"><h3 class="rw__panel-title">In this look</h3><span class="rw__label" data-rw-pieces></span></div>${looks.map(panel).join('')}</div></aside></div></div></runway-section>`;
}
