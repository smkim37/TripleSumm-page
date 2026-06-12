/* DemoPlayer — video synced with GT/pred score curves, summary bands,
 * and per-frame modality attention. No dependencies. */
'use strict';

class DemoPlayer {
  constructor(root) {
    this.root = root;
    this.video = root.querySelector('#video');
    this.canvas = root.querySelector('#chartCanvas');
    this.ctx = this.canvas.getContext('2d');
    this.titleEl = root.querySelector('#playerTitle');
    this.metaEl = root.querySelector('#playerMeta');
    this.badge = root.querySelector('#summaryBadge');
    this.toggle = root.querySelector('#summaryToggle');

    this.data = null;
    this.raf = null;
    this.lastJump = -1;
    this.scrubbing = false;

    const css = getComputedStyle(document.documentElement);
    this.C = {
      gt: css.getPropertyValue('--gt').trim() || '#9ca3af',
      pred: css.getPropertyValue('--pred').trim() || '#e11d48',
      mods: [
        css.getPropertyValue('--mod-v').trim() || '#3b82f6',
        css.getPropertyValue('--mod-t').trim() || '#10b981',
        css.getPropertyValue('--mod-a').trim() || '#f59e0b',
      ],
      hair: '#e5e7eb', label: '#6b7280',
    };

    this._bind();
  }

  _bind() {
    const v = this.video;
    v.addEventListener('play', () => this._startLoop());
    v.addEventListener('pause', () => this._stopLoop());
    v.addEventListener('ended', () => this._stopLoop());
    v.addEventListener('seeked', () => this.draw());
    v.addEventListener('loadedmetadata', () => this.draw());

    window.addEventListener('resize', () => { this._resize(); this.draw(); });

    this.toggle.addEventListener('change', () => {
      this.lastJump = -1;
      if (this.toggle.checked && this.data) {
        const t = this.video.currentTime;
        if (!this._inSegment(t)) this._jumpToNext(t);
      }
      this.draw();
    });

    const seek = (e) => {
      if (!this.data) return;
      const rect = this.canvas.getBoundingClientRect();
      const x = (e.clientX - rect.left - this.padL) / this.plotW();
      const t = Math.max(0, Math.min(1, x)) * this.data.duration;
      this.video.currentTime = t;
      this.lastJump = performance.now();
      this.draw();
    };
    this.canvas.addEventListener('pointerdown', (e) => {
      e.preventDefault();
      this.scrubbing = true;
      try { this.canvas.setPointerCapture(e.pointerId); } catch {}
      seek(e);
    });
    this.canvas.addEventListener('pointermove', (e) => { if (this.scrubbing) seek(e); });
    this.canvas.addEventListener('pointerup', () => { this.scrubbing = false; });
    this.canvas.addEventListener('pointercancel', () => { this.scrubbing = false; });
  }

  load(meta) {
    this.root.hidden = false;
    this.titleEl.textContent = meta.title;
    this.metaEl.innerHTML =
      `<span class="chip">τ ${meta.ktau.toFixed(2)}</span>` +
      `<span class="chip">ρ ${meta.srho.toFixed(2)}</span>` +
      `${Math.floor(meta.duration / 60)}:${String(meta.duration % 60).padStart(2, '0')} · MoSu test set · id ${meta.id}`;

    this.video.pause();
    this.video.poster = `videos/thumbs/${meta.id}.jpg`;
    this.video.src = `videos/${meta.id}.mp4`;
    this.data = null;
    this.lastJump = -1;
    this._resize();
    this._drawEmpty();

    fetch(`data/v/${meta.id}.json`)
      .then((r) => r.json())
      .then((d) => {
        this.data = d;
        this._resize();
        this.draw();
        // playback is orchestrated by main.js (scroll-into-view autoplay)
        this.root.dispatchEvent(new CustomEvent('demo:dataloaded'));
      });
  }

  /* ---------- layout ---------- */
  _resize() {
    const dpr = window.devicePixelRatio || 1;
    const w = this.canvas.parentElement.clientWidth - 0;
    const narrow = w < 560;
    this.padL = narrow ? 46 : 78;
    this.padR = 8;
    this.lanes = {
      score: { y: 6, h: narrow ? 64 : 84, label: narrow ? 'score' : 'importance' },
      gt:    { y: 0, h: 14, label: narrow ? 'GT' : 'GT summary' },
      pred:  { y: 0, h: 14, label: narrow ? 'ours' : 'our summary' },
      attn:  { y: 0, h: narrow ? 44 : 56, label: narrow ? 'modality' : 'modality attn.' },
    };
    const gap = 7;
    this.lanes.gt.y = this.lanes.score.y + this.lanes.score.h + gap + 2;
    this.lanes.pred.y = this.lanes.gt.y + this.lanes.gt.h + 3;
    this.lanes.attn.y = this.lanes.pred.y + this.lanes.pred.h + gap + 2;
    const totalH = this.lanes.attn.y + this.lanes.attn.h + 20;

    this.canvas.style.height = totalH + 'px';
    this.canvas.width = Math.round(w * dpr);
    this.canvas.height = Math.round(totalH * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.W = w; this.H = totalH;
  }

  plotW() { return this.W - this.padL - this.padR; }
  tx(t) { return this.padL + (t / this.data.duration) * this.plotW(); }

  /* ---------- drawing ---------- */
  _drawEmpty() {
    this.ctx.clearRect(0, 0, this.W, this.H);
    this.ctx.fillStyle = this.C.label;
    this.ctx.font = '12px Inter, sans-serif';
    this.ctx.fillText('loading…', this.padL, 40);
  }

  draw() {
    if (!this.data) return;
    const { ctx } = this;
    const d = this.data;
    const t = Math.min(this.video.currentTime || 0, d.duration);
    ctx.clearRect(0, 0, this.W, this.H);

    this._laneFrame(this.lanes.score);
    this._curve(d.gt_score, this.lanes.score, this.C.gt, 1.4, false);
    this._curve(d.pred_score, this.lanes.score, this.C.pred, 1.8, true);
    this._bands(d.gt_segments, this.lanes.gt, '#6b7280');
    this._bands(d.pred_segments, this.lanes.pred, this.C.pred);
    this._attn(d.attn, this.lanes.attn);
    this._labels();
    this._axis();
    if (this.toggle.checked) this._dimNonSummary();
    this._playhead(t);
    this._updateBadge(t);
  }

  _laneFrame(lane) {
    const { ctx } = this;
    ctx.strokeStyle = this.C.hair;
    ctx.lineWidth = 1;
    ctx.strokeRect(this.padL + .5, lane.y + .5, this.plotW() - 1, lane.h - 1);
  }

  _curve(arr, lane, color, lw, fill) {
    const { ctx } = this;
    const n = arr.length;
    const path = new Path2D();
    for (let i = 0; i < n; i++) {
      const x = this.padL + (i / (n - 1)) * this.plotW();
      const y = lane.y + lane.h - arr[i] * (lane.h - 6) - 3;
      i ? path.lineTo(x, y) : path.moveTo(x, y);
    }
    if (fill) {
      const f = new Path2D(path);
      f.lineTo(this.padL + this.plotW(), lane.y + lane.h);
      f.lineTo(this.padL, lane.y + lane.h);
      f.closePath();
      ctx.fillStyle = color + '14';
      ctx.fill(f);
    }
    ctx.strokeStyle = color;
    ctx.lineWidth = lw;
    ctx.lineJoin = 'round';
    ctx.stroke(path);
  }

  _bands(segs, lane, color) {
    const { ctx } = this;
    ctx.fillStyle = '#f3f4f6';
    ctx.fillRect(this.padL, lane.y, this.plotW(), lane.h);
    ctx.fillStyle = color;
    for (const [s, e] of segs) {
      const x0 = this.tx(s), x1 = this.tx(e);
      ctx.beginPath();
      ctx.roundRect(x0, lane.y + 1, Math.max(2, x1 - x0), lane.h - 2, 3);
      ctx.fill();
    }
  }

  _attn(attn, lane) {
    const { ctx } = this;
    const n = attn.length;
    let prevTop = new Float32Array(n).fill(lane.y + lane.h);
    for (let m = 0; m < 3; m++) {
      ctx.beginPath();
      const tops = new Float32Array(n);
      for (let i = 0; i < n; i++) {
        const x = this.padL + (i / (n - 1)) * this.plotW();
        tops[i] = prevTop[i] - attn[i][m] * lane.h;
        i ? ctx.lineTo(x, tops[i]) : ctx.moveTo(x, tops[i]);
      }
      for (let i = n - 1; i >= 0; i--) {
        const x = this.padL + (i / (n - 1)) * this.plotW();
        ctx.lineTo(x, prevTop[i]);
      }
      ctx.closePath();
      ctx.fillStyle = this.C.mods[m] + 'cc';
      ctx.fill();
      prevTop = tops;
    }
    ctx.strokeStyle = this.C.hair;
    ctx.strokeRect(this.padL + .5, lane.y + .5, this.plotW() - 1, lane.h - 1);
  }

  _labels() {
    const { ctx } = this;
    ctx.fillStyle = this.C.label;
    ctx.font = '600 10.5px Inter, sans-serif';
    ctx.textAlign = 'right';
    for (const k of ['score', 'gt', 'pred', 'attn']) {
      const lane = this.lanes[k];
      ctx.fillText(lane.label, this.padL - 7, lane.y + lane.h / 2 + 3.5);
    }
    ctx.textAlign = 'left';
  }

  _axis() {
    const { ctx } = this;
    const d = this.data.duration;
    const y = this.lanes.attn.y + this.lanes.attn.h;
    const step = d > 240 ? 60 : d > 100 ? 30 : 15;
    ctx.fillStyle = this.C.label;
    ctx.font = '10px Inter, sans-serif';
    ctx.textAlign = 'center';
    for (let s = 0; s <= d - step * 0.4; s += step) {
      const x = this.tx(s);
      ctx.fillStyle = this.C.hair;
      ctx.fillRect(x, y, 1, 4);
      ctx.fillStyle = this.C.label;
      ctx.fillText(this._fmt(s), x, y + 14);
    }
    ctx.fillText(this._fmt(d), this.tx(d), y + 14);
    ctx.textAlign = 'left';
  }

  _fmt(s) { return `${Math.floor(s / 60)}:${String(Math.round(s) % 60).padStart(2, '0')}`; }

  _dimNonSummary() {
    const { ctx } = this;
    const segs = this.data.pred_segments;
    const yTop = this.lanes.score.y, yBot = this.lanes.attn.y + this.lanes.attn.h;
    ctx.fillStyle = 'rgba(255,255,255,.62)';
    let cur = 0;
    for (const [s, e] of segs) {
      if (s > cur) ctx.fillRect(this.tx(cur), yTop, this.tx(s) - this.tx(cur), yBot - yTop);
      cur = e;
    }
    if (cur < this.data.duration) {
      ctx.fillRect(this.tx(cur), yTop, this.tx(this.data.duration) - this.tx(cur), yBot - yTop);
    }
  }

  _playhead(t) {
    const { ctx } = this;
    const x = this.tx(t);
    ctx.strokeStyle = '#111827';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(x, this.lanes.score.y - 4);
    ctx.lineTo(x, this.lanes.attn.y + this.lanes.attn.h + 4);
    ctx.stroke();
    ctx.fillStyle = '#111827';
    ctx.beginPath();
    ctx.moveTo(x - 5, this.lanes.score.y - 5);
    ctx.lineTo(x + 5, this.lanes.score.y - 5);
    ctx.lineTo(x, this.lanes.score.y + 1);
    ctx.closePath();
    ctx.fill();
  }

  /* ---------- summary-only playback ---------- */
  _inSegment(t) {
    return this.data.pred_segments.some(([s, e]) => t >= s && t < e);
  }
  _jumpToNext(t) {
    const segs = this.data.pred_segments;
    const next = segs.find(([s]) => s > t);
    if (next) {
      this.video.currentTime = next[0] + 0.01;
      this.lastJump = performance.now();
    } else {
      this.video.pause();
    }
  }

  _startLoop() {
    if (this.raf) return;
    const tick = () => {
      this.raf = requestAnimationFrame(tick);
      if (this.data && this.toggle.checked && !this.video.paused && !this.scrubbing) {
        const t = this.video.currentTime;
        if (performance.now() - this.lastJump > 250 && !this._inSegment(t)) {
          this._jumpToNext(t);
        }
      }
      this.draw();
    };
    this.raf = requestAnimationFrame(tick);
  }
  _stopLoop() {
    cancelAnimationFrame(this.raf);
    this.raf = null;
    this.draw();
  }

  _updateBadge(t) {
    const inSeg = this._inSegment(t);
    if (this.badge.hidden === inSeg) this.badge.hidden = !inSeg;
  }
}

window.DemoPlayer = DemoPlayer;
