/* Gallery, navigation scroll-spy, poster pinch-zoom viewer, BibTeX copy. */
'use strict';

/* ---------- demo gallery ---------- */
const player = new DemoPlayer(document.getElementById('player'));
const gallery = document.getElementById('gallery');
window.__demoPlayer = player;
window.__player_data_check = () => player.data;

fetch('data/videos.json')
  .then((r) => r.json())
  .then(({ videos }) => {
    videos.forEach((v) => {
      const tile = document.createElement('button');
      tile.className = 'tile';
      tile.setAttribute('role', 'listitem');
      tile.innerHTML = `
        <div class="tile-thumb">
          <img src="videos/thumbs/${v.id}.jpg" alt="" loading="lazy" width="640" height="360">
          <span class="dur">${Math.floor(v.duration / 60)}:${String(v.duration % 60).padStart(2, '0')}</span>
          <span class="play-ic"><span>▶</span></span>
        </div>
        <div class="tile-body">
          <div class="tile-title">${escapeHtml(v.title)}</div>
          <div class="tile-metrics">τ <b>${v.ktau.toFixed(2)}</b> · ρ <b>${v.srho.toFixed(2)}</b></div>
        </div>`;
      tile.addEventListener('click', () => {
        gallery.querySelectorAll('.tile.active').forEach((t) => t.classList.remove('active'));
        tile.classList.add('active');
        player.load(v);
        document.getElementById('player').scrollIntoView({ behavior: 'smooth', block: 'center' });
      });
      gallery.appendChild(tile);
    });
    // preview the first video; autoplay (muted) kicks in once it scrolls into view
    if (videos.length) {
      gallery.firstElementChild.classList.add('active');
      player.load(videos[0]);
    }
  });

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

/* ---------- TOC (right rail + mobile sheet) scroll-spy ---------- */
const tocLinks = [...document.querySelectorAll('.toc a, .toc-sheet-panel a')];
const sections = [...document.querySelectorAll('.toc a')]
  .map((a) => document.querySelector(a.getAttribute('href')))
  .filter(Boolean);

const spy = new IntersectionObserver((entries) => {
  for (const en of entries) {
    if (en.isIntersecting) {
      tocLinks.forEach((a) => a.classList.toggle('active', a.getAttribute('href') === '#' + en.target.id));
    }
  }
}, { rootMargin: '-30% 0px -60% 0px' });
sections.forEach((s) => spy.observe(s));

/* mobile TOC sheet */
const tocFab = document.getElementById('tocFab');
const tocSheet = document.getElementById('tocSheet');
function closeSheet() { tocSheet.hidden = true; tocFab.setAttribute('aria-expanded', 'false'); }
tocFab.addEventListener('click', () => {
  tocSheet.hidden = !tocSheet.hidden;
  tocFab.setAttribute('aria-expanded', String(!tocSheet.hidden));
});
tocSheet.querySelector('.toc-sheet-backdrop').addEventListener('click', closeSheet);
tocSheet.querySelectorAll('a').forEach((a) => a.addEventListener('click', closeSheet));
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeSheet(); });

/* ---------- autoplay when the demo player scrolls into view ---------- */
const videoEl = player.video;
const unmuteBtn = document.getElementById('unmuteBtn');
function syncUnmuteBtn() { unmuteBtn.hidden = !(videoEl.muted && !videoEl.paused); }
videoEl.addEventListener('play', syncUnmuteBtn);
videoEl.addEventListener('pause', syncUnmuteBtn);
videoEl.addEventListener('volumechange', syncUnmuteBtn);
unmuteBtn.addEventListener('click', () => { videoEl.muted = false; });

let soundOn = false; // becomes true after an explicit user tap (tile or unmute)
unmuteBtn.addEventListener('click', () => { soundOn = true; });
gallery.addEventListener('click', (e) => { if (e.target.closest('.tile')) soundOn = true; });

let playerInView = false;
function tryAutoplay() {
  if (!playerInView || !player.data || !videoEl.paused) return;
  videoEl.muted = !soundOn;
  const p = videoEl.play();
  if (p) p.catch(() => { videoEl.muted = true; videoEl.play().catch(() => {}); });
}
const autoplaySpy = new IntersectionObserver((entries) => {
  for (const en of entries) {
    playerInView = en.isIntersecting;
    if (en.isIntersecting) tryAutoplay();
    else if (!videoEl.paused) videoEl.pause();
  }
}, { threshold: 0.45 });
autoplaySpy.observe(document.getElementById('player'));
player.root.addEventListener('demo:dataloaded', tryAutoplay);

/* ---------- reveal on scroll ---------- */
const revealTargets = document.querySelectorAll(
  '.section h2, .section .lead, .section figure, .mini-card, .stat-card, .table-wrap, .player, .bibtex-box');
revealTargets.forEach((el) => el.classList.add('reveal'));
const revealer = new IntersectionObserver((entries) => {
  for (const en of entries) {
    if (en.isIntersecting) { en.target.classList.add('in'); revealer.unobserve(en.target); }
  }
}, { rootMargin: '0px 0px -8% 0px' });
revealTargets.forEach((el) => revealer.observe(el));

/* ---------- BibTeX copy ---------- */
document.getElementById('copyBibtex').addEventListener('click', async (e) => {
  const text = document.getElementById('bibtexCode').textContent;
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = document.createElement('textarea');
    ta.value = text; document.body.appendChild(ta); ta.select();
    document.execCommand('copy'); ta.remove();
  }
  e.target.textContent = 'Copied ✓';
  setTimeout(() => { e.target.textContent = 'Copy'; }, 1600);
});

/* ---------- poster pinch-zoom / pan viewer ---------- */
(function posterViewer() {
  const wrap = document.getElementById('posterViewer');
  const img = document.getElementById('posterImg');
  let scale = 1, minScale = 1, x = 0, y = 0;
  const pointers = new Map();
  let lastDist = 0, lastTap = 0;

  function fit() {
    const natW = img.naturalWidth || 2500, natH = img.naturalHeight || 1429;
    minScale = Math.min(wrap.clientWidth / natW, wrap.clientHeight / natH);
    scale = minScale;
    x = (wrap.clientWidth - natW * scale) / 2;
    y = (wrap.clientHeight - natH * scale) / 2;
    apply();
  }
  function clamp() {
    const natW = img.naturalWidth, natH = img.naturalHeight;
    const w = natW * scale, h = natH * scale;
    const minX = Math.min(0, wrap.clientWidth - w), maxX = Math.max(0, wrap.clientWidth - w);
    const minY = Math.min(0, wrap.clientHeight - h), maxY = Math.max(0, wrap.clientHeight - h);
    x = Math.max(minX, Math.min(maxX === 0 ? (wrap.clientWidth - w) / 2 : maxX, x));
    y = Math.max(minY, Math.min(maxY === 0 ? (wrap.clientHeight - h) / 2 : maxY, y));
    if (w <= wrap.clientWidth) x = (wrap.clientWidth - w) / 2;
    if (h <= wrap.clientHeight) y = (wrap.clientHeight - h) / 2;
  }
  function apply() {
    img.style.transform = `translate(${x}px, ${y}px) scale(${scale})`;
  }
  function zoomAt(cx, cy, factor) {
    const ns = Math.max(minScale, Math.min(minScale * 8, scale * factor));
    const rect = wrap.getBoundingClientRect();
    const px = cx - rect.left, py = cy - rect.top;
    x = px - ((px - x) / scale) * ns;
    y = py - ((py - y) / scale) * ns;
    scale = ns;
    clamp(); apply();
  }

  img.addEventListener('load', fit);
  if (img.complete && img.naturalWidth) fit();
  window.addEventListener('resize', fit);

  wrap.addEventListener('wheel', (e) => {
    e.preventDefault();
    zoomAt(e.clientX, e.clientY, e.deltaY < 0 ? 1.15 : 1 / 1.15);
  }, { passive: false });

  wrap.addEventListener('pointerdown', (e) => {
    e.preventDefault();
    wrap.setPointerCapture(e.pointerId);
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.size === 1) {
      const now = performance.now();
      if (now - lastTap < 300) { // double tap: toggle zoom
        if (scale > minScale * 1.05) fit();
        else zoomAt(e.clientX, e.clientY, 2.5);
      }
      lastTap = now;
    } else if (pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      lastDist = Math.hypot(a.x - b.x, a.y - b.y);
    }
  });
  wrap.addEventListener('pointermove', (e) => {
    if (!pointers.has(e.pointerId)) return;
    const prev = pointers.get(e.pointerId);
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.size === 1) {
      x += e.clientX - prev.x;
      y += e.clientY - prev.y;
      clamp(); apply();
    } else if (pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      const dist = Math.hypot(a.x - b.x, a.y - b.y);
      if (lastDist > 0) {
        zoomAt((a.x + b.x) / 2, (a.y + b.y) / 2, dist / lastDist);
      }
      lastDist = dist;
    }
  });
  const lift = (e) => { pointers.delete(e.pointerId); lastDist = 0; };
  wrap.addEventListener('pointerup', lift);
  wrap.addEventListener('pointercancel', lift);
})();
