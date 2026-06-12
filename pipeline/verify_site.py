"""Headless verification of the demo site across a device matrix.

Usage: python pipeline/verify_site.py  (expects http server on :8741)
"""
import asyncio
import json
import os

from playwright.async_api import async_playwright

URL = 'http://127.0.0.1:8741/index.html'
SHOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'work', 'shots')

DEVICES = [
    # name, viewport, dpr, mobile(touch)
    ('iphone16pro', {'width': 393, 'height': 852}, 3, True),
    ('galaxy_s24', {'width': 412, 'height': 915}, 2.625, True),
    ('ipad_portrait', {'width': 810, 'height': 1080}, 2, True),
    ('galaxy_tab', {'width': 800, 'height': 1280}, 2, True),
    ('mac_1440', {'width': 1440, 'height': 900}, 2, False),
    ('win_1920', {'width': 1920, 'height': 1080}, 1, False),
]


async def check_device(browser, name, vp, dpr, mobile):
    ctx = await browser.new_context(
        viewport=vp, device_scale_factor=dpr,
        is_mobile=mobile, has_touch=mobile)
    page = await ctx.new_page()
    errors = []
    page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
    page.on('pageerror', lambda e: errors.append(str(e)))
    mp4_requests = []
    page.on('request', lambda req: mp4_requests.append(req.url) if req.url.endswith('.mp4') else None)

    await page.goto(URL, wait_until='load')
    await page.wait_for_selector('.tile', timeout=15000)
    r = {}
    r['no_h_overflow'] = await page.evaluate(
        'document.documentElement.scrollWidth <= window.innerWidth + 1')
    r['tiles'] = await page.locator('.tile').count()
    r['title_ok'] = (await page.title()) == 'TripleSumm (ICLR 2026)'
    r['zoom'] = await page.evaluate('getComputedStyle(document.body).zoom')
    r['grad_animated'] = await page.evaluate(
        'getComputedStyle(document.querySelector(".grad")).animationName === "grad-slide"')
    r['author_underline'] = await page.evaluate(
        'getComputedStyle(document.querySelector(".hero-authors a")).textDecorationLine === "underline"')

    # first tile should be the featured video (5ERr, Evangeline Lilly | CONAN)
    r['first_tile'] = await page.evaluate(
        'document.querySelector(".tile .tile-title")?.textContent.slice(0, 16)')

    # TOC mode: rail visible >=1280px, fab below
    rail = await page.locator('#toc').is_visible()
    fab = await page.locator('#tocFab').is_visible()
    r['toc_mode_ok'] = (rail and not fab) if vp['width'] >= 1280 else (fab and not rail)
    if rail:
        # rail must sit just right of the 980px content column, labels visible, no overflow
        r['toc_rail'] = await page.evaluate('''() => {
          const t = document.getElementById('toc').getBoundingClientRect();
          const z = parseFloat(getComputedStyle(document.body).zoom) || 1;
          const contentRight = (window.innerWidth - 980 * z) / 2 + 980 * z;
          const label = document.querySelector('#toc a span');
          return {gap_from_content: Math.round(t.left - contentRight),
                  fits: t.right <= window.innerWidth,
                  label_visible: getComputedStyle(label).opacity === '1'};
        }''')

    # mobile sheet open/close
    if not rail:
        await page.locator('#tocFab').click()
        r['sheet_opens'] = await page.locator('.toc-sheet-panel').is_visible()
        await page.locator('.toc-sheet-backdrop').click()
        r['sheet_closes'] = await page.locator('#tocSheet').is_hidden()

    await page.screenshot(path=f'{SHOTS}/{name}_top.png')

    # scroll-into-view autoplay (muted) — wait for manifest + first video json
    await page.wait_for_function('window.__player_data_check && !!window.__player_data_check()')
    r['mp4_before_scroll'] = len(mp4_requests)
    await page.locator('#player').scroll_into_view_if_needed()
    await page.wait_for_timeout(1800)
    r['autoplay'] = await page.evaluate('''() => {
      const v = document.getElementById('video');
      return {paused: v.paused, muted: v.muted,
              unmute_btn: !document.getElementById('unmuteBtn').hidden};
    }''')
    # scroll far away -> pauses
    await page.locator('#bibtex').scroll_into_view_if_needed()
    await page.wait_for_timeout(700)
    r['paused_when_away'] = await page.evaluate('document.getElementById("video").paused')

    await page.locator('#player').scroll_into_view_if_needed()
    await page.wait_for_timeout(1200)
    await page.screenshot(path=f'{SHOTS}/{name}_player.png')

    # seek mapping via real mouse on the canvas
    box = await page.locator('#chartCanvas').bounding_box()
    pad_l, plot_w, dur = await page.evaluate(
        '[__demoPlayer.padL, __demoPlayer.plotW(), __demoPlayer.data.duration]')
    await page.mouse.click(box['x'] + pad_l + plot_w * 0.5, box['y'] + 30)
    await page.wait_for_timeout(300)
    actual = await page.evaluate('document.getElementById("video").currentTime')
    r['seek_ok'] = abs(actual - dur * 0.5) < 2.5

    # summary-only skip logic with a mocked clock
    r['summary_check'] = await page.evaluate('''async () => {
      const v = document.getElementById('video');
      let t = 0, paused = true;
      Object.defineProperty(v, 'currentTime', {get: () => t, set: (x) => { t = x; }, configurable: true});
      Object.defineProperty(v, 'paused', {get: () => paused, configurable: true});
      const p = window.__demoPlayer;
      document.getElementById('summaryToggle').checked = true;
      document.getElementById('summaryToggle').dispatchEvent(new Event('change'));
      t = 0; paused = false;
      p._startLoop();
      const segs = p.data.pred_segments;
      const inSeg = x => segs.some(([s, e]) => x >= s - 0.6 && x < e + 0.6);
      let bad = 0, samples = 0;
      const t0 = performance.now();
      while (performance.now() - t0 < 3000 && !paused) {
        await new Promise(r => setTimeout(r, 90));
        t += 0.35;
        await new Promise(r => setTimeout(r, 60));
        samples++;
        if (!inSeg(t)) bad++;
      }
      paused = true; p._stopLoop();
      document.getElementById('summaryToggle').checked = false;
      document.getElementById('summaryToggle').dispatchEvent(new Event('change'));
      return {bad, samples};
    }''')

    # walk the sections for layout screenshots
    for sec in ['motivation', 'dataset', 'method', 'results', 'poster']:
        await page.locator('#' + sec).scroll_into_view_if_needed()
        await page.wait_for_timeout(220)
    await page.screenshot(path=f'{SHOTS}/{name}_results.png')

    r['console_errors'] = errors
    await ctx.close()
    return r


async def run():
    os.makedirs(SHOTS, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        results = {}
        for name, vp, dpr, mobile in DEVICES:
            results[name] = await check_device(browser, name, vp, dpr, mobile)
        await browser.close()
    print(json.dumps(results, indent=2, ensure_ascii=False))


asyncio.run(run())
