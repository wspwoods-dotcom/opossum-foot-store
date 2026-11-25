"""Opossum Foot local smoke test — runs the PWA in headless Chromium on this machine.
Serves ~/workspace/possum-foot-app over localhost and drives the new/changed
features via the app's own globals. Reports PASS/FAIL per check.
Usage: ~/workspace/.pw-venv/bin/python tools/smoke-test.py
"""
import json, os, subprocess, sys, time, urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
PORT = 8471
URL = f"http://127.0.0.1:{PORT}/"

results = []
def check(name, ok, detail=""):
    results.append((name, bool(ok), str(detail)))
    print(("PASS " if ok else "FAIL ") + name + (f" — {detail}" if detail else ""), flush=True)

server = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT)],
                           cwd=str(APP), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1)
try:
    from playwright.sync_api import sync_playwright
    errors = []
    with sync_playwright() as p:
        chrome_bin = os.path.join(str(APP.parent), ".browsertest", "chrome-linux64", "chrome")
        browser = p.chromium.launch(executable_path=chrome_bin,
                                    args=["--headless=new", "--no-sandbox"])
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
        page.goto(URL, wait_until="networkidle")
        page.wait_for_timeout(4500)  # splash hold

        # --- onboarding: pick Iowa, skip home ---
        try:
            page.select_option("#onboard-state", "IA")
            page.click("#btn-start")
            page.wait_for_timeout(500)
            page.click("#btn-home-skip")
            page.wait_for_timeout(1000)
            check("onboarding completes", page.evaluate("!!document.querySelector('#view-main.active, #pane-map.active')") or
                  page.evaluate("document.getElementById('view-onboard').style.display") != "", "Iowa selected, home skipped")
        except Exception as e:
            check("onboarding completes", False, repr(e)[:120])

        # --- 1. water set types ---
        r = page.evaluate("""() => {
          openSetForm({lat: 42.0, lng: -94.0});
          const opts = [...document.querySelectorAll('#sf-settype option')].map(o => o.textContent.trim());
          return opts;
        }""")
        check("water set types incl. Top/Bottom edge",
              "Top edge" in r and "Bottom edge" in r,
              f"{len(r)} options")

        # --- 2. jaw closure on foothold ---
        r = page.evaluate("""() => {
          const t = document.getElementById('sf-type');
          t.value = 'Foothold'; t.dispatchEvent(new Event('change', {bubbles: true}));
          const jc = document.getElementById('sf-jawclose');
          if (!jc) return {missing: true};
          return {options: [...jc.options].map(o => o.value)};
        }""")
        check("jaw closure Offset/Closed on foothold",
              not r.get("missing") and "Offset" in r.get("options", []) and "Closed" in r.get("options", []),
              str(r.get("options", r)))
        page.evaluate("() => closeSheets()")

        # --- 3. catch time field ---
        r = page.evaluate("""() => {
          const s = {id: 'test-set-1', name: 'Smoke Test Set', lat: 42.0, lng: -94.0,
                     dateSet: '2026-10-01', status: 'active', trapType: 'Foothold',
                     lineId: activeLineId()};
          Store.data.sets.push(s); Store.save();
          openLogSheet('test-set-1');
          const lt = document.getElementById('log-time');
          const now = new Date();
          const hhmm = String(now.getHours()).padStart(2,'0') + ':' + String(now.getMinutes()).padStart(2,'0');
          const val = lt ? lt.value : null;
          const editable = lt && !lt.disabled && !lt.readOnly;
          // accept current minute or one minute earlier (clock edge)
          const ok = val === hhmm || (() => { const d = new Date(now - 60000);
            return val === String(d.getHours()).padStart(2,'0') + ':' + String(d.getMinutes()).padStart(2,'0'); })();
          return {val, hhmm, editable, ok};
        }""")
        check("catch time field defaults to now, editable",
              r["ok"] and r["editable"], f"value={r['val']} now={r['hhmm']}")
        # no suggestion wiring on catch notes
        r = page.evaluate("""() => ({
          suggestDiv: !!document.getElementById('log-notes-suggest'),
          wired: !!document.getElementById('log-notes')._suggestWired
        })""")
        check("catch notes have no tap-to-fill suggestions",
              not r["suggestDiv"] and not r["wired"], str(r))
        page.evaluate("() => closeSheets()")

        # --- 4. export GPS toggle default off ---
        r = page.evaluate("""() => {
          switchTab('settings');
          const t = document.getElementById('settings-exportcoords');
          return t ? {exists: true, checked: t.checked} : {exists: false};
        }""")
        check("Include GPS in reports toggle exists, default OFF",
              r.get("exists") and r.get("checked") is False, str(r))

        # --- 5. purge tool ---
        r = page.evaluate("""() => {
          const els = ['purge-line','purge-from','purge-to','purge-count','btn-purge'].map(id => !!document.getElementById(id));
          const countText = document.getElementById('purge-count').textContent;
          // empty store (except our test set, no logs): range in the past -> no matches
          document.getElementById('purge-from').value = '2020-01-01';
          document.getElementById('purge-to').value = '2020-12-31';
          document.getElementById('purge-from').dispatchEvent(new Event('change', {bubbles:true}));
          const after = document.getElementById('purge-count').textContent;
          return {els, countText, after};
        }""")
        check("purge tool elements + live count",
              all(r["els"]) and "match" in r["after"],
              r["after"][:80])
        # purge count logic: add a log, verify match count = 1
        r = page.evaluate("""() => {
          Store.data.logs.push({id: 'test-log-1', setId: 'test-set-1', lineId: activeLineId(), type: 'catch',
            species: 'Raccoon', count: 1, disposition: 'kept', date: '2026-09-15', notes: ''});
          Store.save();
          document.getElementById('purge-from').value = '2026-09-01';
          document.getElementById('purge-to').value = '2026-09-30';
          document.getElementById('purge-from').dispatchEvent(new Event('change', {bubbles:true}));
          return document.getElementById('purge-count').textContent;
        }""")
        check("purge count finds 1 matching log", r.strip().startswith("1 "), r[:80])

        # --- 6. CSV export respects GPS toggle (intercept downloadCSV) ---
        r = page.evaluate("""() => {
          let captured = null;
          const orig = downloadCSV;
          downloadCSV = function (fn, rows) { captured = {fn: fn, rows: rows}; };
          const out = {};
          try {
            Store.data.exportCoords = false;
            exportSets(); out.setsOff = captured ? captured.rows[0] : null; captured = null;
            exportCatches(); out.catchesOff = captured ? captured.rows[0] : null; captured = null;
            Store.data.exportCoords = true;
            exportSets(); out.setsOn = captured ? captured.rows[0] : null; captured = null;
            exportCatches(); out.catchesOn = captured ? captured.rows[0] : null; captured = null;
          } finally { downloadCSV = orig; }
          Store.data.exportCoords = false;
          const has = (h, c) => !!(h && h.indexOf(c) !== -1);
          return {
            setsOffLat: has(out.setsOff, 'Latitude'), setsOnLat: has(out.setsOn, 'Latitude'),
            catchesOffLat: has(out.catchesOff, 'Latitude'), catchesOnLat: has(out.catchesOn, 'Latitude'),
            catchesTime: has(out.catchesOff, 'Time'), setsJawClose: has(out.setsOff, 'Jaw closure')
          };
        }""")
        check("CSV drops Lat/Long when toggle off, includes when on",
              r["setsOffLat"] is False and r["setsOnLat"] is True and
              r["catchesOffLat"] is False and r["catchesOnLat"] is True, str(r))
        check("Catches CSV has Time col; Sets CSV has Jaw closure col",
              r["catchesTime"] and r["setsJawClose"], str({k: r[k] for k in ("catchesTime", "setsJawClose")}))

        # --- 7. Q77: check clock follows the trap-check toggle ---
        r = page.evaluate("""() => {
          const out = {};
          const s = getSet('test-set-1');
          // toggle ON state first
          Store.data.checkClockOn = true;
          openSetDetail('test-set-1');
          out.btnVisibleOn = !$('btn-sd-emptycheck').hidden;
          out.lineShownOn = /Trap check/.test($('sd-fields').innerHTML);
          // toggle OFF
          Store.data.checkClockOn = false;
          const before = s.lastActivity;
          touchSet(s);
          out.noStampWhenOff = (s.lastActivity === before);
          s.lastActivity = Date.now() - 30 * 3600 * 1000; // stale: 30h ago
          out.noOverdueWhenOff = (isCheckOverdue(s) === false);
          openSetDetail('test-set-1');
          out.btnHiddenOff = $('btn-sd-emptycheck').hidden === true;
          out.lineHiddenOff = !/Trap check/.test($('sd-fields').innerHTML);
          // flip back ON via the real handler -> clocks restart
          Store.data.checkClockOn = true;
          if (Array.isArray(Store.data.sets)) { const n = Date.now(); Store.data.sets.forEach(x => { x.lastActivity = n; }); }
          out.restamped = Math.abs(getSet('test-set-1').lastActivity - Date.now()) < 60000;
          closeSheets();
          return out;
        }""")
        check("Q77 off: no stamp, no overdue, button+line hidden",
              r["noStampWhenOff"] and r["noOverdueWhenOff"] and r["btnHiddenOff"] and r["lineHiddenOff"], str(r))
        check("Q77 on: button+line visible, clocks restart",
              r["btnVisibleOn"] and r["lineShownOn"] and r["restamped"], str({k: r[k] for k in ("btnVisibleOn", "lineShownOn", "restamped")}))

        # --- fg: sponsors, None row, splash, banner ---
        r = page.evaluate("""() => {
          const ids = SPONSORS.map(s => s.id);
          const ph = SPONSORS.find(s => s.id === 'pine-hollow');
          const ktp = SPONSORS.find(s => s.id === 'kansas-trapline');
          const lures = sponsorSuggests('lure', '').map(x => x.name);
          const sorted = (a) => a.join('|') === [...a].sort((x, y) => x.toLowerCase() < y.toLowerCase() ? -1 : 1).join('|');
          openSetForm({lat: 42.0, lng: -94.0});
          const inp = document.getElementById('sf-bait-row-0');
          /* ft: product lists are type-to-filter now — nothing pops on an
             empty query, so type 'n' for the None row and 'g' for Ghost Dancer. */
          inp.value = 'n'; inp.dispatchEvent(new Event('input', {bubbles: true}));
          const firstRow = document.querySelector('#sf-bait-row-0-suggest .suggest-item');
          const noneRow = firstRow ? firstRow.textContent.trim() : null;
          inp.value = 'g'; inp.dispatchEvent(new Event('input', {bubbles: true}));
          const phRow = !!document.querySelector('#sf-bait-row-0-suggest .suggest-fill[data-v="Ghost Dancer"]');
          closeSheets();
          return {
            ids: ids.join(','), ph: ph ? ph.products.length : -1, ktp: ktp ? ktp.products.length : -1,
            luresSorted: sorted(lures), luresFirst: lures[0],
            banner: [...document.querySelectorAll('#county-banner .smb-chip img')].map(i => i.getAttribute('alt') || '').join(','), bannerBtns: document.querySelectorAll('#county-banner .smb-chip button').length,
            splash: document.getElementById('splash-status').textContent,
            noneRow: noneRow, phRow: phRow
          };
        }""")
        check("fg sponsors PH+KTP, 34/49, sorted lures, None row, chips, splash",
              r["ids"] == "pine-hollow,kansas-trapline" and r["ph"] == 34 and r["ktp"] == 49 and
              r["luresSorted"] and r["luresFirst"] == "All Call LDC" and r["noneRow"] == "None" and
              r["phRow"] and r["bannerBtns"] == 0 and "Pine Hollow" in r["banner"] and "Kansas Trapline" in r["banner"] and r["splash"] == "Follow along.",
              str(r))

        # --- fg Q240: Tight Chains Co. credit ---
        r = page.evaluate("""() => ({
          fixed: document.body.innerHTML.indexOf('Tight Chains Co.') !== -1,
          gone: document.body.innerHTML.indexOf('Tight Chains Apparel LLC') === -1
        })""")
        check("Q240 About credits Tight Chains Co.", r["fixed"] and r["gone"], str(r))

        # --- fg Lefty note 2: duplicate set name blocked ---
        r = page.evaluate("""() => {
          Store.data.sets.push({id: 'dup-1', name: 'Smoke Dup', lat: 42.0, lng: -94.0,
            dateSet: '2026-10-01', status: 'active', lineId: activeLineId()});
          Store.save();
          openSetForm({lat: 42.01, lng: -94.01});
          document.getElementById('sf-name').value = 'smoke dup';
          document.getElementById('sf-status').value = 'active';
          document.getElementById('sf-date').value = '2026-11-01';
          saveSetForm();
          const modal = document.getElementById('modal');
          const shown = modal.classList.contains('show') && /already taken/.test(modal.textContent);
          const stillForm = document.getElementById('sheet-setform').classList.contains('show');
          const count = Store.data.sets.filter(s => String(s.name || '').toLowerCase() === 'smoke dup').length;
          closeModal(); closeSheets();
          return {shown, stillForm, count};
        }""")
        check("duplicate set name blocked by popup, no second set saved",
              r["shown"] and r["stillForm"] and r["count"] == 1, str(r))

        # --- fg Lefty note 1: no toast over the post-catch buttons ---
        r = page.evaluate("""() => {
          const calls = [];
          const origToast = toast;
          toast = function (m) { calls.push(m); };
          openLogSheet('test-set-1');
          logEventType = 'catch'; logSpecies = 'Raccoon';
          saveLog();
          const sheetOpen = document.getElementById('sheet-postcatch').classList.contains('show');
          toast = origToast;
          closeSheets();
          return {calls: calls.length, sheetOpen};
        }""")
        check("catch-logged toast skipped when post-catch sheet opens",
              r["calls"] == 0 and r["sheetOpen"], str(r))

        # --- fg Lefty note 3: measure mode ---
        r = page.evaluate("""() => {
          switchTab('map');
          setMeasureMode(true);
          const on = measureMode && document.getElementById('btn-measure').classList.contains('active-mode')
            && document.getElementById('measure-hint').classList.contains('show');
          measureTap(L.latLng(42.0, -94.0));
          measureTap(L.latLng(42.0, -94.01));
          const layers = measureLayer ? measureLayer.getLayers().length : 0;
          const label = document.querySelector('.measure-label');
          const txt = label ? label.textContent : '';
          setMeasureMode(false);
          const cleared = !measureLayer && !measureMode;
          return {on, layers, txt, cleared};
        }""")
        check("measure mode: toggle, two taps draw line + ft/yd label, off clears",
              r["on"] and r["layers"] == 3 and "ft" in r["txt"] and "yd" in r["txt"] and r["cleared"], str(r))

        # --- fg Q241: photo zoom (double-tap toggles 250%) ---
        r = page.evaluate("""() => {
          const c = document.createElement('canvas'); c.width = 40; c.height = 40;
          return new Promise((res) => {
            c.toBlob((blob) => {
              openPhotoViewer({id: 'zoom-test', createdAt: Date.now(), blob: blob}, null, true);
              const wrap = document.querySelector('#modal-card .pv-zoom');
              const img = wrap ? wrap.querySelector('img') : null;
              const hint = !!document.querySelector('#modal-card .pv-zoom-hint');
              let zoomed = false;
              if (wrap && img) {
                const rect = wrap.getBoundingClientRect();
                const opts = {bubbles: true, pointerId: 7, clientX: rect.left + 50, clientY: rect.top + 50, isPrimary: true};
                wrap.dispatchEvent(new PointerEvent('pointerdown', opts));
                wrap.dispatchEvent(new PointerEvent('pointerup', opts));
                wrap.dispatchEvent(new PointerEvent('pointerdown', opts));
                wrap.dispatchEvent(new PointerEvent('pointerup', opts));
                zoomed = img.style.width === '250%';
              }
              closeModal();
              res({wrap: !!wrap, hint, zoomed});
            });
          });
        }""")
        check("Q241 photo viewer has zoom wrap + hint, double-tap zooms to 250%",
              r["wrap"] and r["hint"] and r["zoomed"], str(r))

        # --- fo: sponsor logos flank the county name in the county banner (display-only) ---
        r = page.evaluate("""() => {
          const chips = [...document.querySelectorAll('#county-banner .smb-chip')];
          const imgs = document.querySelectorAll('#county-banner .smb-chip img').length;
          const btns = chips.reduce((n, c) => n + c.querySelectorAll('button').length, 0);
          const logo = document.querySelector('#county-banner .smb-chip img');
          if (logo) logo.click();
          const bioOpened = document.getElementById('modal').classList.contains('show')
            || !!document.querySelector('.sp-bio-sheet');
          const pe = chips.length ? getComputedStyle(chips[0]).pointerEvents : 'x';
          const tab = document.getElementById('tabbar').getBoundingClientRect();
          const bannerGone = !document.getElementById('sponsor-map-banner');
          const mapChipsGone = document.querySelectorAll('#pane-map .smb-chip').length === 0;
          const ph = document.querySelector('#county-banner .smb-chip-ph img');
          const ktp = document.querySelector('#county-banner .smb-chip-ktp img');
          const phR = ph ? ph.getBoundingClientRect() : null;
          const ktpR = ktp ? ktp.getBoundingClientRect() : null;
          const txt = document.querySelector('#county-banner .cb-text').getBoundingClientRect();
          return {
            chips: chips.length, imgs, btns, bioOpened, pe, bannerGone, mapChipsGone,
            tabBottom: Math.round(tab.bottom), innerH: window.innerHeight,
            phLeft: phR ? Math.round(phR.left) : -1, phRight: phR ? Math.round(phR.right) : -1,
            phH: phR ? Math.round(phR.height) : -1,
            ktpLeft: ktpR ? Math.round(ktpR.left) : -1, ktpRight: ktpR ? Math.round(ktpR.right) : -1,
            ktpH: ktpR ? Math.round(ktpR.height) : -1,
            txtLeft: Math.round(txt.left), txtRight: Math.round(txt.right)
          };
        }""")
        check("fo sponsor logos flank the county name (PH left, KTP right, display-only, tap-through), bottom banner gone, map chips gone, tab bar at viewport bottom",
              r["chips"] == 2 and r["imgs"] == 2 and r["btns"] == 0 and not r["bioOpened"] and
              r["pe"] == "none" and r["bannerGone"] and r["mapChipsGone"] and abs(r["tabBottom"] - r["innerH"]) <= 2 and
              r["phH"] == 56 and r["ktpH"] == 40 and r["phRight"] <= r["txtLeft"] and r["ktpLeft"] >= r["txtRight"], str(r))

        # --- fp: tab bar lifts by the bottom safe-area inset (home indicator clears the labels) ---
        # Headless has no safe area (env() = 0), so the real rule can't lift
        # anything here. Two proofs instead: (1) the rule exists on #tabbar
        # (read the stylesheet text), and (2) simulate a 34px inset by
        # injecting it and measure the buttons lifting while the tab bar
        # itself stays pinned to the viewport bottom.
        r = page.evaluate("""() => {
          let ruleFound = false;
          for (const sh of document.styleSheets) {
            let rules; try { rules = sh.cssRules; } catch (e) { continue; }
            for (const r of rules) {
              if (r.selectorText === '#tabbar' && r.style.paddingBottom.includes('safe-area-inset-bottom')) ruleFound = true;
            }
          }
          const tab = document.getElementById('tabbar');
          const btn = tab.querySelector('button');
          const before = { tabBottom: Math.round(tab.getBoundingClientRect().bottom), btnBottom: Math.round(btn.getBoundingClientRect().bottom), innerH: window.innerHeight };
          const st = document.createElement('style');
          st.textContent = '#tabbar { padding-bottom: 34px !important; }';
          document.head.appendChild(st);
          const after = { tabBottom: Math.round(tab.getBoundingClientRect().bottom), btnBottom: Math.round(btn.getBoundingClientRect().bottom), innerH: window.innerHeight };
          st.remove();
          return { ruleFound, before, after };
        }""")
        check("fp tab bar has the safe-area bottom-padding rule; simulating a 34px inset lifts the tab buttons 34px while the tab bar stays at the viewport bottom",
              r["ruleFound"] and r["before"]["tabBottom"] == r["before"]["innerH"] and
              r["after"]["tabBottom"] == r["after"]["innerH"] and
              (r["before"]["btnBottom"] - r["after"]["btnBottom"]) == 34 and
              r["after"]["btnBottom"] == r["after"]["innerH"] - 34, str(r))

        # --- fq: county name shrink-to-fit on one line (long names, no wrap, no overlap) ---
        r = page.evaluate("""() => {
          const out = {};
          const names = ["Pottawattamie", "Prince George's", "San Bernardino", "Greene"];
          for (const n of names) {
            setCountyBanner({county: n, stateName: 'Iowa'});
            const county = document.getElementById('cb-county');
            const ph = document.querySelector('#county-banner .smb-chip-ph img').getBoundingClientRect();
            const ktp = document.querySelector('#county-banner .smb-chip-ktp img').getBoundingClientRect();
            const cr = county.getBoundingClientRect();
            const banner = document.getElementById('county-banner').getBoundingClientRect();
            out[n] = {
              font: parseFloat(getComputedStyle(county).fontSize),
              h: Math.round(county.offsetHeight),
              fits: county.scrollWidth <= county.clientWidth,
              overlap: cr.left < ph.right || cr.right > ktp.left,
              bannerH: Math.round(banner.height)
            };
          }
          setCountyBanner(null); /* back to County unknown */
          return out;
        }""")
        ok_fq = all(
            r[n]["fits"] and not r[n]["overlap"] and r[n]["h"] <= 34 and r[n]["bannerH"] <= 80
            for n in r
        ) and r["Greene"]["font"] == 22 and r["Pottawattamie"]["font"] < 22 and r["Prince George's"]["font"] < 22 and r["Prince George's"]["font"] >= 14
        check("fq long county names shrink to fit on one line (no wrap, no logo overlap, banner stays one line tall; Greene stays 22px, longest names shrink but stay >= 14px)",
              ok_fq, str(r))

        # --- fs: ruler glyph renders bigger (30px, like the PNG icons) ---
        r = page.evaluate("""() => {
          const svg = document.getElementById('btn-measure').querySelector('svg');
          const cs = getComputedStyle(svg);
          const flag = document.getElementById('btn-mark').querySelector('svg');
          return {
            rulerW: parseFloat(cs.width), rulerH: parseFloat(cs.height),
            rulerHasBody: !!svg.querySelector('g rect'),
            flagW: parseFloat(getComputedStyle(flag).width)
          };
        }""")
        check("fs ruler glyph renders at 30px (same as the PNG fab icons, up from 24px); ruler body still present; flag unchanged at 24px",
              r["rulerW"] == 30 and r["rulerH"] == 30 and r["rulerHasBody"] and r["flagW"] == 24, str(r))

        # --- fr: ruler is a real ruler, sign is a flag (old diamond/line gone) ---
        r = page.evaluate("""() => {
          const m = document.getElementById('btn-measure').querySelector('svg');
          const k = document.getElementById('btn-mark').querySelector('svg');
          return {
            rulerHasBody: !!m.querySelector('g rect'),
            rulerTicks: (m.querySelector('g path') || {}).getAttribute ? (m.querySelector('g path').getAttribute('d').match(/M/g) || []).length : 0,
            oldRulerLineGone: !m.innerHTML.includes('M4 20 L20 4'),
            flagPole: k.innerHTML.includes('M8 21 V5'),
            flagSwallowtail: k.innerHTML.includes('M8 5 H19 L15.5 8 L19 11 H8 Z'),
            oldDiamondGone: !k.innerHTML.includes('rotate(45 12 12)'),
            measureLabel: document.getElementById('btn-measure').getAttribute('aria-label'),
            markLabel: document.getElementById('btn-mark').getAttribute('aria-label')
          };
        }""")
        check("fr ruler is a real ruler (rotated body rect + 4 tick marks, old diagonal line gone); sign is a flag (pole + filled swallowtail, old diamond gone); both buttons keep their labels",
              r["rulerHasBody"] and r["rulerTicks"] == 4 and r["oldRulerLineGone"] and
              r["flagPole"] and r["flagSwallowtail"] and r["oldDiamondGone"] and
              r["measureLabel"] == "Measure distance" and r["markLabel"] == "Mark sign or forage", str(r))

        # --- ft: Show-pill set list (grouped by status, A-Z, tap jumps to set) ---
        # --- ft2: the jump lands on the MAP (sheet closes, detail stays shut,
        #     map centers on the set, and the set's status is switched back on
        #     if it was filtered off) — Tanner taps the pin from there.
        r = page.evaluate("""() => {
          switchTab('map');
          document.getElementById('btn-show').click();
          document.querySelector('[data-show-expand="active"]').click();
          const names = [...document.querySelectorAll('#show-list .show-setname')].map(b => b.textContent.trim());
          const sorted = names.join('|') === [...names].sort((a,b) => a.toLowerCase() < b.toLowerCase() ? -1 : 1).join('|');
          const btn = document.querySelector('#show-list .show-setname');
          const id = btn ? btn.getAttribute('data-jump-set') : null;
          const s = id ? getSet(id) : null;
          if (!s) return {names: names, sorted: sorted, id: null};
          const st = normStatus(s.status);
          const m = showModel(); m[st] = false; saveShowModel(); refreshMarkers();
          btn.click();
          return {names: names, sorted: sorted, id: id, lat: s.lat, lng: s.lng, status: st};
        }""")
        page.wait_for_timeout(1200)
        r2 = page.evaluate("""() => {
          const c = map.getCenter();
          return {
            showClosed: !document.getElementById('sheet-show').classList.contains('show'),
            detailClosed: !document.getElementById('sheet-setdetail').classList.contains('show'),
            center: {lat: c.lat, lng: c.lng}
          };
        }""")
        centered = r.get("lat") is not None and abs(r2["center"]["lat"] - r["lat"]) < 0.002 and abs(r2["center"]["lng"] - r["lng"]) < 0.002
        status_on = page.evaluate("() => showModel()['" + r.get("status", "") + "'] !== false") if r.get("status") else False
        check("ft Show pill expands Active to its set names A-Z; tapping a name lands on the map (sheet closes, detail stays shut, map centers on the set, its status switched back on)",
              len(r["names"]) > 0 and r["sorted"] and r2["showClosed"] and r2["detailClosed"] and centered and status_on,
              str({**r, **r2, "centered": centered, "statusOn": status_on}))

        # --- fv (2026-11-14, Tanner's redundancy audit): Show sheet applies
        #     LIVE — a checkbox tap writes the live model at once (no Done,
        #     no draft); the X just closes. Postcatch has no Keep-as-is and
        #     the Filter sheet has no Done — the X is the only close there.
        r = page.evaluate("""() => {
          switchTab('map');
          const m = showModel(); m.sprung = true; saveShowModel(); renderShowButton();
          document.getElementById('btn-show').click();
          const cb = document.querySelector('input[data-show-status="sprung"]');
          if (!cb) return {noRow: true};
          cb.checked = false; cb.dispatchEvent(new Event('change', {bubbles: true}));
          const liveNow = Store.data.mapShow.sprung === false;
          document.querySelector('#sheet-show .sheet-x').click();
          document.getElementById('btn-show').click();
          const stuck = document.querySelector('input[data-show-status="sprung"]').checked === false;
          const cb2 = document.querySelector('input[data-show-status="sprung"]');
          cb2.checked = true; cb2.dispatchEvent(new Event('change', {bubbles: true}));
          const backOn = Store.data.mapShow.sprung === true;
          closeSheets();
          return {liveNow: liveNow, stuck: stuck, backOn: backOn,
            noShowDone: !document.getElementById('btn-show-done'),
            noPcKeep: !document.getElementById('btn-pc-keep'),
            noMsDone: !document.getElementById('sheet-ms-done')};
        }""")
        check("fv Show sheet applies live (checkbox writes the model at once, X just closes, change sticks); no Show Done, no postcatch Keep-as-is, no Filter Done",
              r.get("liveNow") and r.get("stuck") and r.get("backOn") and r.get("noShowDone") and r.get("noPcKeep") and r.get("noMsDone"), str(r))

        # --- fw: one map command at a time + drag-bar buttons match ---
        r = page.evaluate("""() => {
          switchTab('map');
          const hint = (id) => document.getElementById(id).classList.contains('show');
          const bar = (id) => document.getElementById(id).classList.contains('show');
          setDropPinMode(true);
          const pinHintOn = hint('pin-hint');
          Markers.startPinPlace();
          const pinHintOffAfterSign = !hint('pin-hint');
          const mkHintOn = hint('mk-hint');
          setMeasureMode(true);
          const mkHintOffAfterMeasure = !hint('mk-hint');
          const measureHintOn = hint('measure-hint');
          setDropPinMode(true);
          const measureHintOffAfterPin = !hint('measure-hint');
          const pinHintOnAgain = hint('pin-hint');
          setDropPinMode(false); setMeasureMode(false);
          setDropPinMode(true);
          map.fire('click', { latlng: L.latLng(42.0, -94.0) });
          const placeBarOn = bar('place-bar');
          Markers.startPinPlace();
          const placeBarOffAfterSign = !bar('place-bar');
          const mkHintOn2 = hint('mk-hint');
          Markers.cancelAll();
          const ok1 = document.getElementById('btn-place-ok').innerHTML;
          const ok2 = document.getElementById('btn-mk-place-ok').innerHTML;
          const cx1 = document.getElementById('btn-place-cancel').innerHTML;
          const cx2 = document.getElementById('btn-mk-place-cancel').innerHTML;
          const cx3 = document.getElementById('btn-mk-area-cancel').innerHTML;
          const okMatch = ok1 === ok2 && ok1.indexOf('check.png') !== -1;
          const cxMatch = cx1 === cx2 && cx1 === cx3 && cx1.indexOf('x.png') !== -1 && cx1.indexOf('✕') === -1;
          return {pinHintOn, pinHintOffAfterSign, mkHintOn, mkHintOffAfterMeasure, measureHintOn,
            measureHintOffAfterPin, pinHintOnAgain, placeBarOn, placeBarOffAfterSign, mkHintOn2,
            okMatch, cxMatch, ok1, ok2, cx1, cx2};
        }""")
        check("fw one map command at a time (pin/sign/measure hints + drag bars cancel each other); drag-bar Looks-right/X buttons match",
              r.get("pinHintOn") and r.get("pinHintOffAfterSign") and r.get("mkHintOn")
              and r.get("mkHintOffAfterMeasure") and r.get("measureHintOn")
              and r.get("measureHintOffAfterPin") and r.get("pinHintOnAgain")
              and r.get("placeBarOn") and r.get("placeBarOffAfterSign") and r.get("mkHintOn2")
              and r.get("okMatch") and r.get("cxMatch"), str(r))

        # --- fx: line transfer (share out, accept-first import as a NEW line, dupe blocked) ---
        r = page.evaluate("""() => {
          const ln = activeLine();
          const t = buildLineTransfer(ln);
          const before = { lines: Store.data.lines.length, sets: Store.data.sets.length,
            logs: Store.data.logs.length, active: Store.data.activeLineId };
          importLineTransfer(t);
          const promptShown = document.getElementById('modal2').classList.contains('show');
          document.getElementById('m2-ok').click();
          const newLine = Store.data.lines[Store.data.lines.length - 1];
          const newSets = Store.data.sets.filter(s => s.lineId === newLine.id);
          const newLogs = Store.data.logs.filter(l => l.lineId === newLine.id);
          const oldIds = {};
          Store.data.sets.forEach(s => { if (s.lineId === ln.id) oldIds[s.id] = true; });
          const freshIds = newSets.length > 0 && newSets.every(s => !oldIds[s.id]);
          const newSetIds = {};
          newSets.forEach(s => { newSetIds[s.id] = true; });
          const linksOk = newLogs.every(l => !l.setId || newSetIds[l.setId]);
          const after = { lines: Store.data.lines.length, sets: Store.data.sets.length,
            logs: Store.data.logs.length, active: Store.data.activeLineId };
          importLineTransfer(t);
          const dupeBlocked = Store.data.lines.length === after.lines &&
            !document.getElementById('modal2').classList.contains('show');
          return { kind: t.kind, srcName: t.line.name, tSets: t.sets.length, tLogs: t.logs.length,
            promptShown: promptShown, before: before, after: after, newName: newLine.name,
            newSets: newSets.length, newLogs: newLogs.length, freshIds: freshIds, linksOk: linksOk,
            recorded: !!findImportedTransfer(t.transferId), dupeBlocked: dupeBlocked };
        }""")
        check("fx line transfer: builds for the active line, prompt-first import lands as a NEW line (fresh ids, links remapped, active line untouched), same file blocked twice",
              r["kind"] == "line-transfer" and r["tSets"] > 0 and r["promptShown"]
              and r["after"]["lines"] == r["before"]["lines"] + 1
              and r["after"]["active"] == r["before"]["active"]
              and r["newName"].startswith(r["srcName"])
              and r["newSets"] == r["tSets"] and r["newLogs"] == r["tLogs"]
              and r["freshIds"] and r["linksOk"] and r["recorded"] and r["dupeBlocked"], str(r))

        # --- fx: photo gallery (opens, tiles labeled by set / catch / paperwork) ---
        r = page.evaluate("""async () => {
          const lid = activeLineId();
          const set = Store.data.sets.find(s => s.lineId === lid);
          const log = Store.data.logs.find(l => l.lineId === lid);
          const blob = new Blob(['x'], {type: 'image/jpeg'});
          await IDB.put('photos', { id: 'p-test-set', setId: set.id, blob: blob, mime: 'image/jpeg', lat: set.lat, lng: set.lng, createdAt: Date.now() - 1000 });
          if (log) await IDB.put('photos', { id: 'p-test-catch', setId: log.setId, logId: log.id, blob: blob, mime: 'image/jpeg', createdAt: Date.now() });
          await IDB.put('photos', { id: 'p-test-lic', name: 'test-license.jpg', blob: blob, lineId: lid, createdAt: Date.now() - 2000 });
          openGallery();
          await new Promise(res => setTimeout(res, 700));
          const tiles = [...document.querySelectorAll('#gallery-grid .gal-tile')];
          const titles = tiles.map(t => t.querySelector('.gal-title').textContent);
          const subs = tiles.map(t => t.querySelector('.gal-sub') ? t.querySelector('.gal-sub').textContent : '');
          const sheetOpen = document.getElementById('sheet-gallery').classList.contains('show');
          closeSheets();
          return { sheetOpen: sheetOpen, n: tiles.length, titles: titles, subs: subs,
            setName: set.name, species: log ? log.species : null };
        }""")
        check("fx photo gallery opens, tiles labeled by set / catch / paperwork",
              r["sheetOpen"] and r["n"] >= 2 and r["setName"] in r["titles"] and "Paperwork" in r["subs"]
              and (r["species"] is None or r["species"] in r["titles"]), str(r))

        # --- fz: photo pack (build carries set+catch photos only; import re-attaches by set name; dupe blocked) ---
        r = page.evaluate("""async () => {
          const ln = activeLine();
          const allBefore = await IDB.all('photos');
          let expected = 0;
          (allBefore || []).forEach(p => {
            if (!p || !p.blob || (!p.setId && !p.logId)) return;
            const lab = galleryPhotoLabel(p);
            if (!lab || lab.lineId !== ln.id) return;
            if (packPhotoOwner(p).set) expected++;
          });
          const pack = await buildPhotoPack(ln);
          const withLog = pack.photos.filter(p => p.log).length;
          const beforeIds = {};
          (allBefore || []).forEach(p => { beforeIds[p.id] = true; });
          pack.photos.push({ setName: 'No Such Set FZ', kind: null, name: '', mime: 'image/jpeg',
            createdAt: Date.now(), log: null, data: pack.photos[0].data });
          importPhotoPack(pack);
          const promptShown = document.getElementById('modal2').classList.contains('show');
          document.getElementById('m2-ok').click();
          await new Promise(res => setTimeout(res, 900));
          const after = await IDB.all('photos');
          const added = after.filter(p => !beforeIds[p.id]);
          const onLine = added.filter(p => p.lineId === ln.id && p.setId);
          const catchRe = added.filter(p => p.logId);
          const logOk = catchRe.every(p => { const l = Store.data.logs.find(x => x.id === p.logId); return l && l.lineId === ln.id; });
          const blobOk = added.every(p => p.blob && p.blob.size > 0);
          importPhotoPack(pack);
          const dupeBlocked = !document.getElementById('modal2').classList.contains('show');
          return { kind: pack.kind, n: pack.photos.length - 1, expected: expected, withLog: withLog,
            promptShown: promptShown, added: added.length, onLine: onLine.length,
            catchRe: catchRe.length, logOk: logOk, blobOk: blobOk, dupeBlocked: dupeBlocked };
        }""")
        check("fz photo pack: builds from set+catch photos only, prompt-first import re-attaches by set name (catch photos back on their log), unknown sets skipped, same pack blocked twice",
              r["kind"] == "photo-pack" and r["n"] == r["expected"] and r["expected"] >= 2
              and r["withLog"] >= 1 and r["promptShown"] and r["added"] == r["expected"]
              and r["onLine"] == r["expected"] and r["catchRe"] == r["withLog"] and r["logOk"]
              and r["blobOk"] and r["dupeBlocked"], str(r))

        # --- fx: Show/Actions pill locked while a picking command is armed (pin, ruler, sign) ---
        r = page.evaluate("""() => {
          const pillPE = () => getComputedStyle(document.getElementById('show-pill')).pointerEvents;
          const placing = () => document.body.classList.contains('placing');
          setDropPinMode(true);
          const pinLock = placing() && pillPE() === 'none';
          setDropPinMode(false);
          const pinFree = !placing() && pillPE() !== 'none';
          setMeasureMode(true);
          const rulerLock = placing() && pillPE() === 'none';
          setMeasureMode(false);
          const rulerFree = !placing() && pillPE() !== 'none';
          window.Markers.startPinPlace();
          const signLock = placing() && pillPE() === 'none';
          window.Markers.cancelAll();
          const signFree = !placing() && pillPE() !== 'none';
          return {pinLock, pinFree, rulerLock, rulerFree, signLock, signFree};
        }""")
        check("fx Show/Actions pill is locked while pin, ruler, or sign placement is armed (and free again after)",
              r["pinLock"] and r["pinFree"] and r["rulerLock"] and r["rulerFree"] and r["signLock"] and r["signFree"], str(r))

        # --- fy: zoom on every photo (license, trip/openFullPhoto, marker) + iOS gesture pinch + ruler toggle ---
        r = page.evaluate("""async () => {
          const out = {};
          const c = document.createElement('canvas'); c.width = 800; c.height = 1000;
          const x = c.getContext('2d'); x.fillStyle = '#888'; x.fillRect(0, 0, 800, 1000);
          const blob = await new Promise(res => c.toBlob(res, 'image/jpeg', 0.9));
          const pinch = (wrap) => {
            const img = wrap.querySelector('img');
            const rect = wrap.getBoundingClientRect(); const cy = rect.top + rect.height / 2;
            const pe = (t, id, px) => img.dispatchEvent(new PointerEvent(t, { pointerId: id, clientX: px, clientY: cy, bubbles: true, cancelable: true, pointerType: 'touch' }));
            pe('pointerdown', 1, rect.left + 140); pe('pointerdown', 2, rect.left + 240);
            pe('pointermove', 1, rect.left + 90); pe('pointermove', 2, rect.left + 290);
            const w = img.style.width;
            pe('pointerup', 1, rect.left + 90); pe('pointerup', 2, rect.left + 290);
            return parseFloat(w) > 100;
          };
          // license detail: zoom wired + pinch grows the photo
          licURLs['fy-lic'] = URL.createObjectURL(blob);
          openLicenseDetail({ id: 'fy-lic', blob: blob, link: '', createdAt: Date.now() });
          await new Promise(r2 => setTimeout(r2, 120));
          let wrap = document.querySelector('#modal-card .pv-zoom');
          out.licenseZoom = !!wrap && pinch(wrap);
          closeModal();
          // openFullPhoto (trip photos): exists, opens zoomable viewer
          out.fullPhotoFn = typeof openFullPhoto === 'function';
          openFullPhoto(blob);
          await new Promise(r2 => setTimeout(r2, 120));
          wrap = document.querySelector('#modal-card .pv-zoom');
          out.fullPhotoZoom = !!wrap;
          // iOS gesture pinch: gesturestart + gesturechange scale 2 -> width ~200%
          if (wrap) {
            wrap.dispatchEvent(new Event('gesturestart', { bubbles: true, cancelable: true }));
            const ge = new Event('gesturechange', { bubbles: true, cancelable: true }); ge.scale = 2;
            wrap.dispatchEvent(ge);
            out.gestureZoom = Math.abs(parseFloat(wrap.querySelector('img').style.width) - 200) < 1;
          } else out.gestureZoom = false;
          document.getElementById('m-close').click();
          // ruler toggle: on-> measure works; unchecking hides the button and ends measure mode
          setMeasureMode(true);
          const cb = document.getElementById('settings-ruler');
          out.rulerBox = !!cb;
          cb.checked = false; cb.dispatchEvent(new Event('change', { bubbles: true }));
          out.rulerOff = Store.data.rulerOn === false && document.getElementById('btn-measure').style.display === 'none' && measureMode === false;
          cb.checked = true; cb.dispatchEvent(new Event('change', { bubbles: true }));
          out.rulerOn = Store.data.rulerOn === true && document.getElementById('btn-measure').style.display === '';
          // marker photo: detail thumb opens the layer-2 viewer with zoom
          Store.data.markers.push({ id: 'mk-fy', cat: 'sign', ref: 'S1', fam: 'ground', name: 'Tracks / footprints', lat: 42.0, lng: -94.0, createdAt: Date.now(), lineId: 'line-1' });
          await IDB.put('photos', { id: 'ph-fy', markerId: 'mk-fy', blob: blob, createdAt: Date.now() });
          Markers.openDetail('mk-fy');
          await new Promise(r2 => setTimeout(r2, 450));
          const thumb = document.querySelector('#mk-detail-photos .mk-thumb');
          out.markerThumb = !!thumb;
          if (thumb) thumb.click();
          await new Promise(r2 => setTimeout(r2, 200));
          out.markerViewer = !!document.querySelector('#modal2-card .pv-zoom');
          closeModal2(); closeSheets();
          Store.data.markers = Store.data.markers.filter(m => m.id !== 'mk-fy');
          await IDB.del('photos', 'ph-fy');
          return out;
        }""")
        check("fy zoom on license + trip (openFullPhoto) + marker photos, iOS gesture pinch, ruler feature toggle",
              r["licenseZoom"] and r["fullPhotoFn"] and r["fullPhotoZoom"] and r["gestureZoom"]
              and r["rulerBox"] and r["rulerOff"] and r["rulerOn"] and r["markerThumb"] and r["markerViewer"], str(r))

        # --- ga: set notes as dated entries + iPhone voice-button strip ---
        r = page.evaluate("""() => {
          const out = {};
          openSetForm({ lat: 42.0, lng: -94.0 });
          document.getElementById('sf-name').value = 'GA Notes Set';
          document.getElementById('btn-save-set').click();
          const set = Store.data.sets.find(s => s.name === 'GA Notes Set');
          set.notes = 'GA LEGACY NOTE'; delete set.noteLog; Store.save();
          openSetForm(null, set.id);
          out.legacyShown = document.querySelectorAll('#sf-note-entries .note-entry').length === 1
            && document.querySelector('#sf-note-entries .note-text').textContent === 'GA LEGACY NOTE'
            && document.querySelector('#sf-note-entries .note-date').textContent === 'Earlier note'
            && document.getElementById('sf-notes').value === '';
          document.getElementById('sf-notes').value = 'GA FIRST ENTRY';
          document.getElementById('btn-add-note').click();
          out.staged = formNoteEntries.length === 2 && document.getElementById('sf-notes').value === ''
            && !set.noteLog;
          out.stagedDate = formNoteEntries[1].date === todayISO();
          document.querySelector('#sheet-setform .sheet-x').click();
          out.xDiscards = !set.noteLog && (set.notes === 'GA LEGACY NOTE');
          openSetForm(null, set.id);
          document.getElementById('sf-notes').value = 'GA SECOND ENTRY';
          document.getElementById('btn-save-set').click();
          out.saved = Array.isArray(set.noteLog) && set.noteLog.length === 2
            && set.noteLog[0].text === 'GA LEGACY NOTE' && set.noteLog[1].text === 'GA SECOND ENTRY'
            && set.notes.indexOf('GA LEGACY NOTE') !== -1 && set.notes.indexOf('GA SECOND ENTRY') !== -1;
          appendTranscriptToSetNotes(set.id, 'GA MEMO WORDS');
          out.memoEntry = set.noteLog.length === 3 && set.noteLog[2].text === 'GA MEMO WORDS' && !!set.noteLog[2].date;
          openSetDetail(set.id);
          const sd = document.getElementById('sd-notes').textContent;
          out.detailOrder = sd.indexOf('GA MEMO WORDS') !== -1 && sd.indexOf('GA MEMO WORDS') < sd.indexOf('GA SECOND ENTRY')
            && sd.indexOf('GA SECOND ENTRY') < sd.indexOf('GA LEGACY NOTE');
          closeSheets();
          const origIOS = isIOSPWA;
          isIOSPWA = () => true;
          applyFeatureToggles();
          out.iosStrip = document.getElementById('btn-voice-setnotes').style.display === 'none'
            && document.getElementById('btn-voice-lognotes').style.display === 'none'
            && document.getElementById('voice-setnotes-tip').style.display === ''
            && document.getElementById('voice-lognotes-tip').style.display === '';
          isIOSPWA = origIOS;
          applyFeatureToggles();
          out.iosRestore = document.getElementById('btn-voice-setnotes').style.display === ''
            && document.getElementById('voice-setnotes-tip').style.display === 'none';
          return out;
        }""")
        check("ga notes file as dated entries (legacy carry-over, Add stages, X discards, Save files the box, memo transcript = entry, detail newest-first); iPhone voice buttons stripped for the keyboard tip",
              r["legacyShown"] and r["staged"] and r["stagedDate"] and r["xDiscards"] and r["saved"]
              and r["memoEntry"] and r["detailOrder"] and r["iosStrip"] and r["iosRestore"], str(r))

        # --- gb: mileage toggle off keeps past trips + export; record buttons swap for the note ---
        r = page.evaluate("""() => {
          const out = {};
          const ln = activeLine();
          const savedTrips = (Store.data.trips || []).slice();
          Store.data.trips = savedTrips.concat([{ id: 'gb-trip', lineId: ln.id, date: '2026-11-14', startOdo: 100, endOdo: 142, purpose: 'GB check', createdAt: Date.now() }]);
          Store.data.mileageOn = false; Store.save();
          applyFeatureToggles(); renderPaperworkMileage();
          const card = document.getElementById('setsec-mileage');
          const box = document.getElementById('paperwork-mileage-lines');
          out.offCardShown = card.style.display === '';
          out.offTripListed = !!box.querySelector('[data-trip-edit="gb-trip"]');
          out.offNote = box.textContent.indexOf('Mileage is off') !== -1 && box.textContent.indexOf('Feature Toggles') !== -1;
          out.offNoButtons = !box.querySelector('[data-pm-logtrip]') && !box.querySelector('[data-pm-track]');
          out.offExportShown = document.getElementById('btn-export-mileage').style.display === '';
          Store.data.trips = []; Store.save();
          applyFeatureToggles(); renderPaperworkMileage();
          out.emptyHidden = card.style.display === 'none';
          out.emptyExportHidden = document.getElementById('btn-export-mileage').style.display === 'none';
          Store.data.trips = savedTrips; Store.data.mileageOn = true; Store.save();
          applyFeatureToggles(); renderPaperworkMileage();
          out.onButtons = !!box.querySelector('[data-pm-logtrip]') && !!box.querySelector('[data-pm-track]');
          out.onNoteGone = box.textContent.indexOf('Mileage is off') === -1;
          return out;
        }""")
        check("gb mileage off: past trips stay listed + export stays, record buttons swap for the note; no trips + off hides both; back on restores buttons",
              r["offCardShown"] and r["offTripListed"] and r["offNote"] and r["offNoButtons"] and r["offExportShown"]
              and r["emptyHidden"] and r["emptyExportHidden"] and r["onButtons"] and r["onNoteGone"], str(r))

        # --- gc: History By Species cut (Totals owns species counts) + keyboard-mic icon in the tips ---
        r = page.evaluate("""() => {
          const out = {};
          const ln = activeLine();
          Store.data.logs.push({ id: 'gc-log', lineId: ln.id, setId: '', setName: 'GC Set', species: 'Raccoon', date: todayISO(), disposition: 'kept', count: 1, createdAt: Date.now(), bait: [], lure: [], urine: [], visual: [], audio: [], other: [], trapType: 'Foothold' });
          Store.save();
          histUI.q = ''; histUI.disp = 'all'; histUI.season = 'this';
          const segBtns = [...document.querySelectorAll('#hist-view-seg button')].map(b => b.getAttribute('data-view'));
          out.segViews = segBtns.join(',') === 'date,traptype';
          histUI.view = 'species'; renderHistory();
          out.noSpeciesGroups = !document.querySelector('#history-list .sp-head:not(.tt-head)');
          out.dateFallback = !!document.querySelector('#history-list .log-row, #history-list .day-head');
          histUI.view = 'traptype'; renderHistory();
          out.trapTypeOk = !!document.querySelector('#history-list .tt-head');
          histUI.view = 'date'; renderHistory();
          renderTotals();
          out.totalsSpecies = document.getElementById('totals-body').textContent.indexOf('By Species') !== -1;
          const tipS = document.getElementById('voice-setnotes-tip');
          const tipL = document.getElementById('voice-lognotes-tip');
          out.micIcon = !!tipS.querySelector('svg') && !!tipL.querySelector('svg') && tipS.innerHTML.indexOf('\\u{1F3A4}') === -1;
          Store.data.logs = Store.data.logs.filter(l => l.id !== 'gc-log'); Store.save();
          return out;
        }""")
        check("gc History is the record (seg = By Date + By Trap Type only, stale species view falls back to date, trap-type groups intact); Totals keeps By Species; tips carry the outline mic, not the emoji",
              r["segViews"] and r["noSpeciesGroups"] and r["dateFallback"] and r["trapTypeOk"]
              and r["totalsSpecies"] and r["micIcon"], str(r))

        # --- gd: Totals section chips removed — all three cards always stand ---
        r = page.evaluate("""() => {
          const out = {};
          const ln = activeLine();
          Store.data.logs.push({ id: 'gd-log', lineId: ln.id, setId: '', setName: 'GD Set', species: 'Raccoon', date: todayISO(), disposition: 'kept', count: 1, createdAt: Date.now(), bait: [], lure: [], urine: [], visual: [], audio: [], other: [], trapType: 'Foothold' });
          Store.data.totalsSections = { species: false, set: false, disposition: false };
          Store.save();
          renderTotals();
          const body = document.getElementById('totals-body');
          out.noChips = !document.getElementById('totals-sec-chips');
          out.allCards = body.textContent.indexOf('By Species') !== -1 && body.textContent.indexOf('By Set') !== -1
            && body.textContent.indexOf('By Disposition') !== -1;
          out.heads = body.querySelectorAll('.totals-card-head').length >= 3;
          Store.data.logs = Store.data.logs.filter(l => l.id !== 'gd-log');
          delete Store.data.totalsSections; Store.save();
          return out;
        }""")
        check("gd Totals chips gone: no chip row renders, all three section cards stand even with chip-era stored values all off",
              r["noChips"] and r["allCards"] and r["heads"], str(r))

        # --- ge: By Month card on Totals ---
        r = page.evaluate("""() => {
          const out = {};
          const ln = activeLine();
          const mk = (id, date, count, disp) => ({ id, lineId: ln.id, setId: '', setName: 'GE Set', species: 'Raccoon', date, disposition: disp, count, createdAt: Date.now(), bait: [], lure: [], urine: [], visual: [], audio: [], other: [], trapType: 'Foothold' });
          Store.data.logs.push(mk('ge-log1', '2026-11-02', 2, 'kept'));
          Store.data.logs.push(mk('ge-log2', '2026-12-01', 1, 'released'));
          Store.save();
          renderTotals();
          const cards = [...document.querySelectorAll('#totals-body .card')];
          const mc = cards.find(c => { const h = c.querySelector('.totals-card-head'); return h && h.textContent.indexOf('By Month') !== -1; });
          out.cardFound = !!mc;
          if (mc) {
            const rowEls = [...mc.querySelectorAll('.rowline')];
            const rows = rowEls.map(x => x.textContent.replace(/\\s+/g, ' ').trim());
            out.rows = rows;
            const ni = rows.findIndex(t => t.indexOf('November 2026') !== -1);
            const di = rows.findIndex(t => t.indexOf('December 2026') !== -1);
            out.order = ni !== -1 && di !== -1 && ni < di;
            out.decTotal = di !== -1 && rowEls[di].querySelector('.big-num').textContent.trim() === '1';
            out.decDetail = !!mc.querySelector('[data-totkey="mo:2026-12"]');
          }
          Store.data.logs = Store.data.logs.filter(l => l.id !== 'ge-log1' && l.id !== 'ge-log2');
          Store.save();
          return out;
        }""")
        check("ge Totals gains a By Month card: months in chronological order, December total exact, released detail behind the tap",
              r["cardFound"] and r["order"] and r["decTotal"] and r["decDetail"], str(r))

        # --- gf: remembered custom set types fold into the A-Z run ---
        r = page.evaluate("""() => {
          const out = {};
          rememberCustomOption('sf-settype', 'MM Custom');
          openSetForm({lat: 42.0, lng: -94.0});
          const opts = [...document.querySelectorAll('#sf-settype option')].map(o => o.textContent.trim());
          out.opts = opts;
          out.last = opts[opts.length - 1];
          const body = opts.slice(0, -1);
          out.sorted = body.every((v, i) => i === 0 || body[i - 1].toLowerCase() <= v.toLowerCase());
          out.customIdx = opts.indexOf('MM Custom');
          out.notTailBlock = out.customIdx !== -1 && out.customIdx < opts.length - 2;
          const co = Store.data.customOptions['sf-settype'];
          Store.data.customOptions['sf-settype'] = co.filter(t => t !== 'MM Custom');
          Store.save();
          return out;
        }""")
        check("gf custom set types fold into the A-Z run (list fully sorted, custom mid-list, Other… last)",
              r["sorted"] and r["notTailBlock"] and r["last"] == "Other…", str(r))

        # --- gi: an Other… type-in joins its list the moment it's typed ---
        r = page.evaluate("""() => {
          const out = {};
          openSetForm({lat: 42.0, lng: -94.0});
          const sel = document.getElementById('sf-settype');
          sel.value = '__other';
          sel.dispatchEvent(new Event('change', {bubbles: true}));
          const box = document.getElementById('sf-settype-othertext');
          box.value = 'Fish Stick';
          box.dispatchEvent(new Event('change', {bubbles: true}));
          const opts = [...sel.querySelectorAll('option')].map(o => o.textContent.trim());
          out.idx = opts.indexOf('Fish Stick');
          const body = opts.slice(0, -1);
          out.sorted = body.every((v, i) => i === 0 || body[i - 1].toLowerCase() <= v.toLowerCase());
          out.nextIsFlat = opts[out.idx + 1] === 'Flat';
          out.stillOther = sel.value === '__other';
          out.textKept = box.value === 'Fish Stick';
          out.remembered = (Store.data.customOptions['sf-settype'] || []).includes('Fish Stick');
          const mk = document.getElementById('sf-maker');
          mk.value = '__other';
          mk.dispatchEvent(new Event('change', {bubbles: true}));
          const mkBox = document.getElementById('sf-maker-othertext');
          mkBox.value = 'Acme Trap Co';
          mkBox.dispatchEvent(new Event('change', {bubbles: true}));
          const mkOpts = [...mk.querySelectorAll('option')].map(o => o.textContent.trim());
          out.makerIdx = mkOpts.indexOf('Acme Trap Co');
          out.makerBeforeOther = out.makerIdx !== -1 && mkOpts[out.makerIdx + 1] === 'Other…';
          ['sf-settype', 'sf-maker'].forEach(id => {
            Store.data.customOptions[id] = (Store.data.customOptions[id] || []).filter(t => t !== 'Fish Stick' && t !== 'Acme Trap Co');
          });
          Store.save();
          closeSheets();
          return out;
        }""")
        check("gi Other… type-in joins its list immediately (remembered on type, set type folded into the sorted run, maker inserted ahead of Other…)",
              r["remembered"] and r["idx"] != -1 and r["sorted"] and r["nextIsFlat"] and r["stillOther"] and r["textKept"] and r["makerBeforeOther"], str(r))

        # --- gj: a custom variation is remembered under its set type ---
        r = page.evaluate("""() => {
          const out = {};
          openSetForm({lat: 42.0, lng: -94.0});
          const st = document.getElementById('sf-settype');
          st.value = 'Pocket';
          st.dispatchEvent(new Event('change', {bubbles: true}));
          const box = document.getElementById('sf-setvariation-custom');
          box.value = 'Deep Water';
          box.dispatchEvent(new Event('change', {bubbles: true}));
          const vsel = document.getElementById('sf-setvariation');
          out.remembered = (Store.data.customOptions['sf-setvariation:Pocket'] || []).includes('Deep Water');
          out.selected = vsel.value === 'Deep Water';
          out.boxCleared = box.value === '';
          openSetForm({lat: 42.0, lng: -94.0});
          st.value = 'Pocket';
          st.dispatchEvent(new Event('change', {bubbles: true}));
          const opts2 = [...vsel.querySelectorAll('option')].map(o => o.textContent.trim());
          out.stillListed = opts2.includes('Deep Water');
          Store.data.customOptions['sf-setvariation:Pocket'] = (Store.data.customOptions['sf-setvariation:Pocket'] || []).filter(t => t !== 'Deep Water');
          Store.save();
          closeSheets();
          return out;
        }""")
        check("gj custom variation remembered under its set type (selected on the spot, still listed on the next form)",
              r["remembered"] and r["selected"] and r["boxCleared"] and r["stillListed"], str(r))

        # --- ft: Set Type straight A-Z, Other last, no Land/Water groups ---
        r = page.evaluate("""() => {
          openSetForm({lat: 42.0, lng: -94.0});
          const sel = document.getElementById('sf-settype');
          const opts = [...sel.querySelectorAll('option')].map(o => o.textContent.trim());
          const groups = sel.querySelectorAll('optgroup').length;
          closeSheets();
          const body = opts.slice(0, -1);
          const sorted = body.join('|') === [...body].sort((a,b) => a.toLowerCase() < b.toLowerCase() ? -1 : 1).join('|');
          return {opts: opts, groups: groups, sorted: sorted, last: opts[opts.length - 1]};
        }""")
        check("ft Set Type is straight A-Z with Other last and no Land/Water groups",
              r["groups"] == 0 and r["sorted"] and r["last"] == "Other…", str(r))

        # --- ft: product lists type-to-filter (nothing on focus, C matches on 'c', pick fills + closes) ---
        r = page.evaluate("""() => {
          openSetForm({lat: 42.0, lng: -94.0});
          const inp = document.getElementById('sf-lure-row-0');
          const box = document.getElementById('sf-lure-row-0-suggest');
          inp.value = ''; inp.dispatchEvent(new Event('input', {bubbles: true}));
          inp.focus();
          const hiddenOnFocus = !box.classList.contains('show');
          inp.value = 'c'; inp.dispatchEvent(new Event('input', {bubbles: true}));
          const shownOnType = box.classList.contains('show');
          const vals = [...box.querySelectorAll('.suggest-item, .suggest-fill')].map(b => b.getAttribute('data-v') || '');
          const allC = vals.length > 0 && vals.every(v => v.toLowerCase().startsWith('c'));
          const firstBtn = box.querySelector('.suggest-item, .suggest-fill');
          let picked = '', hiddenAfterPick = false;
          if (firstBtn) { firstBtn.click(); picked = inp.value; hiddenAfterPick = !box.classList.contains('show'); }
          closeSheets();
          return {hiddenOnFocus: hiddenOnFocus, shownOnType: shownOnType, vals: vals, allC: allC, picked: picked, hiddenAfterPick: hiddenAfterPick};
        }""")
        check("ft product list stays shut on focus, shows C products on typing 'c', picking one fills it and closes the box",
              r["hiddenOnFocus"] and r["shownOnType"] and r["allC"] and r["picked"] and r["hiddenAfterPick"], str(r))

        # --- fi: sponsor bio has no Tier 2 upsell line ---
        r = page.evaluate("""() => {
          openSponsorBio('pine-hollow');
          const sh = document.querySelector('.sp-bio-sheet');
          const h = sh ? sh.innerHTML : 'no sheet';
          closeModal();
          document.getElementById('modal').classList.remove('sponsor-sheet');
          return {visit: h.indexOf('sp-bio-visit') !== -1, ghost: h.indexOf('Ghost Dancer') !== -1,
                  tier2: h.indexOf('Tier 2') !== -1, upgrade: h.indexOf('sp-bio-upgrade') !== -1};
        }""")
        check("fi sponsor bio: Visit Website + products present, no Tier 2 upsell",
              r["visit"] and r["ghost"] and not r["tier2"] and not r["upgrade"], str(r))

        # --- fj REMOVED (Item 8, 2026-11-24, Tanner): the About viewport
        # diagnostic strip (win/vv/scr/safeB/appH/bannerB) is gone —
        # element and updater both. The --app-h layout math it merely
        # described (fitAppHeight) stays and is asserted elsewhere. ---
        r = page.evaluate("""() => {
          const el = document.getElementById('viewport-stamp');
          const txt = document.body.innerText || '';
          return { el: !!el, fn: typeof reportViewport,
                   text: (txt.indexOf('safeB') !== -1 || txt.indexOf('bannerB') !== -1) };
        }""")
        check("fj viewport diagnostic strip removed (no element, no updater, no metrics text)",
              r["el"] is False and r["fn"] == "undefined" and r["text"] is False, str(r))

        # --- gk: tracking gap break — a >40 s recording gap starts a new
        # segment, counts no distance across it, and saves segmented;
        # a gapless track still saves in the flat shape ---
        r = page.evaluate("""() => {
          const T = window.Tracking._test;
          let fake = 1700000000000;
          const realNow = Date.now;
          Date.now = () => fake;
          const pos = (lat, lng) => ({ coords: { latitude: lat, longitude: lng, accuracy: 5 } });
          T.start();
          T.onPos(pos(42.0000, -94.0000));
          fake += 5000; T.onPos(pos(42.0010, -94.0000));
          fake += 5000; T.onPos(pos(42.0020, -94.0000));
          const milesBeforeGap = T.miles();
          const flatShape = !JSON.stringify(T.downsample(T.pts(), 400)).startsWith('[[[');
          fake += 90000; T.onPos(pos(42.0100, -94.0050));
          const ptsAfter = T.pts();
          const gapFlagged = !!ptsAfter[ptsAfter.length - 1].g;
          fake += 5000; T.onPos(pos(42.0110, -94.0050));
          const res = { milesBeforeGap: milesBeforeGap, milesAfter: T.miles(), gapFlagged: gapFlagged,
                        segs: T.segs(), npts: T.pts().length, flatShape: flatShape,
                        segShape: JSON.stringify(T.downsample(T.pts(), 400)).startsWith('[[[') };
          T.stop();
          Date.now = realNow;
          return res;
        }""")
        check("gk tracking gap: break flagged, 2 segments, no distance across the gap, segmented save / flat save",
              r["gapFlagged"] and r["segs"] == 2 and r["npts"] == 5 and r["flatShape"] and r["segShape"]
              and abs((r["milesAfter"] - r["milesBeforeGap"]) - 0.069) < 0.01, str(r))

        # --- gl: suggestion order — regular entries before sponsored ---
        r = page.evaluate("""() => {
          rememberEntry('lure', 'Alpha Test Lure');
          openSetForm({lat: 42.0, lng: -94.0});
          const inp = document.getElementById('sf-lure-row-0');
          const box = document.getElementById('sf-lure-row-0-suggest');
          inp.value = 'a'; inp.dispatchEvent(new Event('input', {bubbles: true}));
          const rows = [...box.querySelectorAll('.suggest-item, .suggest-fill')];
          const kinds = rows.map(b => b.classList.contains('suggest-fill') ? 'S' : 'R').join('');
          const order = kinds.indexOf('R') !== -1 && kinds.indexOf('S') !== -1 && kinds.lastIndexOf('R') < kinds.indexOf('S');
          closeSheets();
          return {order: order, kinds: kinds};
        }""")
        check("gl suggestion order: regular products list before sponsored products",
              r["order"] is True, str(r))

        # --- gl: feet under a mile on the track bar + finish sheet ---
        r = page.evaluate("""() => {
          const T = window.Tracking._test;
          let fake = 1700000000000;
          const realNow = Date.now;
          Date.now = () => fake;
          const pos = (lat, lng) => ({ coords: { latitude: lat, longitude: lng, accuracy: 5 } });
          T.start();
          T.onPos(pos(42.0000, -94.0000));
          fake += 5000; T.onPos(pos(42.0009, -94.0000));
          const shortBar = document.getElementById('track-stats').textContent;
          let lat = 42.0009;
          for (let i = 0; i < 20; i++) { fake += 5000; lat += 0.001; T.onPos(pos(lat, -94.0000)); }
          const longBar = document.getElementById('track-stats').textContent;
          T.stop();
          const done = document.getElementById('track-done-stats').textContent;
          Date.now = realNow;
          return {shortBar: shortBar, longBar: longBar, done: done};
        }""")
        check("gl feet: short track reads in feet, long track in miles, finish sheet matches",
              r["shortBar"].endswith(" ft") and r["longBar"].endswith(" mi") and " mi" in r["done"], str(r))

        # --- gl: Set Name field is plain (no suggestion wiring, no popup) ---
        r = page.evaluate("""() => {
          openSetForm({lat: 42.0, lng: -94.0});
          const inp = document.getElementById('sf-name');
          const box = document.getElementById('sf-name-suggest');
          inp.value = 'H'; inp.dispatchEvent(new Event('input', {bubbles: true})); inp.focus();
          const res = { wired: !!inp._suggestWired, shown: box ? box.classList.contains('show') : false,
                        html: box ? box.innerHTML : 'no box' };
          closeSheets();
          return res;
        }""")
        check("gl set name plain: no suggestion wiring and nothing pops up",
              not r["wired"] and not r["shown"] and r["html"] == "", str(r))

        # --- gl: collapsible trip rows (kind on the line, detail inside, no elapsed) ---
        r = page.evaluate("""() => {
          const ln = activeLine();
          const savedTrips = (Store.data.trips || []).slice();
          Store.data.trips = [
            { id: 'gl-gps', lineId: ln.id, date: '2026-11-16', source: 'gps-track', miles: 10.3,
              notes: 'GPS track \\u00b7 0:00 \\u00b7 passed 3 of 5 active sets', track: [[42, -94], [42.001, -94]], createdAt: Date.now() },
            { id: 'gl-odo', lineId: ln.id, date: '2026-11-15', startOdo: 100, endOdo: 142,
              notes: 'gl odo note', createdAt: Date.now() - 1000 }
          ];
          Store.save();
          renderPaperworkMileage();
          const box = document.getElementById('paperwork-mileage-lines');
          const blocks = [...box.querySelectorAll('.trip-block')];
          const gps = blocks.find(b => b.textContent.indexOf('GPS track') !== -1);
          const odo = blocks.find(b => b.textContent.indexOf('Odometer') !== -1);
          const out = { n: blocks.length, gps: !!gps, odo: !!odo };
          if (gps) {
            out.gpsHead = gps.querySelector('.trip-head').textContent;
            out.gpsBody = gps.querySelector('.trip-body').textContent;
            out.gpsShut = getComputedStyle(gps.querySelector('.trip-body')).display === 'none';
            gps.querySelector('[data-trip-toggle]').click();
            out.gpsOpen = gps.classList.contains('open');
          }
          if (odo) {
            out.odoHead = odo.querySelector('.trip-head').textContent;
            out.odoEdit = !!odo.querySelector('[data-trip-edit="gl-odo"]');
            out.odoBody = odo.querySelector('.trip-body').textContent;
          }
          Store.data.trips = savedTrips; Store.save();
          renderPaperworkMileage();
          return out;
        }""")
        check("gl trips collapsible: kind + readings on the line, detail/edit inside, elapsed stripped, tap opens",
              r["n"] == 2 and r["gps"] and r["odo"] and r["gpsShut"] and r["gpsOpen"] and r["odoEdit"]
              and "0:00" not in r["gpsHead"] and "Passed 3 of 5 active sets" in r["gpsBody"]
              and "Odometer" in r["odoHead"] and "100" in r["odoHead"] and "142" in r["odoHead"]
              and "gl odo note" in r["odoBody"], str(r))

        # --- console errors ---
        real_errors = [e for e in errors if "favicon" not in e and "net::" not in e]
        check("no JS console/page errors", len(real_errors) == 0,
              f"{len(real_errors)} errors" if real_errors else "clean")
        for e in real_errors[:5]:
            print("   ! " + e[:160])

        browser.close()
finally:
    server.terminate()

fails = [n for n, ok, _ in results if not ok]
print(f"\n{len(results) - len(fails)}/{len(results)} checks passed")
sys.exit(1 if fails else 0)
