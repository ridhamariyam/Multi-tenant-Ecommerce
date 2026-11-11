/* eslint-disable */
// @ts-nocheck -- vanilla custom element, loaded by RunwayClient.
(() => {
'use strict';
const TAU = Math.PI * 2;
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const RM = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
/* =================== Cart bridge ===================
 * The element never talks to the API itself. It asks the page (RunwayClient)
 * to add variants to the real storefront cart and waits for the answer:
 * { added: string[], error: string | null }.
 */
const addToCart = variantIds => new Promise(resolve => {
  const ev = new CustomEvent('cliq:add-to-cart', { cancelable: true, detail: { variantIds, resolve } });
  document.dispatchEvent(ev);
  if (!ev.defaultPrevented) resolve({ added: [], error: null, unhandled: true });
});

/* =================== Runway section =================== */
class RunwaySection extends HTMLElement {
  connectedCallback() {
    if (this._init) return;
    this._init = true;
    const d = this.dataset;
    this.feel = { K: 95, lag: 0.04 };
    this.K = this.feel.K;
    this.C = 2 * Math.sqrt(this.K);
    this.blur = d.blur === 'true';
    this.dStyle = d.style || 'ring';
    this.mStyle = d.mstyle || 'classic';
    this.speed = parseInt(d.speed, 10) || 5000;
    this.msgChoose = d.msgChoose || 'Pick a size for: [items]';
    this.msgError = d.msgError || 'Couldn’t add to bag. Please try again.';
    this.msgSoldout = d.msgSoldout || 'Sold out';
    this.rm = RM();

    this.stage = this.querySelector('[data-rw-stage]');
    this.actors = this.querySelector('[data-rw-actors]');
    this.heroes = [...this.querySelectorAll('[data-rw-hero]')];
    this.n = this.heroes.length;
    this.panels = [...this.querySelectorAll('[data-rw-panel]')];
    this.ticks = [...this.querySelectorAll('[data-rw-tick]')];
    this.live = this.querySelector('[data-rw-live]');
    this.piecesLabel = this.querySelector('[data-rw-pieces]');
    this.panel = this.querySelector('.rw__panel');
    this.lb = this.querySelector('[data-rw-lb]');
    this.lbStage = this.querySelector('[data-rw-lb-stage]');
    this.cursor = this.querySelector('[data-rw-cursor]');
    this.autoBtn = this.querySelector('[data-rw-auto]');

    // clones -> N bodies
    const originals = [...this.actors.querySelectorAll('[data-rw-model]')];
    const N = this.n * Math.ceil(8 / this.n);
    for (let a = this.n; a < N; a++) {
      const c = originals[a % this.n].cloneNode(true);
      c.setAttribute('data-rw-clone', '');
      c.querySelectorAll('img').forEach(i => { i.loading = 'lazy'; i.classList.remove('is-decoded'); });
      this.actors.append(c);
    }
    this.bodies = [...this.actors.querySelectorAll('[data-rw-model]')].map((el, a) => ({
      el, a, look: a % this.n, w: 0, hit: el.querySelector('.rw__hit'),
      x: 0, v: 0, g: 0, goal: 0, trip: false, from: 0, last: {}
    }));
    this.N = N;

    // cards
    this.cards = [];
    this.panels.forEach(p => p.querySelectorAll('[data-rw-card]').forEach(card => {
      card.picker = card.querySelector('[data-rw-picker]');
      card.addBtn = card.querySelector('[data-rw-add]');
      if (card.picker) {
        card.picker.card = card;
        try { card._variants = JSON.parse(card.picker.querySelector('[data-rw-variants]').textContent); } catch { card._variants = []; }
        this.updateVariant(card, false);
      }
      this.cards.push(card);
    }));

    // state
    this.index = 0;
    this.target = 0;
    const start = this.rm ? 0 : 1.15;
    this.cur = -start;
    this.vel = 0;
    this.bodies.forEach(s => { s.goal = this.wrapN(s.a - this.target); s.x = s.g = s.goal + start; });
    this.still = false;
    this.dragging = false;
    this.playing = false;
    this.visible = false;
    this.engaged = false;
    this.panelHover = false;
    this.zoomed = false;
    this.revealed = false;
    this.raf = 0;
    this.lastT = 0;
    this.suppress = 0;
    this.wheelAcc = 0;
    this.wheelLock = 0;
    this.vh = window.innerHeight;
    this.vw = window.innerWidth;

    this.classList.add('rw--js');
    this.decodeImages(this);
    this.bind();
    this.measure();
    this.setIndex(0, true);
    this.probeFeet();
    this.setupCursor();
    this.reveal();
    if (d.autoplay === 'true' && !this.rm && !(window.Shopify && window.Shopify.designMode)) this.play(true);
  }

  disconnectedCallback() {
    cancelAnimationFrame(this.raf); this.raf = 0;
    cancelAnimationFrame(this.curRaf);
    clearTimeout(this.timer); clearTimeout(this.resizeT); clearTimeout(this.lbT);
    this.io?.disconnect(); this.revealIo?.disconnect(); this.ro?.disconnect();
    window.removeEventListener('resize', this._onResize);
    document.removeEventListener('visibilitychange', this._onVis);
    this.closeSheet();
    this.host?.remove();
    this._init = false;
  }

  /* ---------- helpers ---------- */
  wrapN(v) { const N = this.N; return ((v % N) + N) % N; }
  get mobile() { return window.innerWidth <= 749; }
  get mode() { return this.mobile ? this.mStyle : this.dStyle; }

  decodeImages(root) {
    root.querySelectorAll('[data-model-image]').forEach(img => {
      if (img.classList.contains('is-decoded')) return;
      const done = () => img.classList.add('is-decoded');
      const p = img.decode ? img.decode() : Promise.reject();
      p.then(done).catch(() => {
        if (img.naturalWidth) done();
        else img.addEventListener('load', done, { once: true });
      });
    });
  }

  /* ---------- measure ---------- */
  measure() {
    const mob = this.mobile;
    const wasMode = this._mode;
    this._mode = this.mode;
    if (wasMode && wasMode !== this._mode) {
      if (!mob) this.closeSheet();
      this.bodies.forEach(s => { s.goal = this.wrapN(s.a - this.target); s.x = s.g = s.goal; s.v = 0; s.trip = false; });
      this.cur = this.target; this.vel = 0;
    }
    let frameH;
    if (mob) {
      const w = window.innerWidth, h = window.innerHeight;
      if (w !== this.vw || Math.abs(h - this.vh) >= 160) { this.vw = w; this.vh = h; }
      frameH = this.vh * clamp(parseFloat(this.dataset.mheightVh) || 109, 50, 120) / 100;
    } else {
      this.vw = window.innerWidth; this.vh = window.innerHeight;
      let head = 0;
      document.querySelectorAll('.shopify-section-group-header-group, #shopify-section-header, #shopify-section-announcement-bar').forEach(el => {
        if (el.contains(this) || !el.getClientRects().length) return;
        head += el.getBoundingClientRect().height;
      });
      frameH = Math.max(380, window.innerHeight - head);
    }
    this.style.setProperty('--rw-frame-h', `${Math.round(frameH)}px`);

    const r = this.stage.getBoundingClientRect();
    this.W = r.width; this.H = r.height;
    const ring = this._mode === 'ring';
    this.fs = ring ? 1.08 : 1;
    this.style.setProperty('--rw-fs', this.fs);
    let modelH;
    if (ring) modelH = Math.max(200, Math.round((this.H - 34 - 18) / 1.08));
    else modelH = Math.max(200, Math.round(this.H - (mob ? 24 : 36) - 18));
    this.stage.style.setProperty('--rw-model-h', `${modelH}px`);
    let hx, hy;
    if (ring) { hx = 0.5 * this.W; hy = 34; }
    else {
      this.cl = mob
        ? { ax: .3, ay: 22, sx: .32, sy: 22, sr: .76, ex: .55, d: 4 }
        : { ax: .4, ay: 36, sx: .125, sy: 58, sr: .76, ex: .38, d: 5 };
      hx = this.cl.ax * this.W; hy = this.cl.ay;
    }
    this.stage.style.setProperty('--rw-hx', `${hx}px`);
    this.stage.style.setProperty('--rw-hy', `${hy}px`);
    this.style.setProperty('--rw-ax', `${(hx / (this.W || 1) * 100).toFixed(2)}%`);
    this.unit = ring ? Math.max(mob ? 90 : 120, 0.3 * this.W) : Math.max(90, this.W * 0.32 * 1.6);
    this.bodies.forEach(s => { s.w = s.el.offsetWidth; s.last = {}; });
    this.renderAll();
    this.kick();
  }

  /* ---------- placement ---------- */
  put(s, x, bottom, scale, op, blur, z) {
    const hw = s.w * scale / 2;
    if (x + hw < -4 || x - hw > this.W + 4) op = 0;
    const el = s.el, L = s.last;
    const t = `translate3d(${x.toFixed(2)}px,${(-bottom).toFixed(2)}px,0) translateX(-50%) scale(${scale.toFixed(4)})`;
    if (L.t !== t) { el.style.transform = t; L.t = t; }
    const o = op.toFixed(3);
    if (L.o !== o) { el.style.opacity = o; L.o = o; }
    if (L.z !== z) { el.style.zIndex = z; L.z = z; }
    const vis = op < 0.01 ? 'hidden' : 'visible';
    if (L.vis !== vis) { el.style.visibility = vis; L.vis = vis; }
    const pe = op < 0.5 ? 'none' : '';
    if (L.pe !== pe) { el.style.pointerEvents = pe; L.pe = pe; }
    const b = this.blur ? Math.round(blur * 10) / 10 : 0;
    if (L.b !== b) {
      if (b <= 0.05) el.style.removeProperty('filter'); else el.style.filter = `blur(${b}px)`;
      L.b = b;
    }
  }

  renderAll() {
    if (!this.W) return;
    if (this._mode === 'ring') this.renderRing(); else this.renderClassic();
  }

  renderRing() {
    const { W, H, N } = this, mob = this.mobile;
    const cx = 0.5 * W, R = (mob ? 0.72 : 0.62) * W, P = (mob ? 1.9 : 1.65) * W;
    const floor = H - 34, hor = 0.36 * H, step = TAU / N, fs = this.fs;
    for (const s of this.bodies) {
      let phi = ((s.a - this.cur) * step) % TAU;
      if (phi > Math.PI) phi -= TAU;
      if (phi <= -Math.PI) phi += TAU;
      const z = R * (1 - Math.cos(phi));
      const persp = P / (P + z);
      const sl = Math.abs(phi) / step;
      const scale = persp * (1 + (fs - 1) * clamp(1 - sl, 0, 1));
      const x = cx + R * Math.sin(phi) * persp;
      const feet = hor + (floor - hor) * persp;
      const blur = sl <= 1 ? 1.8 * sl : Math.min(1.8 + (sl - 1) * 2, 6.5);
      let op = clamp((Math.cos(phi) + 0.55) / 0.3, 0, 1);
      if (this.still && sl < 0.02) op = 0;
      this.put(s, x, H - feet, scale, op, blur, Math.round(scale * 1000));
    }
  }

  renderClassic() {
    const { W } = this, c = this.cl;
    for (const s of this.bodies) {
      let k = s.x, e = -1;
      if (s.trip) {
        const span = Math.abs(s.goal - s.from) || 1;
        const u = clamp(Math.abs(s.x - s.from) / span, 0, 1);
        if (s.goal > s.from) {
          if (u < 0.5) e = 2 * u * 1.4; else k = s.goal + 2 * (1 - u);
        } else {
          if (u < 0.5) k = s.from + 2 * u; else e = 2 * (1 - u) * 1.4;
        }
      } else if (k < 0) e = Math.min(-k, 1.4);
      if (e >= 0) {
        this.put(s, W * (c.ax - c.ex * e), c.ay - 22 * e, 1 + 0.14 * e, Math.max(0, 1 - 1.05 * e), 4 * Math.min(e, 1), 1100);
      } else {
        let op = k <= c.d - 1 ? 1 - 0.13 * k : Math.max(0, 0.61 * (c.d - k));
        if (this.still && Math.abs(k) < 0.02) op = 0;
        this.put(s, W * (c.ax + c.sx * k), c.ay + c.sy * k, Math.pow(c.sr, k), op, Math.min(0.9 * k, 3.2), 1000 - Math.round(10 * k));
      }
    }
  }

  /* ---------- loop ---------- */
  kick() {
    if (this.raf || !this.visible || document.hidden || !this.revealed) return;
    this.raf = requestAnimationFrame(t => this.frame(t));
  }

  setStill(v) {
    if (this.still === v) return;
    this.still = v;
    this.classList.toggle('rw--still', v);
  }

  stepRing(dt) {
    if (this.rm) { this.cur = this.target; this.vel = 0; return true; }
    const h = dt / 3;
    for (let i = 0; i < 3; i++) {
      const acc = -this.K * (this.cur - this.target) - this.C * this.vel;
      this.vel += acc * h; this.cur += this.vel * h;
    }
    if (Math.abs(this.cur - this.target) <= 0.0005 && Math.abs(this.vel) <= 0.0005) {
      this.cur = this.target; this.vel = 0; return true;
    }
    return false;
  }

  stepClassic(dt) {
    let settled = true;
    const N = this.N;
    for (const s of this.bodies) {
      const goal = this.wrapN(s.a - this.target);
      if (Math.abs(goal - s.goal) > N / 2) {
        s.trip = true; s.from = s.x;
      }
      s.goal = goal;
      if (this.rm) { s.x = s.g = goal; s.v = 0; s.trip = false; continue; }
      const tau = this.dragging ? 0.016 : s.trip ? 0.1 : 0.03 + 0.04 * Math.min(goal, 4);
      s.g += (goal - s.g) * (1 - Math.exp(-dt / tau));
      const h = dt / 3;
      for (let i = 0; i < 3; i++) {
        const acc = -this.K * (s.x - s.g) - this.C * s.v;
        s.v += acc * h; s.x += s.v * h;
      }
      if (s.trip && Math.abs(s.x - goal) < 0.02) s.trip = false;
      if (Math.abs(s.x - goal) <= 0.0006 && Math.abs(s.v) <= 0.0006 && Math.abs(s.g - goal) <= 0.0006) {
        s.x = s.g = goal; s.v = 0; s.trip = false;
      } else settled = false;
    }
    return settled;
  }

  frame(t) {
    this.raf = 0;
    if (!this.visible || document.hidden) { this.lastT = 0; return; }
    const dt = this.lastT ? Math.min(0.034, (t - this.lastT) / 1000) : 1 / 60;
    this.lastT = t;
    const settled = this._mode === 'ring' ? this.stepRing(dt) : this.stepClassic(dt);
    if (settled && !this.dragging) {
      this.setStill(true);
      this.renderAll();
      this.lastT = 0;
      return;
    }
    this.setStill(false);
    this.renderAll();
    this.raf = requestAnimationFrame(tt => this.frame(tt));
  }

  /* ---------- index ---------- */
  rank(s) {
    if (this._mode === 'ring') {
      let k = this.wrapN(s.a - Math.round(this.target));
      if (k > this.N / 2) k -= this.N;
      return k;
    }
    return this.wrapN(s.a - Math.round(this.target));
  }

  setIndex(i, silent = false) {
    const prev = this.index;
    this.index = i;
    const lim = this._mode === 'ring' ? 2 : 3;
    for (const s of this.bodies) {
      const k = this.rank(s);
      const on = k !== 0 && Math.abs(k) <= lim;
      if (s.hit) s.hit.tabIndex = on ? 0 : -1;
      if (on) s.el.removeAttribute('aria-hidden'); else s.el.setAttribute('aria-hidden', 'true');
    }
    this.kick();
    if (!silent && prev === i) { this.restartBar(); return; }
    if (!silent) {
      this.closeLb();
      if (this.mobile) this.closeSheet();
    }
    this.style.setProperty('--rw-progress', ((i + 1) / this.n).toFixed(3));
    this.heroes.forEach((h, j) => {
      h.classList.toggle('is-on', j === i);
      h.classList.toggle('was', !silent && j === prev && j !== i);
      h.setAttribute('aria-hidden', j === i ? 'false' : 'true');
      const z = h.querySelector('[data-rw-zoom]');
      if (z) z.tabIndex = j === i ? 0 : -1;
    });
    if (!silent && !this.rm) {
      this.stage.classList.remove('is-sweep');
      void this.stage.offsetWidth;
      this.stage.classList.add('is-sweep');
    }
    if (!silent && this.live) this.live.textContent = this.heroes[i].dataset.label || '';
    this.ticks.forEach((t, j) => {
      t.setAttribute('aria-current', j === i ? 'true' : 'false');
      t.classList.toggle('is-past', j < i);
    });
    this.panels.forEach((p, j) => { p.hidden = j !== i; });
    if (!silent) {
      this.panels.forEach(p => p.classList.remove('is-in'));
      void this.panels[i].offsetWidth;
      this.panels[i].classList.add('is-in');
    }
    const tpl = this.panels[i].querySelector('template[data-rw-pieces-text]');
    if (this.piecesLabel) {
      this.piecesLabel.textContent = tpl ? tpl.content.textContent.trim() : '';
      if (!silent) {
        this.piecesLabel.classList.remove('is-swap');
        void this.piecesLabel.offsetWidth;
        this.piecesLabel.classList.add('is-swap');
      }
    }
    this.clearHot();
    this.restartBar();
  }

  moveTo(T) {
    this.target = T;
    this.setStill(false);
    this.setIndex(((T % this.n) + this.n) % this.n);
  }
  next() { this.moveTo(Math.round(this.target) + 1); }
  prev() { this.moveTo(Math.round(this.target) - 1); }
  go(i) {
    let d = ((i - this.index) % this.n + this.n) % this.n;
    if (d > this.n / 2) d -= this.n;
    this.moveTo(Math.round(this.target) + d);
  }

  /* ---------- autoplay ---------- */
  play(on) {
    this.playing = !!on;
    this.classList.toggle('is-playing', this.playing);
    this.autoBtn?.setAttribute('aria-pressed', this.playing ? 'true' : 'false');
    this.restartBar();
  }
  restartBar() {
    clearTimeout(this.timer);
    this.ticks.forEach(t => t.classList.remove('is-run'));
    if (!this.playing) return;
    const t = this.ticks[this.index];
    if (t) { void t.offsetWidth; t.classList.add('is-run'); }
    this.timer = setTimeout(() => {
      if (this.playing && this.visible && !this.dragging && !document.hidden && !this.panelHover && !this.zoomed && !this.engaged) this.next();
      else this.restartBar();
    }, this.speed);
  }
  engage() { this.engaged = true; if (this.playing) this.play(false); }

  /* ---------- reveal & visibility ---------- */
  reveal() {
    const show = () => {
      if (this.revealed) return;
      this.revealed = true;
      this.classList.add('is-revealed');
      this.kick();
    };
    if (this.rm) { show(); return; }
    this.revealIo = new IntersectionObserver(es => {
      if (es.some(e => e.isIntersecting)) {
        this.revealIo.disconnect();
        requestAnimationFrame(() => requestAnimationFrame(show));
      }
    }, { threshold: 0, rootMargin: '0px 0px -22% 0px' });
    this.revealIo.observe(this);
  }

  /* ---------- feet detection ---------- */
  probeFeet() {
    this.heroes.forEach((hero, i) => {
      const src = hero.dataset.probe;
      if (!src) return;
      const img = new Image();
      img.crossOrigin = 'anonymous';
      img.onload = () => {
        try {
          const w = 48, h = Math.max(1, Math.round(48 * img.naturalHeight / img.naturalWidth));
          const cv = document.createElement('canvas');
          cv.width = w; cv.height = h;
          const ctx = cv.getContext('2d', { willReadFrequently: true });
          ctx.drawImage(img, 0, 0, w, h);
          const data = ctx.getImageData(0, 0, w, h).data;
          let last = -1;
          for (let y = h - 1; y >= 0 && last < 0; y--) {
            for (let x = 0; x < w; x++) if (data[(y * w + x) * 4 + 3] > 40) { last = y; break; }
          }
          if (last < 0) return;
          const foot = clamp((h - 1 - last) / h, 0, 0.4).toFixed(4);
          hero.style.setProperty('--rw-foot', foot);
          this.bodies.forEach(s => { if (s.look === i) s.el.style.setProperty('--rw-foot', foot); });
        } catch {}
      };
      img.src = src;
    });
  }

  /* ---------- events ---------- */
  bind() {
    this._onResize = () => { clearTimeout(this.resizeT); this.resizeT = setTimeout(() => this.measure(), 120); };
    window.addEventListener('resize', this._onResize);
    this.ro = new ResizeObserver(() => this._onResize());
    this.ro.observe(this.stage);
    this._onVis = () => { if (!document.hidden) { this.kick(); this.restartBar(); } };
    document.addEventListener('visibilitychange', this._onVis);
    this.io = new IntersectionObserver(es => {
      this.visible = es.some(e => e.isIntersecting);
      if (this.visible) this.kick();
    }, { threshold: 0 });
    this.io.observe(this);

    const st = this.stage;
    st.addEventListener('pointerdown', e => this.onDown(e));
    st.addEventListener('pointermove', e => this.onMove(e));
    st.addEventListener('pointerup', e => this.onUp(e));
    st.addEventListener('pointercancel', e => this.onUp(e));
    st.addEventListener('click', e => {
      if (performance.now() < this.suppress) { e.stopPropagation(); e.preventDefault(); }
    }, true);
    st.addEventListener('dragstart', e => e.preventDefault());
    st.addEventListener('wheel', e => this.onWheel(e), { passive: false });
    st.addEventListener('keydown', e => {
      if (e.key === 'ArrowRight') { e.preventDefault(); this.next(); }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); this.prev(); }
    });
    this.addEventListener('keydown', e => this.onEsc(e));
    this.addEventListener('click', e => this.onClick(e));
    this.addEventListener('change', e => this.onChange(e));

    const panel = this.panel;
    panel.addEventListener('pointerenter', e => { if (e.pointerType === 'mouse') this.panelHover = true; });
    panel.addEventListener('pointerleave', e => {
      if (e.pointerType === 'mouse') { this.panelHover = false; this.restartBar(); }
    });
    panel.addEventListener('click', e => {
      if (e.target.closest('button, a, input, select, label')) this.engage();
    }, true);
    panel.addEventListener('change', () => this.engage());
    panel.addEventListener('pointerover', e => {
      if (e.pointerType !== 'mouse') return;
      const card = e.target.closest('[data-rw-card]');
      if (card && !card.classList.contains('is-hot')) this.hot(card.dataset.rwCard);
    });
    panel.addEventListener('pointerout', e => {
      if (e.pointerType !== 'mouse') return;
      const card = e.target.closest('[data-rw-card]');
      if (card && !card.contains(e.relatedTarget)) this.clearHot();
    });
  }

  onDown(e) {
    if (this.zoomed) return;
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    const now = performance.now();
    this.p = { id: e.pointerId, type: e.pointerType, x0: e.clientX, y0: e.clientY, t: this.target, drag: false, samples: [{ x: e.clientX, time: now }] };
  }
  onMove(e) {
    const p = this.p;
    if (!p || e.pointerId !== p.id) return;
    if (p.type === 'mouse' && !(e.buttons & 1)) { this.onUp(e); return; }
    const dx = e.clientX - p.x0, dy = e.clientY - p.y0;
    p.samples.push({ x: e.clientX, time: performance.now() });
    if (p.samples.length > 6) p.samples.shift();
    if (!p.drag) {
      if (Math.abs(dx) > 8 && Math.abs(dx) > 1.2 * Math.abs(dy)) {
        p.drag = true;
        this.dragging = true;
        this.classList.add('is-dragging');
        this.cursor?.classList.remove('is-link', 'is-view');
        try { this.stage.setPointerCapture(p.id); } catch {}
      } else if (Math.abs(dy) > 10) { this.p = null; return; }
      else return;
    }
    this.target = p.t - dx / this.unit;
    this.setStill(false);
    this.kick();
  }
  onUp(e) {
    const p = this.p;
    if (!p || e.pointerId !== p.id) return;
    this.p = null;
    if (!p.drag) return;
    try { this.stage.releasePointerCapture(p.id); } catch {}
    this.dragging = false;
    this.classList.remove('is-dragging');
    this.suppress = performance.now() + 60;
    const dx = e.clientX - p.x0;
    const f = p.samples[0], l = p.samples[p.samples.length - 1];
    const vx = l.time > f.time ? (l.x - f.x) / (l.time - f.time) : 0;
    const sign = -1, from = Math.round(p.t);
    if (this.mobile) {
      if (Math.abs(dx) > 30 || Math.abs(vx) > 0.3) this.moveTo(from + sign * (dx > 0 ? 1 : -1));
      else this.moveTo(from);
      return;
    }
    let i = Math.round(this.target + sign * vx * 160 / this.unit);
    if (i === from && Math.abs(vx) > 0.3) i = from + sign * Math.sign(vx);
    i = clamp(i, from - 2, from + 2);
    this.moveTo(i);
  }
  onWheel(e) {
    if (this.zoomed || Math.abs(e.deltaX) <= Math.abs(e.deltaY)) return;
    e.preventDefault();
    const now = performance.now();
    if (now < this.wheelLock) return;
    this.wheelAcc += e.deltaX;
    if (Math.abs(this.wheelAcc) > 45) {
      if (this.wheelAcc > 0) this.next(); else this.prev();
      this.wheelAcc = 0;
      this.wheelLock = now + 520;
    }
  }
  onEsc(e) {
    if (e.key !== 'Escape') return;
    if (this.sheetCard) {
      const btn = this.sheetCard.addBtn;
      this.closeSheet();
      btn?.focus({ preventScroll: true });
      return;
    }
    if (this.zoomed) this.closeLb();
  }

  onClick(e) {
    const t = e.target;
    if (!(t instanceof Element)) return;
    let el;
    if ((el = t.closest('[data-rw-pick-close]'))) {
      const pk = el.closest('[data-rw-picker]');
      const card = pk ? pk.card : this.sheetCard;
      if (card) this.closePicker(card, true);
      return;
    }
    if (t.closest('[data-rw-zoom-close]')) { this.closeLb(); return; }
    if (this.zoomed && t.closest('[data-rw-lb]') && !t.closest('.rw__lb-model') && !t.closest('.rw__lb-top')) { this.closeLb(); return; }
    if (t.closest('[data-rw-zoom]')) { this.openLb(); return; }
    if (t.closest('[data-rw-next]')) { this.next(); return; }
    if (t.closest('[data-rw-prev]')) { this.prev(); return; }
    if ((el = t.closest('[data-rw-tick]'))) { this.go(+el.dataset.rwTick); return; }
    if (t.closest('[data-rw-auto]')) {
      if (!this.playing) this.engaged = false;
      this.play(!this.playing);
      return;
    }
    if ((el = t.closest('[data-rw-pin]'))) { this.engage(); this.hot(el.dataset.rwPin, true); return; }
    if ((el = t.closest('[data-rw-go]'))) {
      const body = this.bodies.find(s => s.el === el.closest('[data-rw-model]'));
      if (!body) return;
      let k = this.rank(body);
      if (this._mode !== 'ring' && k > this.N / 2) k -= this.N;
      if (k !== 0 && Math.abs(k) < 6) this.moveTo(Math.round(this.target) + k);
      else if (k === 0) this.openLb();
      return;
    }
    if ((el = t.closest('[data-rw-confirm]'))) {
      const card = el.closest('[data-rw-picker]')?.card;
      if (card) { card.dataset.touched = '1'; this.confirm(card); }
      return;
    }
    if ((el = t.closest('[data-rw-add]'))) { this.togglePicker(el.closest('[data-rw-card]')); return; }
    if ((el = t.closest('[data-rw-all]'))) { this.addAll(el); return; }
  }

  onChange(e) {
    const inp = e.target;
    if (!(inp instanceof HTMLInputElement) || !inp.matches('[data-rw-option]')) return;
    const card = inp.closest('[data-rw-picker]')?.card;
    if (card) this.updateVariant(card, true);
  }

  /* ---------- hot linking ---------- */
  clearHot() { this.querySelectorAll('.is-hot').forEach(el => el.classList.remove('is-hot')); }
  hot(n, scroll = false) {
    this.clearHot();
    const root = this.zoomed ? this.lbStage : this.heroes[this.index];
    root?.querySelector(`[data-rw-pin="${n}"]`)?.classList.add('is-hot');
    const card = this.panels[this.index].querySelector(`[data-rw-card="${n}"]`);
    if (!card) return;
    card.classList.add('is-hot');
    if (scroll) this.revealCard(card);
  }
  revealCard(card) {
    const behavior = this.rm ? 'auto' : 'smooth';
    const list = card.closest('.rw__items');
    if (!list) return;
    const cr = card.getBoundingClientRect(), lr = list.getBoundingClientRect();
    if (list.scrollWidth > list.clientWidth + 1) {
      list.scrollTo({ left: list.scrollLeft + cr.left - lr.left - 20, behavior });
    } else if (list.scrollHeight > list.clientHeight + 1) {
      list.scrollTo({ top: list.scrollTop + cr.top - lr.top - 12, behavior });
    } else if (cr.top < 0 || cr.bottom > window.innerHeight - 140) {
      window.scrollBy({ top: cr.top - 0.3 * window.innerHeight, behavior });
    }
  }

  /* ---------- pickers ---------- */
  updateVariant(card, touched) {
    const pk = card.picker;
    const radios = [...pk.querySelectorAll('[data-rw-option]')];
    const groups = {};
    radios.forEach(r => { (groups[r.dataset.rwOption] ||= []).push(r); });
    const keys = Object.keys(groups).sort();
    const sel = keys.map(k => (groups[k].find(r => r.checked) || {}).value);
    const vs = card._variants || [];
    const match = vs.find(v => v.o.every((o, i) => o === sel[i]));
    keys.forEach((k, oi) => groups[k].forEach(r => {
      const ok = vs.some(v => v.a && v.o[oi] === r.value && v.o.every((o, j) => j === oi || o === sel[j]));
      r.closest('.rw__pill')?.classList.toggle('is-unavailable', !ok);
    }));
    const btn = pk.querySelector('[data-rw-confirm]');
    const lab = pk.querySelector('[data-rw-confirm-label]');
    const avail = !!(match && match.a);
    if (btn) btn.disabled = !avail;
    if (lab) lab.textContent = avail ? lab.dataset.add : this.msgSoldout;
    card.dataset.selected = avail ? String(match.id) : '';
    if (touched) card.dataset.touched = '1';
  }

  togglePicker(card) {
    if (!card || card.classList.contains('is-added') || card.classList.contains('is-loading') || card.classList.contains('is-soldout')) return;
    if (card.dataset.variantId) { this.addCards([card]); return; }
    if (card.classList.contains('is-picking')) { this.closePicker(card); return; }
    this.openPicker(card, true);
  }

  openPicker(card, focus) {
    if (!card.picker || card.classList.contains('is-added')) return;
    if (this.mobile) { this.openSheet(card, focus); return; }
    card.picker.hidden = false;
    card.classList.add('is-picking');
    card.addBtn?.setAttribute('aria-expanded', 'true');
    if (focus) {
      card.picker.querySelector('[data-rw-option]:checked')?.focus({ preventScroll: true });
      this.revealCard(card);
    }
  }

  closePicker(card, focusBack = false) {
    if (this.sheetCard === card) { this.closeSheet(); if (focusBack) card.addBtn?.focus({ preventScroll: true }); return; }
    if (card.picker) card.picker.hidden = true;
    card.classList.remove('is-picking');
    if (!card.classList.contains('is-added')) card.addBtn?.setAttribute('aria-expanded', 'false');
  }

  ensureHost() {
    if (this.host) return this.host;
    const host = document.createElement('div');
    host.className = 'rw-sheet-host';
    const scrim = document.createElement('button');
    scrim.type = 'button';
    scrim.className = 'rw__pick-scrim';
    scrim.setAttribute('data-rw-pick-close', '');
    scrim.tabIndex = -1;
    scrim.setAttribute('aria-hidden', 'true');
    host.append(scrim);
    host.addEventListener('click', e => this.onClick(e));
    host.addEventListener('change', e => { this.engage(); this.onChange(e); });
    host.addEventListener('keydown', e => this.onEsc(e));
    this.host = host;
    return host;
  }

  openSheet(card, focus) {
    this.closeSheet();
    const host = this.ensureHost();
    const cs = getComputedStyle(this);
    ['--rw-panel', '--rw-text', '--rw-muted', '--rw-line', '--rw-accent', '--rw-on-accent', '--rw-btn-bg', '--rw-btn-fg', '--rw-btn-radius',
      '--rw-pill-radius', '--rw-bar-r', '--rw-thumb-radius', '--rw-pt-size', '--rw-price', '--rw-opt', '--rw-ease', '--rw-ease-sheet', '--rw-ease-spring']
      .forEach(v => host.style.setProperty(v, cs.getPropertyValue(v)));
    host.style.fontFamily = cs.fontFamily;
    host.style.color = cs.color;
    const pk = card.picker;
    this.sheetMark = document.createComment('rw-picker');
    pk.before(this.sheetMark);
    host.append(pk);
    host.classList.remove('is-open');
    document.body.append(host);
    pk.hidden = false;
    this.sheetCard = card;
    card.classList.add('is-picking');
    card.addBtn?.setAttribute('aria-expanded', 'true');
    this.classList.add('rw--picking');
    requestAnimationFrame(() => host.classList.add('is-open'));
    if (focus) pk.querySelector('[data-rw-option]:checked')?.focus({ preventScroll: true });
  }

  closeSheet() {
    const card = this.sheetCard;
    if (!card) return;
    const pk = card.picker;
    pk.hidden = true;
    if (this.sheetMark) { this.sheetMark.replaceWith(pk); this.sheetMark = null; }
    card.classList.remove('is-picking');
    if (!card.classList.contains('is-added')) card.addBtn?.setAttribute('aria-expanded', 'false');
    this.host?.classList.remove('is-open');
    this.host?.remove();
    this.sheetCard = null;
    this.classList.remove('rw--picking');
  }

  /* ---------- adding ---------- */
  panelOf(card) { return card.closest('[data-rw-panel]'); }
  setMsg(panel, text) {
    const m = panel.querySelector('[data-rw-msg]');
    if (!m) return;
    m.textContent = text || '';
    m.classList.remove('is-on');
    if (text) { void m.offsetWidth; m.classList.add('is-on'); }
  }

  confirm(card) {
    if (!card.dataset.selected || card.classList.contains('is-added')) return;
    this.addCards([card]);
  }

  async addCards(cards) {
    if (!cards.length) return false;
    const panel = this.panelOf(cards[0]);
    cards.forEach(c => c.classList.add('is-loading'));
    let res;
    try {
      res = await addToCart(cards.map(c => String(c.dataset.variantId || c.dataset.selected)));
    } catch (err) {
      res = { added: [], error: (err && err.message) || this.msgError };
    }
    if (res.unhandled) res.error = this.msgError;
    const added = new Set(res.added || []);
    cards.forEach(c => {
      if (added.has(String(c.dataset.variantId || c.dataset.selected))) this.markAdded(c);
      else c.classList.remove('is-loading');
    });
    if (res.error) this.setMsg(panel, res.error);
    else this.checkComplete(panel);
    return !res.error;
  }

  markAdded(card) {
    card.classList.remove('is-loading');
    card.classList.add('is-added');
    this.closePicker(card);
    if (card.addBtn) {
      card.addBtn.setAttribute('aria-label', card.addBtn.dataset.addedLabel || 'Added to bag');
      card.addBtn.removeAttribute('aria-expanded');
    }
    if (this.mobile && !this.rm && navigator.vibrate) { try { navigator.vibrate(12); } catch {} }
  }

  checkComplete(panel) {
    const cards = [...panel.querySelectorAll('[data-rw-card]')].filter(c => !c.classList.contains('is-soldout'));
    if (cards.length >= 1 && cards.every(c => c.classList.contains('is-added'))) {
      panel.classList.add('is-complete');
      this.setMsg(panel, '');
    }
  }

  async addAll(btn) {
    const panel = btn.closest('[data-rw-panel]');
    if (!panel || panel.classList.contains('is-complete') || btn.classList.contains('is-loading')) return;
    this.setMsg(panel, '');
    const cards = [...panel.querySelectorAll('[data-rw-card]')].filter(c => !c.classList.contains('is-added') && !c.classList.contains('is-soldout'));
    const ready = cards.filter(c => c.dataset.variantId || (c.dataset.touched && c.dataset.selected));
    const pending = cards.filter(c => !ready.includes(c));
    if (ready.length) {
      btn.classList.add('is-loading');
      await this.addCards(ready);
      btn.classList.remove('is-loading');
    }
    if (pending.length) {
      const list = this.mobile ? pending.slice(0, 1) : pending;
      list.forEach((c, i) => this.openPicker(c, i === 0));
      if (!this.mobile) this.revealCard(pending[0]);
      this.setMsg(panel, this.msgChoose.replace('[items]', pending.map(c => c.dataset.title).join(', ')));
    }
  }

  /* ---------- popup ---------- */
  openLb() {
    if (this.zoomed || !this.lb) return;
    this.engage();
    this.clearHot();
    clearTimeout(this.lbT);
    const hero = this.heroes[this.index];
    const srcFig = hero.querySelector('.rw__figure');
    const wrap = document.createElement('div');
    wrap.className = 'rw__lb-model';
    const sh = hero.querySelector('.rw__shadow');
    if (sh) wrap.append(sh.cloneNode(true));
    const fig = srcFig.cloneNode(true);
    fig.querySelector('[data-rw-zoom]')?.remove();
    fig.querySelectorAll('.rw__pin').forEach(p => { p.tabIndex = 0; });
    const foot = hero.style.getPropertyValue('--rw-foot');
    if (foot) wrap.style.setProperty('--rw-foot', foot);
    wrap.append(fig);
    this.lbStage.textContent = '';
    this.lbStage.append(wrap);
    const kick = this.lb.querySelector('[data-rw-lb-kicker]');
    const name = this.lb.querySelector('[data-rw-lb-name]');
    if (kick) kick.textContent = `${this.lb.dataset.word || 'Look'} ${String(this.index + 1).padStart(2, '0')}`;
    if (name) name.textContent = hero.dataset.name || '';
    const sr = this.lbStage.getBoundingClientRect();
    const h = Math.max(160, Math.min(sr.height, sr.width / 0.5625));
    wrap.style.setProperty('--rw-model-h', `${Math.round(h)}px`);
    fig.querySelectorAll('img').forEach(img => {
      img.loading = 'eager';
      img.sizes = `${Math.round(h * 0.5625)}px`;
      img.classList.add('is-decoded');
    });
    // source rect: hero (if visible) or front body
    const a = this.frontFigRect();
    this.zoomed = true;
    this.classList.add('rw--zoom');
    this.lb.setAttribute('aria-hidden', 'false');
    if (!this.rm && a && a.height) {
      const b = fig.getBoundingClientRect();
      wrap.style.transition = 'none';
      wrap.style.transformOrigin = '0 100%';
      wrap.style.transform = `translate3d(${a.left - b.left}px,${a.bottom - b.bottom}px,0) scale(${a.height / b.height})`;
      void wrap.offsetWidth;
      wrap.style.transition = '';
      wrap.style.transform = '';
    }
    this.lb.querySelector('[data-rw-zoom-close]')?.focus({ preventScroll: true });
  }

  frontFigRect() {
    const hero = this.heroes[this.index];
    if (this.still) return hero.querySelector('.rw__figure').getBoundingClientRect();
    let best = null;
    for (const s of this.bodies) {
      if (s.look !== this.index) continue;
      const r = s.el.querySelector('.rw__figure').getBoundingClientRect();
      if (!best || r.height > best.height) best = r;
    }
    return best;
  }

  closeLb() {
    if (!this.zoomed) return;
    this.zoomed = false;
    const wrap = this.lbStage.querySelector('.rw__lb-model');
    const fig = wrap?.querySelector('.rw__figure');
    if (wrap && fig && !this.rm) {
      const a = this.frontFigRect();
      const cur = wrap.style.transform;
      wrap.style.transform = '';
      const b = fig.getBoundingClientRect();
      wrap.style.transform = cur;
      if (a && a.height && b.height) {
        wrap.style.transformOrigin = '0 100%';
        wrap.style.transform = `translate3d(${a.left - b.left}px,${a.bottom - b.bottom}px,0) scale(${a.height / b.height})`;
      }
    }
    this.classList.remove('rw--zoom');
    this.lb.setAttribute('aria-hidden', 'true');
    this.clearHot();
    const hadFocus = this.lb.contains(document.activeElement);
    this.lbT = setTimeout(() => { if (!this.zoomed) this.lbStage.textContent = ''; }, 950);
    if (hadFocus) this.stage.focus({ preventScroll: true });
    this.restartBar();
  }

  /* ---------- cursor ---------- */
  setupCursor() {
    const c = this.cursor;
    if (!c) return;
    if (!window.matchMedia('(hover: hover) and (pointer: fine)').matches) { c.remove(); this.cursor = null; return; }
    this.classList.add('rw--cursor');
    let x = 0, y = 0, tx = 0, ty = 0, first = true;
    const k = this.rm ? 1 : 0.18;
    const tickC = () => {
      x += (tx - x) * k; y += (ty - y) * k;
      if (Math.hypot(tx - x, ty - y) < 0.2) { x = tx; y = ty; }
      c.style.transform = `translate3d(${x}px,${y}px,0)`;
      this.curRaf = (x !== tx || y !== ty) ? requestAnimationFrame(tickC) : 0;
    };
    this.stage.addEventListener('pointermove', e => {
      if (e.pointerType !== 'mouse') return;
      const r = this.stage.getBoundingClientRect();
      tx = e.clientX - r.left; ty = e.clientY - r.top;
      if (first) { x = tx; y = ty; first = false; c.style.transform = `translate3d(${x}px,${y}px,0)`; }
      c.classList.add('is-on');
      const t = e.target instanceof Element ? e.target : null;
      const view = !this.dragging && !!t?.closest('.rw__zoom') && this.still;
      const link = !this.dragging && !!t?.closest('.rw__pin, .rw__hit');
      c.classList.toggle('is-view', view);
      c.classList.toggle('is-link', link && !view);
      if (!this.curRaf) this.curRaf = requestAnimationFrame(tickC);
    });
    this.stage.addEventListener('pointerleave', () => {
      c.classList.remove('is-on', 'is-link', 'is-view');
      first = true;
    });
  }
}

if (!customElements.get('runway-section')) customElements.define('runway-section', RunwaySection);
})();
export {};
