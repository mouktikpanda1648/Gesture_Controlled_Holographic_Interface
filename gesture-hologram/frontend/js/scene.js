/**
 * The holographic interface itself, drawn on a 1000×1000 logical canvas.
 * Pure rendering: feed it backend state via update(), draw it with draw().
 */
const TAU = Math.PI * 2;
const COLORS = {
  cyan: '77,232,255',
  warm: '255,205,110',
  red: '255,90,110',
  slate: '120,150,170',
};
const rgba = (c, a) => `rgba(${COLORS[c] ?? c},${a})`;
const ease = (dt, rate) => 1 - Math.exp(-dt * rate);

const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

export class Scene {
  glow = 0;       // 0 = LED off, 1 = LED on (smoothed)
  focus = 0;      // LIGHT highlight amount (smoothed)
  presence = 0;   // hand-in-view amount (smoothed)
  progress = 0;
  gesture = 'NONE';
  led = 'unknown';
  linkOk = false;
  online = false;
  focused = false;
  t = 0;

  update(dt, state, online) {
    this.t += reducedMotion ? 0 : dt;
    this.online = online;
    if (state) {
      this.led = state.link.led;
      this.linkOk = state.link.status === 'connected';
      this.gesture = state.hand.gesture;
      this.progress = state.hand.progress;
      this.focused = state.ui.focus === 'LIGHT';
      this.hand = state.hand.present;
    }
    const k = ease(dt, 7);
    this.glow += ((this.led === 'on' ? 1 : 0) - this.glow) * k;
    this.focus += ((this.focused ? 1 : 0) - this.focus) * k;
    this.presence += ((this.hand ? 1 : 0) - this.presence) * ease(dt, 4);
  }

  /** The accent colour follows the LED: cyan idle, warm when lit, red on faults. */
  get accent() {
    if (!this.online || (!this.linkOk && this.led !== 'on')) return 'red';
    return this.glow > 0.5 ? 'warm' : 'cyan';
  }

  hint() {
    if (!this.online) return 'BACKEND OFFLINE · RECONNECTING';
    if (!this.linkOk) return 'CONTROLLER NOT CONNECTED';
    if (!this.hand) return 'SHOW YOUR HAND TO THE CAMERA';
    if (this.led === 'on') return 'OPEN PALM TO TURN OFF';
    return this.focused ? 'THUMBS UP TO TURN ON' : 'POINT TO SELECT LIGHT';
  }

  /**
   * @param {{compact?: boolean}} opts  compact = pyramid layout: no outer rings or
   * title, and nothing in the strip nearest the pyramid, so the four reflected
   * copies never overlap each other.
   */
  draw(ctx, size, { compact = false } = {}) {
    ctx.save();
    ctx.translate(size / 2, size / 2);
    ctx.scale(size / 1000, size / 1000);
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';

    const acc = this.accent;
    this.#backdrop(ctx, acc);
    ctx.save();
    if (compact) ctx.scale(0.76, 0.76);
    this.#rings(ctx, acc);
    ctx.restore();
    if (!compact) this.#title(ctx, acc);
    this.#sideNode(ctx, -285, 105, 'FAN', 'fan');
    this.#sideNode(ctx, 285, 105, 'TEMP', 'temp');
    this.#reactor(ctx, acc);
    this.#footer(ctx, acc, compact);
    ctx.restore();
  }

  // ---- layers ---------------------------------------------------------------
  #backdrop(ctx, acc) {
    const g = ctx.createRadialGradient(0, -30, 0, 0, -30, 500);
    g.addColorStop(0, rgba(acc, 0.10 + 0.22 * this.glow));
    g.addColorStop(0.55, rgba(acc, 0.04 + 0.05 * this.glow));
    g.addColorStop(1, rgba(acc, 0));
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.arc(0, 0, 500, 0, TAU); ctx.fill();
  }

  #rings(ctx, acc) {
    const t = this.t;
    ctx.strokeStyle = rgba(acc, 0.28);
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(0, 0, 478, 0, TAU); ctx.stroke();

    ctx.save();
    ctx.rotate(t * 0.04);
    const n = 144;
    for (let i = 0; i < n; i++) {
      const a = (i / n) * TAU, major = i % 6 === 0;
      const r1 = major ? 446 : 458, r2 = 472;
      ctx.strokeStyle = rgba(acc, major ? 0.55 : 0.22);
      ctx.lineWidth = major ? 3 : 2;
      ctx.beginPath();
      ctx.moveTo(Math.cos(a) * r1, Math.sin(a) * r1);
      ctx.lineTo(Math.cos(a) * r2, Math.sin(a) * r2);
      ctx.stroke();
    }
    ctx.restore();

    ctx.save();
    ctx.rotate(-t * 0.12);
    ctx.strokeStyle = rgba(acc, 0.5);
    ctx.lineWidth = 6;
    for (let i = 0; i < 3; i++) {
      const a = (i / 3) * TAU;
      ctx.beginPath(); ctx.arc(0, 0, 420, a, a + 0.9); ctx.stroke();
    }
    ctx.strokeStyle = rgba(acc, 0.16);
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(0, 0, 420, 0, TAU); ctx.stroke();
    ctx.restore();
  }

  #text(ctx, str, x, y, { size, weight = 600, spacing = 0, color, alpha = 1, align = 'center' }) {
    ctx.font = `${weight} ${size}px system-ui, "Segoe UI", Roboto, sans-serif`;
    ctx.textAlign = align;
    ctx.textBaseline = 'middle';
    if ('letterSpacing' in ctx) ctx.letterSpacing = `${spacing}px`;
    ctx.fillStyle = rgba(color, alpha);
    // letter-spacing adds trailing space; nudge to keep the text optically centred
    ctx.fillText(str, x + (align === 'center' ? spacing / 2 : 0), y);
    if ('letterSpacing' in ctx) ctx.letterSpacing = '0px';
  }

  #title(ctx, acc) {
    this.#text(ctx, 'HOLO · LINK', 0, -360, { size: 30, weight: 700, spacing: 16, color: acc, alpha: 0.95 });
    this.#text(ctx, 'GESTURE CONTROL INTERFACE', 0, -322, { size: 15, spacing: 7, color: acc, alpha: 0.55 });
  }

  #sideNode(ctx, x, y, label, icon) {
    ctx.save();
    ctx.translate(x, y);
    ctx.scale(0.85, 0.85);
    ctx.strokeStyle = rgba('slate', 0.45);
    ctx.lineWidth = 3;
    ctx.setLineDash([5, 9]);
    ctx.beginPath(); ctx.arc(0, 0, 66, 0, TAU); ctx.stroke();
    ctx.setLineDash([]);

    ctx.strokeStyle = rgba('slate', 0.7);
    ctx.lineWidth = 4;
    if (icon === 'fan') {
      for (let i = 0; i < 3; i++) {
        ctx.save();
        ctx.rotate((i / 3) * TAU);
        ctx.beginPath();
        ctx.moveTo(0, 0);
        ctx.bezierCurveTo(22, -14, 24, -46, 0, -44);
        ctx.bezierCurveTo(-8, -30, -6, -12, 0, 0);
        ctx.stroke();
        ctx.restore();
      }
      ctx.beginPath(); ctx.arc(0, 0, 5, 0, TAU); ctx.stroke();
    } else {
      ctx.beginPath();
      ctx.moveTo(-8, 26); ctx.lineTo(-8, -30);
      ctx.arc(0, -30, 8, Math.PI, 0);
      ctx.lineTo(8, 26);
      ctx.stroke();
      ctx.beginPath(); ctx.arc(0, 32, 16, 0, TAU); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(0, 20); ctx.lineTo(0, -12); ctx.stroke();
    }
    ctx.restore();
    this.#text(ctx, label, x, y + 94, { size: 24, spacing: 8, color: 'slate', alpha: 0.9 });
    this.#text(ctx, 'NOT INSTALLED', x, y + 124, { size: 12, spacing: 2, color: 'slate', alpha: 0.6 });
  }

  #reactor(ctx, acc) {
    const cy = -30;
    const pulse = reducedMotion ? 0 : Math.sin(this.t * 3) * 0.5 + 0.5;
    ctx.save();
    ctx.translate(0, cy);

    // soft halo
    const halo = ctx.createRadialGradient(0, 0, 40, 0, 0, 260);
    halo.addColorStop(0, rgba('warm', 0.55 * this.glow));
    halo.addColorStop(1, rgba('warm', 0));
    ctx.fillStyle = halo;
    ctx.beginPath(); ctx.arc(0, 0, 260, 0, TAU); ctx.fill();

    // disc
    const disc = ctx.createRadialGradient(0, -30, 10, 0, 0, 150);
    disc.addColorStop(0, rgba(acc, 0.18 + 0.2 * this.glow));
    disc.addColorStop(1, rgba(acc, 0.04));
    ctx.fillStyle = disc;
    ctx.beginPath(); ctx.arc(0, 0, 150, 0, TAU); ctx.fill();
    ctx.strokeStyle = rgba(acc, 0.7);
    ctx.lineWidth = 3;
    ctx.beginPath(); ctx.arc(0, 0, 150, 0, TAU); ctx.stroke();

    // outer track + hold-progress arc
    ctx.strokeStyle = rgba(acc, 0.22);
    ctx.lineWidth = 8;
    ctx.beginPath(); ctx.arc(0, 0, 178, 0, TAU); ctx.stroke();
    const holding = this.gesture === 'THUMBS_UP' || this.gesture === 'OPEN_PALM';
    if (holding && this.progress > 0 && this.progress < 1) {
      ctx.strokeStyle = rgba(this.gesture === 'THUMBS_UP' ? 'warm' : 'cyan', 0.95);
      ctx.lineWidth = 10;
      ctx.beginPath();
      ctx.arc(0, 0, 178, -Math.PI / 2, -Math.PI / 2 + TAU * this.progress);
      ctx.stroke();
    }

    // focus brackets
    if (this.focus > 0.01) {
      const d = 214 + (1 - this.focus) * 24 + pulse * 4, len = 52;
      ctx.strokeStyle = rgba(acc, 0.35 + 0.65 * this.focus);
      ctx.lineWidth = 6;
      for (const [sx, sy] of [[-1, -1], [1, -1], [1, 1], [-1, 1]]) {
        ctx.beginPath();
        ctx.moveTo(sx * d, sy * (d - len));
        ctx.lineTo(sx * d, sy * d);
        ctx.lineTo(sx * (d - len), sy * d);
        ctx.stroke();
      }
    }

    this.#bulb(ctx, acc);
    ctx.restore();

    this.#text(ctx, 'LIGHT', 0, 218, {
      size: 46, weight: 700, spacing: 20, color: acc, alpha: 0.7 + 0.3 * Math.max(this.focus, this.glow),
    });
    const state = this.led === 'on' ? 'ON' : this.led === 'off' ? 'OFF' : '—';
    this.#text(ctx, state, 0, 268, {
      size: 28, weight: 700, spacing: 10, color: this.glow > 0.5 ? 'warm' : 'cyan', alpha: 0.95,
    });
  }

  #bulb(ctx, acc) {
    const g = this.glow;
    ctx.save();
    ctx.translate(0, -6);

    if (g > 0.02) {                                     // rays
      ctx.save();
      ctx.rotate(this.t * 0.2);
      ctx.strokeStyle = rgba('warm', 0.85 * g);
      ctx.lineWidth = 5;
      for (let i = 0; i < 12; i++) {
        const a = (i / 12) * TAU, r1 = 92 + 8 * (1 - g), r2 = r1 + 22 * g;
        ctx.beginPath();
        ctx.moveTo(Math.cos(a) * r1, Math.sin(a) * r1);
        ctx.lineTo(Math.cos(a) * r2, Math.sin(a) * r2);
        ctx.stroke();
      }
      ctx.restore();
    }

    const path = new Path2D();                         // bulb silhouette
    path.moveTo(-26, 44);
    path.bezierCurveTo(-26, 26, -62, 14, -62, -22);
    path.arc(0, -22, 62, Math.PI, 0);
    path.bezierCurveTo(62, 14, 26, 26, 26, 44);
    path.closePath();

    if (g > 0.01) {
      const fill = ctx.createRadialGradient(0, -22, 4, 0, -22, 70);
      fill.addColorStop(0, `rgba(255,250,225,${g})`);
      fill.addColorStop(1, `rgba(255,205,110,${0.85 * g})`);
      ctx.fillStyle = fill;
      ctx.shadowColor = rgba('warm', 0.9);
      ctx.shadowBlur = 40 * g;
      ctx.fill(path);
      ctx.shadowBlur = 0;
    }
    ctx.strokeStyle = rgba(this.glow > 0.5 ? 'warm' : acc, 0.95);
    ctx.lineWidth = 6;
    ctx.stroke(path);

    ctx.lineWidth = 5;                                  // filament + screw base
    ctx.strokeStyle = rgba(this.glow > 0.5 ? 'warm' : acc, 0.8);
    ctx.beginPath();
    ctx.moveTo(-10, 44); ctx.lineTo(-10, 8); ctx.quadraticCurveTo(0, -12, 10, 8); ctx.lineTo(10, 44);
    ctx.stroke();
    for (const y of [58, 74]) {
      ctx.beginPath(); ctx.moveTo(-24, y); ctx.lineTo(24, y); ctx.stroke();
    }
    ctx.restore();
  }

  #footer(ctx, acc, compact) {
    this.#text(ctx, this.hint(), 0, compact ? 335 : 338, {
      size: 18, weight: 600, spacing: 5, color: this.online && this.linkOk ? acc : 'red', alpha: 0.85,
    });
  }
}
