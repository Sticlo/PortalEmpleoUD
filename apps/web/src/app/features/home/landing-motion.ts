/**
 * Motor de movimiento del inicio. Reglas para sostener 60 FPS:
 * - Un solo listener de scroll (passive) y un solo requestAnimationFrame que
 *   solo corre mientras haya algo que mover.
 * - Las posiciones se miden al cargar y al redimensionar, nunca dentro del frame.
 * - Solo se escriben transform, opacity y variables CSS (sin layout).
 */

interface ParallaxItem {
  el: HTMLElement;
  host: HTMLElement;
  speed: number;
  mid: number;
  last: number;
}

interface RevealItem {
  el: HTMLElement;
  top: number;
  height: number;
  last: number;
}

interface PointerItem {
  el: HTMLElement;
  depth: number;
}

interface TiltItem {
  el: HTMLElement;
  rect: DOMRect | null;
  rx: number;
  ry: number;
  trx: number;
  try: number;
  active: boolean;
}

const clamp = (v: number, min: number, max: number) => Math.min(max, Math.max(min, v));

export function startLandingMotion(root: HTMLElement): () => void {
  const win = window;
  const reduced = win.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const finePointer = win.matchMedia('(hover: hover) and (pointer: fine)').matches;
  const cleanups: Array<() => void> = [];

  const listen = (
    target: EventTarget,
    type: string,
    fn: (e: Event) => void,
    opts: AddEventListenerOptions = { passive: true },
  ) => {
    target.addEventListener(type, fn, opts);
    cleanups.push(() => target.removeEventListener(type, fn, opts));
  };

  let frame = 0;
  let scrollDirty = true;
  const request = () => {
    if (!frame) frame = win.requestAnimationFrame(tick);
  };

  // ── Ambient shift + navegación flotante ──
  const sections = Array.from(root.querySelectorAll<HTMLElement>('[data-ambient]'));
  const navLinks = Array.from(root.querySelectorAll<HTMLElement>('[data-nav]'));
  const visible = new Set<Element>();

  const ambientIo = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const sec = entry.target as HTMLElement;
        root.dataset['ambient'] = sec.dataset['ambient'] ?? '';
        for (const link of navLinks) link.classList.toggle('is-active', link.dataset['nav'] === sec.id);
      }
    },
    { rootMargin: '-50% 0px -50% 0px' },
  );

  const visibilityIo = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) visible.add(entry.target);
        else visible.delete(entry.target);
      }
      scrollDirty = true;
      request();
    },
    { rootMargin: '25% 0px' },
  );

  for (const sec of sections) {
    ambientIo.observe(sec);
    visibilityIo.observe(sec);
  }

  const hero = root.querySelector<HTMLElement>('[data-hero]');
  const navIo = new IntersectionObserver(
    ([entry]) => root.classList.toggle('lp-nav-on', entry.intersectionRatio < 0.3),
    { threshold: [0, 0.3, 1] },
  );
  if (hero) navIo.observe(hero);

  // ── Parallax por capas + revelado de texto ──
  const parallax: ParallaxItem[] = reduced
    ? []
    : Array.from(root.querySelectorAll<HTMLElement>('[data-speed]')).map((el) => ({
        el,
        host: el.closest<HTMLElement>('[data-ambient]') ?? root,
        speed: Number(el.dataset['speed'] ?? 1),
        mid: 0,
        last: Number.NaN,
      }));

  const reveals: RevealItem[] = Array.from(root.querySelectorAll<HTMLElement>('[data-reveal]')).map(
    (el) => ({ el, top: 0, height: 0, last: -1 }),
  );

  let vw = win.innerWidth;
  let vh = win.innerHeight;
  let amplitude = vw < 720 ? 0.55 : 1;

  const measure = () => {
    vw = win.innerWidth;
    vh = win.innerHeight;
    amplitude = vw < 720 ? 0.55 : 1;
    const y = win.scrollY;
    for (const item of parallax) {
      const r = item.host.getBoundingClientRect();
      item.mid = r.top + y + r.height / 2;
    }
    for (const item of reveals) {
      const r = item.el.getBoundingClientRect();
      item.top = r.top + y;
      item.height = r.height;
    }
    scrollDirty = true;
    request();
  };

  // ── Orbes que siguen al mouse (solo en el hero, solo con mouse) ──
  const pointerItems: PointerItem[] =
    finePointer && !reduced
      ? Array.from(root.querySelectorAll<HTMLElement>('[data-pointer]')).map((el) => ({
          el,
          depth: Number(el.dataset['pointer'] ?? 20),
        }))
      : [];
  let tx = 0;
  let ty = 0;
  let mx = 0;
  let my = 0;

  // ── Tarjetas con tilt 3D ──
  const tilts: TiltItem[] =
    finePointer && !reduced
      ? Array.from(root.querySelectorAll<HTMLElement>('[data-tilt]')).map((el) => ({
          el,
          rect: null,
          rx: 0,
          ry: 0,
          trx: 0,
          try: 0,
          active: false,
        }))
      : [];

  function tick() {
    frame = 0;
    let again = false;

    if (scrollDirty) {
      scrollDirty = false;
      const y = win.scrollY;
      const center = y + vh / 2;

      for (const item of parallax) {
        if (!visible.has(item.host)) continue;
        const t = (center - item.mid) * (1 - item.speed) * amplitude;
        if (Math.abs(t - item.last) < 0.15) continue;
        item.last = t;
        item.el.style.transform = `translate3d(0, ${t.toFixed(2)}px, 0)`;
      }

      for (const item of reveals) {
        const p = reduced ? 1 : clamp((y + vh * 0.82 - item.top) / (item.height + vh * 0.3), 0, 1);
        const v = Math.round(p * 500) / 500;
        if (v === item.last) continue;
        item.last = v;
        item.el.style.setProperty('--reveal', String(v));
      }
    }

    if (pointerItems.length) {
      mx += (tx - mx) * 0.075;
      my += (ty - my) * 0.075;
      if (Math.abs(tx - mx) > 0.0008 || Math.abs(ty - my) > 0.0008) again = true;
      for (const item of pointerItems) {
        item.el.style.transform = `translate3d(${(mx * item.depth).toFixed(2)}px, ${(my * item.depth).toFixed(2)}px, 0)`;
      }
    }

    for (const card of tilts) {
      if (!card.active && Math.abs(card.rx) < 0.01 && Math.abs(card.ry) < 0.01) continue;
      card.rx += (card.trx - card.rx) * 0.14;
      card.ry += (card.try - card.ry) * 0.14;
      const settled = Math.abs(card.trx - card.rx) < 0.01 && Math.abs(card.try - card.ry) < 0.01;
      if (!settled) again = true;
      if (!card.active && settled) {
        card.rx = 0;
        card.ry = 0;
        card.el.style.transform = '';
        continue;
      }
      card.el.style.transform = `perspective(1000px) rotateX(${card.rx.toFixed(2)}deg) rotateY(${card.ry.toFixed(2)}deg)`;
    }

    if (again) request();
  }

  listen(win, 'scroll', () => {
    scrollDirty = true;
    request();
  });

  let resizeFrame = 0;
  listen(win, 'resize', () => {
    const widthChanged = win.innerWidth !== vw;
    const heightJump = Math.abs(win.innerHeight - vh) > 120;
    if (!widthChanged && !heightJump) return;
    cancelAnimationFrame(resizeFrame);
    resizeFrame = win.requestAnimationFrame(measure);
  });

  const ro = new ResizeObserver(() => {
    cancelAnimationFrame(resizeFrame);
    resizeFrame = win.requestAnimationFrame(measure);
  });
  ro.observe(root);

  if (pointerItems.length && hero) {
    listen(win, 'pointermove', (e) => {
      if (!visible.has(hero.closest('[data-ambient]') ?? hero)) return;
      const ev = e as PointerEvent;
      tx = (ev.clientX / vw - 0.5) * 2;
      ty = (ev.clientY / vh - 0.5) * 2;
      request();
    });
  }

  for (const card of tilts) {
    listen(card.el, 'pointerenter', () => {
      card.rect = card.el.getBoundingClientRect();
      card.active = true;
      card.el.classList.add('is-hover');
    });
    listen(card.el, 'pointermove', (e) => {
      const r = card.rect;
      if (!r) return;
      const ev = e as PointerEvent;
      const px = (ev.clientX - r.left) / r.width;
      const py = (ev.clientY - r.top) / r.height;
      card.trx = (0.5 - py) * 7;
      card.try = (px - 0.5) * 9;
      card.el.style.setProperty('--gx', `${(px * 100).toFixed(1)}%`);
      card.el.style.setProperty('--gy', `${(py * 100).toFixed(1)}%`);
      request();
    });
    listen(card.el, 'pointerleave', () => {
      card.active = false;
      card.trx = 0;
      card.try = 0;
      card.rect = null;
      card.el.classList.remove('is-hover');
      request();
    });
  }

  // ── Botones con resplandor que sigue al cursor ──
  if (finePointer) {
    for (const btn of Array.from(root.querySelectorAll<HTMLElement>('[data-glow]'))) {
      listen(btn, 'pointermove', (e) => {
        const ev = e as PointerEvent;
        const r = btn.getBoundingClientRect();
        btn.style.setProperty('--mx', `${(ev.clientX - r.left).toFixed(0)}px`);
        btn.style.setProperty('--my', `${(ev.clientY - r.top).toFixed(0)}px`);
      });
    }
  }

  measure();
  document.fonts?.ready.then(measure).catch(() => undefined);
  root.classList.add('lp-ready');

  return () => {
    cancelAnimationFrame(frame);
    cancelAnimationFrame(resizeFrame);
    ambientIo.disconnect();
    visibilityIo.disconnect();
    navIo.disconnect();
    ro.disconnect();
    for (const fn of cleanups) fn();
  };
}
