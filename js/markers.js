/* ============ Q190/Q191 — Sign & Forage markers ============
   A marker is NOT a set: no status, no checks, no catches, no season
   alerts, never counted in set totals. It is a scouting/intel layer:
   71 mammal-sign kinds (5 families) + 44 forage & finds kinds, each
   with its own glyph, field info behind the pin, sources cited in-app.
   Q191: a marker is a pin OR an area (polygon) for patches.
   Data: Store.data.markers = [{ id, cat:'sign'|'forage'|'custom', ref, fam,
   name, lat, lng } | { ..., poly:[[lat,lng],...] }, note, noteLog,
   createdAt, lineId]. `name` is the KIND's name; `label` is the
   trapper's own name for the marker (2026-11-25, Tanner: markers get
   a Name, REQUIRED like Set Name — see displayName). Photos live in
   IndexedDB 'photos' with markerId set; voice memos live in IndexedDB
   'memos' with markerId set.
   2026-11-25 (Tanner): the marker form joins the set-form family —
   Kind of sign is a picker field (typed customs remembered like every
   other list; a custom kind is cat 'custom' with a plain dot glyph),
   and notes are the set screens' notes family: noteLog entries
   ({id, text, date, at}) filed from a composer, with `note` kept as
   the joined-text mirror — the same dual shape sets carry. Legacy
   markers holding only a single `note` string are migrated into
   noteLog by data() below, so no existing note is ever lost.
   2026-11-25 (Tanner): markers are LINE-SCOPED, like sets — a sign
   recorded on one line no longer shows on every line. render() draws
   only the active line's markers (onActiveLine); a legacy marker
   with no lineId adopts the first line once, in data() below. */
var Markers = (function () {
  var layer = null, mapRef = null;
  var FAM_LABEL = { homes: 'Homes & structures', ground: 'Ground sign', tree: 'Tree & vegetation', feeding: 'Feeding & remains', scent: 'Scent & communication', forage: 'Forage & finds' };
  var FORAGE_FAM_LABEL = { fungi: 'Fungi & mushrooms', fruit: 'Fruits & berries', greens: 'Greens, shoots & plants', mast: 'Nuts & mast', other: 'Other finds' };

  function data() {
    if (!Store.data) return [];
    if (!Array.isArray(Store.data.markers)) Store.data.markers = [];
    /* Notes migration (2026-11-25): a marker written before the notes
       family arrived carries a single `note` string. Fold it into
       noteLog as its first filed entry — dated "Earlier note" (empty
       date), timestamped with the marker's own creation — the same
       legacy shape setNoteEntries gives old sets. `note` itself stays
       as the joined-text mirror, so the string is never lost, on
       upgrade or on backup/restore either way. */
    var changed = false;
    Store.data.markers.forEach(function (mk) {
      if (mk && !Array.isArray(mk.noteLog) && mk.note && String(mk.note).trim()) {
        mk.noteLog = [{ id: uid('n'), text: String(mk.note).trim(), date: '', at: mk.createdAt || 0 }];
        changed = true;
      }
    });
    /* Line adoption (2026-11-25, Tanner): signs live on their own
       line, like sets — see onActiveLine below. A marker recorded
       before lineId existed (or written without one) adopts the FIRST
       line in Store.data.lines order — the user's original line —
       exactly once, in this same migration pass. A marker that
       already carries a lineId is never re-assigned. */
    var firstLineId = null;
    if (Array.isArray(Store.data.lines) && Store.data.lines.length && Store.data.lines[0]) firstLineId = Store.data.lines[0].id;
    if (firstLineId) {
      Store.data.markers.forEach(function (mk) {
        if (mk && (mk.lineId === null || mk.lineId === undefined)) { mk.lineId = firstLineId; changed = true; }
      });
    }
    if (changed && Store.save) { try { Store.save(); } catch (e) { /* noop */ } }
    return Store.data.markers;
  }
  /* The set form's note-entry shape, for markers: entries when they
     exist, else the legacy single string as one undated entry —
     setNoteEntries' exact contract. */
  function markerNoteEntries(mk) {
    if (!mk) return [];
    if (Array.isArray(mk.noteLog)) return mk.noteLog;
    if (mk.note && mk.note.trim()) return [{ id: 'legacy', text: mk.note, date: '', at: mk.createdAt || 0 }];
    return [];
  }
  function syncMkNotesText(mk) {
    var es = Array.isArray(mk.noteLog) ? mk.noteLog : [];
    mk.note = es.map(function (e) { return e.text; }).join('\n');
  }
  function markersOn() { return !Store.data || Store.data.markersOn !== false; }
  /* The marker's headline wherever it is identified (2026-11-25,
     Tanner, options widget): its own Name when it has one, the kind
     otherwise. Every marker written before the Name existed has no
     `label`, so it falls back to the kind exactly as it always
     showed — nothing is renamed by invention. (Uniqueness was NOT
     ruled for marker names — Set Name's Q270 guard does not apply;
     two markers may share a name until Tanner says otherwise.) */
  function displayName(mk) {
    if (!mk) return 'Marker';
    var own = mk.label && String(mk.label).trim();
    return own || mk.name || mk.ref || 'Marker';
  }
  function showModel() {
    var d = Store.data || {};
    if (!d.mapShow) d.mapShow = {};
    var m = d.mapShow;
    ['active', 'sprung', 'pulled', 'missing', 'prospect'].forEach(function (k) { if (m[k] === undefined) m[k] = true; });
    if (!m.fam) m.fam = {};
    ['homes', 'ground', 'tree', 'feeding', 'scent', 'forage'].forEach(function (k) { if (m.fam[k] === undefined) m.fam[k] = true; });
    return m;
  }
  function signEntry(ref) { for (var i = 0; i < SIGN_CATALOG.length; i++) if (SIGN_CATALOG[i].ref === ref) return SIGN_CATALOG[i]; return null; }
  function forageEntry(glyph) { for (var i = 0; i < FORAGE_CATALOG.length; i++) if (FORAGE_CATALOG[i].glyph === glyph) return FORAGE_CATALOG[i]; return null; }
  function glyphSvg(inner) {
    return '<svg viewBox="0 0 24 24" class="mk-glyph">' + (inner || '') + '</svg>';
  }
  function glyphFor(mk) {
    if (mk.cat === 'sign') { var e = signEntry(mk.ref); return glyphSvg(e && SIGN_GLYPHS[mk.ref]); }
    /* A kind the trapper typed himself has no catalog glyph — a plain
       dot in the pin badge, nothing invented. */
    if (mk.cat === 'custom') return glyphSvg('<circle cx="12" cy="12" r="5" fill="currentColor"></circle>');
    return glyphSvg(FORAGE_GLYPHS[mk.ref]);
  }
  function famOf(mk) { return mk.cat === 'sign' ? mk.fam : (mk.cat === 'custom' ? 'custom' : 'forage'); }

  /* Line scope (2026-11-25, Tanner): "my sign actually transfers
     over from line to line — I don't think I want to do that." A
     marker shows only on its own line — the line recorded on it at
     creation — mirroring how sets are scoped (activeSets). The
     per-line Show family model still gates families WITHIN the
     line's own markers. */
  function onActiveLine(mk) {
    var lid = null;
    try { lid = activeLineId(); } catch (e) { lid = null; }
    if (!lid) return true; /* no line resolvable (pre-onboarding) — nothing to scope against */
    return mk.lineId === lid;
  }
  function visible(mk) {
    if (!markersOn()) return false;
    if (!onActiveLine(mk)) return false;
    var m = showModel();
    return m.fam[famOf(mk)] !== false;
  }

  function pinIcon(mk) {
    return L.divIcon({
      className: '',
      html: '<div class="mk-pin">' + glyphFor(mk) + '</div>',
      iconSize: [30, 30], iconAnchor: [15, 15]
    });
  }

  function render() {
    if (!layer || !mapRef) return;
    layer.clearLayers();
    data().forEach(function (mk) {
      if (!visible(mk)) return;
      if (mk.poly && mk.poly.length > 2) {
        var p = L.polygon(mk.poly, { className: 'mk-area', color: '#f0d28a', weight: 2, fillColor: '#2c3e2d', fillOpacity: 0.45 });
        p.on('click', function () { if (document.body.classList.contains('placing') || document.body.classList.contains('editor-lock')) return; openDetail(mk.id); });
        layer.addLayer(p);
        var c = p.getBounds().getCenter();
        var cm = L.marker(c, { icon: pinIcon(mk), title: displayName(mk) });
        cm.on('click', function () { if (document.body.classList.contains('placing') || document.body.classList.contains('editor-lock')) return; openDetail(mk.id); });
        layer.addLayer(cm);
      } else if (isFinite(+mk.lat) && isFinite(+mk.lng)) {
        var m = L.marker([+mk.lat, +mk.lng], { icon: pinIcon(mk), title: displayName(mk) });
        m.on('click', function () { if (document.body.classList.contains('placing') || document.body.classList.contains('editor-lock')) return; openDetail(mk.id); });
        layer.addLayer(m);
      }
    });
  }

  function attach(map) {
    mapRef = map;
    if (!layer) { layer = L.layerGroup().addTo(map); }
    render();
  }

  /* ---------- placement: pin ---------- */
  var placeMk = null, pendingKind = null;
  function setLock(on) { document.body.classList.toggle('placing', !!on); }
  function startPinPlace() {
    cancelAll();
    if (window.cancelAllMapModes) window.cancelAllMapModes(); /* fw: one picking mode at a time */
    setLock(true);
    $('mk-hint').textContent = 'Tap the map where the sign is.';
    $('mk-hint').classList.add('show');
    mode = 'pin-tap';
  }
  var mode = null; /* 'pin-tap' | 'pin-drag' | 'area' */
  function onMapClick(e) {
    if (mode === 'pin-tap') {
      cancelHint();
      placeMk = L.marker(e.latlng, { draggable: true, icon: L.divIcon({ className: '', html: '<div class="mk-pin mk-place">' + glyphSvg('') + '</div>', iconSize: [36, 36], iconAnchor: [18, 18] }) }).addTo(mapRef);
      $('mk-place-bar').classList.add('show');
      mode = 'pin-drag';
      return true;
    }
    if (mode === 'area') {
      areaPts.push([e.latlng.lat, e.latlng.lng]);
      drawAreaDraft();
      return true;
    }
    return false;
  }
  function cancelHint() { var h = $('mk-hint'); if (h) h.classList.remove('show'); }
  function cancelAll() {
    mode = null; areaPts = []; pendingKind = null;
    cancelHint();
    if (placeMk && mapRef) { try { mapRef.removeLayer(placeMk); } catch (e) {} placeMk = null; }
    var pb = $('mk-place-bar'); if (pb) pb.classList.remove('show');
    var ab = $('mk-area-bar'); if (ab) ab.classList.remove('show');
    if (areaDraft && mapRef) { try { mapRef.removeLayer(areaDraft); } catch (e) {} areaDraft = null; }
    setLock(false);
  }

  /* ---------- placement: area (Q191) ---------- */
  var areaPts = [], areaDraft = null;
  function startAreaPlace() {
    cancelAll();
    if (window.cancelAllMapModes) window.cancelAllMapModes(); /* fw: one picking mode at a time */
    setLock(true);
    mode = 'area'; areaPts = [];
    $('mk-hint').textContent = 'Tap the corners around the patch.';
    $('mk-hint').classList.add('show');
    $('mk-area-bar').classList.add('show');
    updateAreaBar();
  }
  function drawAreaDraft() {
    if (areaDraft && mapRef) { try { mapRef.removeLayer(areaDraft); } catch (e) {} }
    if (areaPts.length > 1) {
      areaDraft = L.polygon(areaPts, { color: '#f0d28a', weight: 2, dashArray: '5 4', fillColor: '#2c3e2d', fillOpacity: 0.3 }).addTo(mapRef);
    } else if (areaPts.length === 1) {
      areaDraft = L.circleMarker(areaPts[0], { radius: 5, color: '#f0d28a' }).addTo(mapRef);
    }
    updateAreaBar();
  }
  function updateAreaBar() {
    var b = $('btn-mk-area-done'); if (b) b.disabled = areaPts.length < 3;
    var n = $('mk-area-count'); if (n) n.textContent = areaPts.length ? areaPts.length + (areaPts.length === 1 ? ' corner' : ' corners') : 'No corners yet';
  }

  /* ---------- form ---------- */
  var formCtx = null; /* { mode:'pin'|'area', latlng | poly, editId? } */
  var mkFormNoteEntries = []; /* the open form's staged note entries */
  /* Kind of sign (2026-11-25): catalog names are unique across both
     catalogs (verified — 127 names, no duplicates), so the picker's
     plain name IS the kind's identity. A name in neither catalog is a
     custom kind the trapper typed: remembered by the picker's own
     bag (customKey 'mk-kind'), resolved here to cat 'custom'. */
  function kindByName(name) {
    var i, e;
    for (i = 0; i < SIGN_CATALOG.length; i++) if (SIGN_CATALOG[i].name === name) { e = SIGN_CATALOG[i]; return { cat: 'sign', ref: e.ref, fam: e.fam, name: e.name }; }
    for (i = 0; i < FORAGE_CATALOG.length; i++) if (FORAGE_CATALOG[i].name === name) { e = FORAGE_CATALOG[i]; return { cat: 'forage', ref: e.glyph, fam: 'forage', name: e.name }; }
    return { cat: 'custom', ref: 'custom', fam: 'custom', name: name };
  }
  function kindOptions() {
    var out = [];
    SIGN_CATALOG.forEach(function (e) { out.push(e.name); });
    FORAGE_CATALOG.forEach(function (e) { out.push(e.name); });
    return out;
  }
  /* Inline validation on the marker sheet — showSetFormError's exact
     treatment (the .form-error element, scrolled into view), for the
     one refusal that mirrors Set Name's: a save with no name. */
  function showMkFormError(msg) {
    var el = $('mkform-error');
    if (!el) { toast(msg); return; }
    el.textContent = msg;
    el.classList.add('show');
    el.scrollIntoView({ block: 'nearest' });
  }
  function hideMkFormError() {
    var el = $('mkform-error');
    if (el) { el.textContent = ''; el.classList.remove('show'); }
  }
  /* (2026-11-25): drop the memos staged under the form's provisional
     owner — a NEW marker's memos record under ctx.pendingId (minted
     in openForm, the set form's staging shape); the save adopts the
     id as the marker's own and clears it, so anything still pointing
     at a pendingId when this runs belongs to a form that closed
     without saving, and the recordings must not persist. Called from
     closeSheets (app.js) and at the next openForm. */
  function dropPendingFormMemos() {
    var pid = formCtx && formCtx.pendingId;
    if (!pid) return;
    formCtx.pendingId = null;
    if (typeof IDB === 'undefined') return;
    IDB.all('memos').then(function (all) {
      all.forEach(function (m) { if (m.markerId === pid) IDB.del('memos', m.id); });
    }).catch(function () { /* noop */ });
  }
  function openForm(ctx) {
    if (formCtx && formCtx.pendingId) dropPendingFormMemos(); /* a prior new-form session never saved */
    formCtx = ctx;
    pendingKind = ctx.kind || null;
    hideMkFormError();
    /* Item 4 (2026-11-25, Tanner): the sheet names its identity —
       "Edit marker" for a stored marker, "New marker" only for a new
       one, parallel to the set form's Edit Set / New Set. The title
       used to be a static "New marker" in the markup, so an existing
       marker opened under the wrong name. (The stored note DID load —
       it rode the lone note box; under the notes family it now loads
       as filed entries below.) */
    var title = $('mk-form-title');
    if (title) title.textContent = ctx.editId ? 'Edit marker' : 'New marker';
    var kindInput = $('mk-kind');
    if (kindInput) kindInput.value = pendingKind ? pendingKind.name : '';
    var mk = ctx.editId ? data().filter(function (m) { return m.id === ctx.editId; })[0] : null;
    /* The Name field (required, Set Name's pattern): a stored marker's
       own name, or empty — a legacy marker opens with the box empty
       and will ask for a name at save. The bare write is fine: the
       sheet-open sweep (sweepClearInputs) recomputes its Clear pill
       from the value, like every other field's. */
    var nameInput = $('mk-name');
    if (nameInput) nameInput.value = mk ? (mk.label || '') : '';
    mkFormNoteEntries = mk ? markerNoteEntries(mk).map(function (e) {
      return { id: e.id, text: e.text, date: e.date || '', at: e.at || 0 };
    }) : [];
    var ta = $('mk-note'); if (ta) ta.value = '';
    renderMkFormNoteEntries();
    /* Voice memos: a NEW marker stages them under a provisional
       owner id minted here (Q71's edit-only gate retired, the set
       form's staging shape) — the block renders on New and Edit
       alike; the voice toggle governs it through applyFeatureToggles
       as before. Save adopts the id; an unsaved close drops them. */
    if (!ctx.editId && !ctx.pendingId) ctx.pendingId = uid('mk');
    var memoBlock = $('markerform-memos');
    if (memoBlock) memoBlock.hidden = false;
    if (typeof renderMemos === 'function') renderMemos(ctx.editId || ctx.pendingId, 'mk-memos', true, 'markerId');
    renderFormPhotos(ctx.editId || null);
    openSheet('sheet-marker-form');
  }
  /* The set form's filed-note renderer (renderFormNoteEntries), same
     classes, same card, same confirm-before-delete wording — only the
     box and the staged array are the marker form's own. */
  function renderMkFormNoteEntries() {
    var box = $('mk-note-entries');
    if (!box) return;
    box.innerHTML = '';
    mkFormNoteEntries.slice().reverse().forEach(function (e) {
      var div = document.createElement('div');
      div.className = 'note-entry';
      var head = document.createElement('div');
      head.className = 'entry-head';
      var chev = document.createElement('span');
      chev.className = 'entry-chev';
      chev.setAttribute('aria-hidden', 'true');
      chev.textContent = '›';
      head.appendChild(chev);
      var dl = document.createElement('span');
      dl.className = 'note-date';
      dl.textContent = e.date ? fmtDate(e.date) : 'Earlier note';
      head.appendChild(dl);
      var gl = document.createElement('span');
      gl.className = 'entry-glimpse';
      gl.textContent = e.text;
      head.appendChild(gl);
      var del = document.createElement('button');
      del.type = 'button';
      del.className = 'note-del';
      del.textContent = '✕';
      del.title = 'Delete this note';
      del.onclick = function (ev) {
        if (ev) ev.stopPropagation();
        confirmModal('Delete this note?',
          'This note will be permanently deleted. This cannot be undone — deleted data is gone forever.',
          'Delete', function () {
            mkFormNoteEntries = mkFormNoteEntries.filter(function (x) { return x.id !== e.id; });
            renderMkFormNoteEntries();
          });
      };
      head.appendChild(del);
      head.onclick = function () { div.classList.toggle('expanded'); };
      div.appendChild(head);
      var body = document.createElement('div');
      body.className = 'entry-body';
      var tx = document.createElement('div');
      tx.className = 'note-text';
      tx.textContent = e.text;
      body.appendChild(tx);
      div.appendChild(body);
      box.appendChild(div);
    });
  }
  function stageMkNote() {
    var ta = $('mk-note');
    if (!ta) return false;
    var t = ta.value.trim();
    if (!t) return false;
    mkFormNoteEntries.push({ id: uid('n'), text: t, date: todayISO(), at: Date.now() });
    ta.value = '';
    renderMkFormNoteEntries();
    return true;
  }
  function renderFormPhotos(editId) {
    var host = $('mk-form-photos'); if (!host) return;
    host.innerHTML = '';
    /* Photos picked in this session render as thumbnails right away —
       the set form's pending-photo treatment (they used to be
       invisible until save, announced by a toast only). A tap opens
       the same viewer shape the set form's pending photos use, with
       Remove behind the same confirm. */
    formPhotoFiles.forEach(function (file, idx) {
      var img = document.createElement('img'); img.className = 'mk-thumb'; img.src = URL.createObjectURL(file);
      img.style.cursor = 'pointer';
      img.onclick = function () {
        var url = img.src;
        showModal('<img src="' + url + '" style="width:100%;border-radius:8px" alt="Marker photo">' +
          '<div class="btn-row" style="margin-top:10px"><button class="btn-danger" id="m-ph-del" type="button">Remove</button>' +
          '<button class="btn-secondary" id="m-close" type="button">Close</button></div>');
        if (typeof wirePhotoZoom === 'function') wirePhotoZoom($('modal-card'));
        $('m-close').onclick = function () { closeModal(); };
        $('m-ph-del').onclick = function () {
          confirmModal('Remove this photo?', 'It will not be saved with this marker.', 'Remove', function () {
            formPhotoFiles.splice(idx, 1);
            closeModal();
            renderFormPhotos(editId);
          });
        };
      };
      host.appendChild(img);
    });
    if (!editId) return;
    IDB.all('photos').then(function (all) {
      all.filter(function (p) { return p.markerId === editId; }).forEach(function (p) {
        var img = document.createElement('img'); img.className = 'mk-thumb'; img.src = URL.createObjectURL(p.blob);
        /* fy: tap opens the photo viewer (zoom + save), like every other photo in the app. */
        img.style.cursor = 'pointer';
        img.onclick = function () {
          if (window.openPhotoViewerLayer2) openPhotoViewerLayer2(p, 'Sign photo', function (ph) { return URL.createObjectURL(ph.blob); }, function () {
            closeModal2();
            IDB.del('photos', p.id).then(function () { renderFormPhotos(editId); });
          });
        };
        host.appendChild(img);
      });
    }).catch(function () {});
  }
  function saveForm() {
    if (!formCtx) return;
    /* The Name is required, like Set Name (Tanner, 2026-11-25): the
       refusal is the set form's — an inline message on the sheet,
       checked first, ahead of the kind. No uniqueness guard: Q270 is
       Set Name's law, never ruled for markers. */
    var ownName = ($('mk-name') ? $('mk-name').value : '').trim();
    if (!ownName) { showMkFormError('Name is required — give this marker a name.'); return; }
    if (!pendingKind) { toast('Choose the kind of sign first.'); return; }
    hideMkFormError();
    /* ga's set-form rule, mirrored: a note still in the composer box
       files as an entry too when the form saves. */
    stageMkNote();
    var entries = mkFormNoteEntries.map(function (e) {
      return { id: e.id, text: e.text, date: e.date || '', at: e.at || 0 };
    });
    if (formCtx.editId) {
      var ex = data().filter(function (m) { return m.id === formCtx.editId; })[0];
      if (ex) {
        ex.cat = pendingKind.cat; ex.ref = pendingKind.ref; ex.fam = pendingKind.fam; ex.name = pendingKind.name;
        ex.label = ownName;
        ex.noteLog = entries; syncMkNotesText(ex);
      }
    } else {
      var mk = { id: formCtx.pendingId || uid('mk'), cat: pendingKind.cat, ref: pendingKind.ref, fam: pendingKind.fam, name: pendingKind.name, label: ownName, note: '', noteLog: entries, createdAt: Date.now(), lineId: (activeLine() || {}).id || null };
      syncMkNotesText(mk);
      if (formCtx.mode === 'area') mk.poly = formCtx.poly; else { mk.lat = formCtx.latlng.lat; mk.lng = formCtx.latlng.lng; }
      data().push(mk);
      formCtx.editId = mk.id;
      formCtx.pendingId = null; /* adopted — the staged memos' owner is a real marker now */
    }
    Store.save(); render();
    var newFiles = formPhotoFiles;
    if (newFiles.length) {
      var mid = formCtx.editId;
      /* hj (2026-11-19): the photo carries the owning marker's lineId,
         stamped at write time from the parent record — line-less photo
         records were the root of the License Wallet misfiling. */
      var owner = data().filter(function (m) { return m.id === mid; })[0];
      var mLineId = (owner && owner.lineId) || null;
      newFiles.forEach(function (file) {
        downscalePhoto(file, function (blob) {
          IDB.put('photos', { id: uid('p'), markerId: mid, lineId: mLineId, blob: blob, createdAt: Date.now() }).then(function () { renderFormPhotos(mid); });
        });
      });
      formPhotoFiles = [];
    }
    closeSheets();
    /* Q199 (2026-10-18): Tanner saved a marker with its layer toggled off and
       it looked broken — the app now SAYS why a saved marker won't show,
       instead of leaving the trapper guessing. His words: "Perfect, I like that." */
    var savedMk = data().filter(function (m) { return m.id === formCtx.editId; })[0];
    if (!markersOn()) toast('Marker saved — but the Sign & forage markers layer is off in Settings, so it won\'t show on the map until you turn it back on.');
    else if (savedMk && !visible(savedMk)) toast('Marker saved — but that kind is turned off in the Show list, so it won\'t show on the map until you turn it on there.');
    else toast('Marker saved.');
  }
  var formPhotoFiles = [];

  /* ---------- detail ---------- */
  var detailId = null;
  function openDetail(id) {
    var mk = data().filter(function (m) { return m.id === id; })[0];
    if (!mk) return;
    detailId = id;
    /* The headline is the marker's own Name when it has one, with the
       kind leading the line beneath it; an unnamed (legacy) marker
       renders exactly as it always did — kind as the headline. */
    var named = !!(mk.label && String(mk.label).trim());
    var html = '<div class="mk-detail-head"><span class="mk-kind-ic big">' + glyphFor(mk) + '</span><div><h3>' + esc(displayName(mk)) + '</h3>' +
      '<p class="dim">' + (named ? esc(mk.name) + ' · ' : '') + esc(mk.cat === 'sign' ? FAM_LABEL[mk.fam] : mk.cat === 'custom' ? 'Custom kind' : FORAGE_FAM_LABEL[(forageEntry(mk.ref) || {}).fam] || 'Forage & finds') + ' · ' + (mk.poly ? 'Area' : 'Pin') + ' · ' + new Date(mk.createdAt).toLocaleDateString() + '</p></div></div>';
    /* Q194 (2026-10-18): Tanner — his photo and his note come FIRST; the
       catalog description lives as a tab at the bottom of the page. */
    html += '<div class="mk-detail-photos" id="mk-detail-photos"></div>';
    /* 2026-11-25: the filed notes render as the family's collapsible
       entry cards (noteEntryHTML — the set detail's own renderer),
       newest first; memos render playback-only below them, the set
       detail's treatment (renderMemos, editable=false). */
    var mkEntries = markerNoteEntries(mk);
    if (mkEntries.length) html += '<div class="mk-detail-notes">' + mkEntries.slice().reverse().map(noteEntryHTML).join('') + '</div>';
    html += '<div id="mk-detail-memos" style="margin-top:8px"></div>';
    $('mk-detail-body').innerHTML = html;
    $('mk-detail-body').querySelectorAll('.note-entry .entry-head').forEach(function (h) {
      h.onclick = function () { h.parentElement.classList.toggle('expanded'); };
    });
    if (typeof renderMemos === 'function') renderMemos(mk.id, 'mk-detail-memos', false, 'markerId');
    var infoHost = $('mk-detail-info');
    var ih = infoHtml(mk);
    if (infoHost) {
      /* A custom kind has no catalog entry, hence no info card — the
         section is omitted rather than rendered empty. */
      infoHost.innerHTML = ih ? '<div class="setsec" style="margin-top:14px">' +
        '<button type="button" class="setsec-head" id="mk-info-head" aria-expanded="false"><span>' + (mk.cat === 'sign' ? 'How to read it' : 'About this find') + '</span><span class="setsec-chev" aria-hidden="true">›</span></button>' +
        '<div class="setsec-body" id="mk-info-body" hidden><div class="card mk-info-card">' + ih + '</div></div></div>' : '';
      if (ih) $('mk-info-head').onclick = function () {
        var b = $('mk-info-body'); if (!b) return;
        var open = b.hidden; b.hidden = !open;
        this.setAttribute('aria-expanded', open ? 'true' : 'false');
      };
    }
    IDB.all('photos').then(function (all) {
      var host = $('mk-detail-photos'); if (!host) return;
      all.filter(function (p) { return p.markerId === id; }).forEach(function (p) {
        var img = document.createElement('img'); img.className = 'mk-thumb'; img.src = URL.createObjectURL(p.blob);
        /* fy: tap opens the photo viewer (zoom + save), like every other photo in the app. */
        img.style.cursor = 'pointer';
        img.onclick = function () {
          if (window.openPhotoViewerLayer2) openPhotoViewerLayer2(p, displayName(mk) || 'Sign photo', function (ph) { return URL.createObjectURL(ph.blob); }, function () {
            closeModal2();
            IDB.del('photos', p.id).then(function () { openDetail(id); });
          });
        };
        host.appendChild(img);
      });
    }).catch(function () {});
    openSheet('sheet-marker-detail');
  }
  function infoHtml(mk) {
    if (mk.cat === 'sign') {
      var e = signEntry(mk.ref); if (!e) return '';
      return '<strong>How to read it</strong><p>' + esc(e.desc) + '</p>' +
        '<p><strong>Who makes it:</strong> ' + esc(e.species) + '</p>' +
        '<p><strong>Skill:</strong> ' + esc(e.skill) + '</p>' +
        '<p class="dim">From the Sign &amp; Forage Reference — sources cited there.</p>';
    }
    var f = forageEntry(mk.ref); if (!f) return '';
    return '<strong>How to spot it</strong><p>' + esc(f.recog) + '</p>' +
      '<p><strong>Where:</strong> ' + esc(f.region) + ' · <strong>Season:</strong> ' + esc(f.season) + '</p>' +
      '<p><strong>Who feeds on it:</strong> ' + esc(f.animals) + '</p>' +
      '<p><strong>Skill:</strong> ' + esc(f.skill) + '</p>' +
      (f.safety ? '<p class="mk-safety"><strong>Caution:</strong> ' + esc(f.safety) + '</p>' : '') +
      '<p class="dim">Not a foraging guide — this pin marks where it grows and what feeds on it, not what is safe to eat.</p>';
  }
  function deleteDetail() {
    if (!detailId) return;
    var id = detailId;
    /* 2026-11-24 (next build): the app's own modal instead of
       window.confirm — a native confirm can be swallowed in the store
       build's iOS shell when another presentation is in flight. */
    var go = function () {
      Store.data.markers = data().filter(function (m) { return m.id !== id; });
      Store.save();
      IDB.all('photos').then(function (all) {
        all.filter(function (p) { return p.markerId === id; }).forEach(function (p) { IDB.del('photos', p.id); });
      }).catch(function () {});
      /* The marker's memos go with it — Q38's delete discipline, the
         same cleanup its photos get. */
      IDB.all('memos').then(function (all) {
        all.filter(function (m) { return m.markerId === id; }).forEach(function (m) { IDB.del('memos', m.id); });
      }).catch(function () {});
      detailId = null; closeSheets(); render();
      toast('Marker deleted.');
    };
    if (typeof confirmModal2 === 'function') { confirmModal2('Delete this marker for good?', 'This cannot be undone.', 'Delete', go); return; }
    if (window.confirm('Delete this marker for good? This cannot be undone.')) go();
  }

  return {
    attach: attach, render: render, onMapClick: onMapClick,
    startPinPlace: startPinPlace, startAreaPlace: startAreaPlace,
    cancelAll: cancelAll, openForm: openForm,
    saveForm: saveForm, openDetail: openDetail, displayName: displayName,
    deleteDetail: deleteDetail, showModel: showModel, data: data,
    markerNoteEntries: markerNoteEntries,
    pickKind: function (name) { pendingKind = name ? kindByName(name) : null; },
    kindOptions: kindOptions,
    stageNote: stageMkNote,
    recordMemo: function (btn) {
      var owner = formCtx && (formCtx.editId || formCtx.pendingId);
      if (owner && typeof Memo !== 'undefined') Memo.toggle(owner, btn, null, 'mk-memos', true, 'markerId');
    },
    dropPendingFormMemos: dropPendingFormMemos,
    famLabel: FAM_LABEL, forageFamLabel: FORAGE_FAM_LABEL,
    getPlaceMarker: function () { return placeMk; },
    clearPlaceMarker: function () { placeMk = null; },
    addPhotoFiles: function (files) {
      for (var i = 0; i < files.length; i++) formPhotoFiles.push(files[i]);
      renderFormPhotos(formCtx ? (formCtx.editId || null) : null);
    },
    areaPts: function () { return areaPts; },
    finishPin: function () {
      if (!placeMk) return;
      var ll = placeMk.getLatLng();
      cancelAll();
      openForm({ mode: 'pin', latlng: { lat: ll.lat, lng: ll.lng } });
    },
    finishArea: function () {
      if (areaPts.length < 3) return;
      var poly = areaPts.slice();
      cancelAll();
      openForm({ mode: 'area', poly: poly });
    },
    undoArea: function () { areaPts.pop(); drawAreaDraft(); },
    editDetail: function () {
      var mk = data().filter(function (m) { return m.id === detailId; })[0];
      if (!mk) return;
      closeSheets();
      openForm({ mode: mk.poly ? 'area' : 'pin', latlng: { lat: mk.lat, lng: mk.lng }, poly: mk.poly, editId: mk.id, kind: { cat: mk.cat, ref: mk.ref, fam: mk.fam, name: mk.name } });
    },
    isPlacing: function () { return !!mode; }
  };
})();

/* ---------- Q190 wiring + reference (init) ---------- */
(function () {
  function glyphSpan(inner) { return '<span class="mk-kind-ic">' + '<svg viewBox="0 0 24 24" class="mk-glyph">' + (inner || '') + '</svg></span>'; }
  /* Q205 (2026-10-19): Tanner — the reference lives in the Trapper's Guide
     now (a chapter of the guide, rendered by app.js into the guide sheet),
     with a search bar filtering it. This renderer takes any host + filter;
     app.js owns the chapter shell and the search field, and calls this. */
  function renderReference(host, filter) {
    if (!host) return;
    var q = String(filter || '').trim().toLowerCase();
    function hit() {
      if (!q) return true;
      for (var i = 0; i < arguments.length; i++) {
        if (String(arguments[i] || '').toLowerCase().indexOf(q) !== -1) return true;
      }
      return false;
    }
    var html = '';
    var any = false;
    ['homes', 'ground', 'tree', 'feeding', 'scent'].forEach(function (fam) {
      var rows = '';
      SIGN_CATALOG.forEach(function (e) {
        if (e.fam !== fam) return;
        if (!hit(e.name, e.species, e.desc)) return;
        rows += '<div class="mk-ref-row">' + glyphSpan(SIGN_GLYPHS[e.ref]) + '<div><strong>' + esc(e.name) + '</strong>' +
          '<p>' + esc(e.desc) + '</p><p class="dim">Who makes it: ' + esc(e.species) + ' · Skill: ' + esc(e.skill) + '</p></div></div>';
      });
      if (rows) { html += '<h4 class="mk-ref-fam">' + Markers.famLabel[fam] + '</h4>' + rows; any = true; }
    });
    var frows = '';
    FORAGE_CATALOG.forEach(function (e) {
      if (!hit(e.name, e.recog, e.animals)) return;
      frows += '<div class="mk-ref-row">' + glyphSpan(FORAGE_GLYPHS[e.glyph]) + '<div><strong>' + esc(e.name) + '</strong>' +
        '<p>' + esc(e.recog) + '</p><p class="dim">' + esc(e.region) + ' · ' + esc(e.season) + ' · Skill: ' + esc(e.skill) + '</p>' +
        '<p class="dim">Who feeds on it: ' + esc(e.animals) + '</p>' +
        (e.safety ? '<p class="mk-safety">Caution: ' + esc(e.safety) + '</p>' : '') + '</div></div>';
    });
    if (frows) {
      html += '<h4 class="mk-ref-fam">Forage &amp; finds</h4>' +
        '<p class="dim mk-disclaimer">Not a foraging guide: these pins mark where things grow and what feeds on them — not what is safe to eat. Never eat a wild plant or mushroom based on this app; confirm any identification with a trusted field guide or an expert first.</p>' + frows;
      any = true;
    }
    if (!any) html = '<p class="dim">Nothing in the reference matches that search.</p>';
    if (!q) {
      function srcList(title, arr) {
        if (!arr || !arr.length) return '';
        var h = '<h4 class="mk-ref-fam">' + title + '</h4><ul class="mk-src">';
        arr.forEach(function (s) {
          var m = String(s).match(/https?:\/\/[^\s)]+/);
          var txt = esc(String(s).replace(/https?:\/\/[^\s)]+/, '').replace(/\s+—\s*$/, '').trim());
          h += '<li>' + (m ? '<a href="' + esc(m[0]) + '" target="_blank" rel="noopener">' + txt + '</a>' : txt) + '</li>';
        });
        return h + '</ul>';
      }
      html += srcList('Sources — sign', CATALOG_SOURCES.sign) + srcList('Sources — forage &amp; finds', CATALOG_SOURCES.forage);
    }
    host.innerHTML = html;
  }
  window.renderSignReference = renderReference;
  function syncSettings() {
    var cb = $('settings-markers'); if (!cb || !window.Store || !Store.data) return false;
    cb.checked = Store.data.markersOn !== false;
    var fab = $('btn-mark'); if (fab) fab.style.display = Store.data.markersOn === false ? 'none' : '';
    return true;
  }
  function wire() {
    var fab = $('btn-mark');
    if (fab) fab.onclick = function () {
      /* ho (Q259, Tanner): opening Mark ends the other tap-modes first —
         Measure's banner and measurement clear, so nothing stacks. */
      if (window.cancelAllMapModes) window.cancelAllMapModes('mark');
      openSheet('sheet-marker-add');
    };
    $('btn-mk-add-pin').onclick = function () { closeSheets(); Markers.startPinPlace(); };
    $('btn-mk-add-area').onclick = function () { closeSheets(); Markers.startAreaPlace(); };
    $('btn-mk-place-ok').onclick = function () { Markers.finishPin(); };
    $('btn-mk-place-cancel').onclick = function () { Markers.cancelAll(); };
    $('btn-mk-area-done').onclick = function () { Markers.finishArea(); };
    $('btn-mk-area-undo').onclick = function () { Markers.undoArea(); };
    $('btn-mk-area-cancel').onclick = function () { Markers.cancelAll(); };
    /* Kind of sign joins the picker family (2026-11-25): comboAttach
       gives it the full-screen picker, the label-derived title
       ("Kind of Sign"), the Add-to-list confirm row, the remembered
       bag (customKey 'mk-kind') and the beside-the-box Clear pill.
       pendingKind follows the field: a pick resolves the name to its
       catalog kind (or a custom kind); clearing the field un-picks
       it, and Save still refuses an empty kind with its toast — the
       Set Name pattern (Clear present, requirement at save). */
    if (typeof comboAttach === 'function') {
      comboAttach('mk-kind', 'mk-kind-suggest', function () { return Markers.kindOptions(); }, {
        customKey: 'mk-kind',
        onPick: function (v) { Markers.pickKind(v || null); }
      });
    }
    var kindIn = $('mk-kind');
    if (kindIn) kindIn.addEventListener('change', function () { if (!this.value.trim()) Markers.pickKind(null); });
    $('btn-mk-add-note').onclick = function () { if (!Markers.stageNote()) toast('Nothing to add yet — write the note first.'); };
    $('btn-mk-memo').onclick = function () { Markers.recordMemo(this); };
    $('btn-mk-photo').onclick = function () { $('mk-photo-input').click(); };
    $('mk-photo-input').addEventListener('change', function () {
      if (this.files && this.files.length) { Markers.addPhotoFiles(this.files); toast(this.files.length + (this.files.length === 1 ? ' photo' : ' photos') + ' will attach when you save.'); }
      this.value = '';
    });
    $('btn-mk-save').onclick = function () { Markers.saveForm(); };
    $('btn-mk-edit').onclick = function () { Markers.editDetail(); };
    $('btn-mk-delete').onclick = function () { Markers.deleteDetail(); };
    /* Q205: the marker sheet's Reference & sources opens the Trapper's Guide
       at the Sign & Forage Reference chapter (app.js owns the guide). */
    $('btn-mk-ref').onclick = function () { if (window.openGuideReference) window.openGuideReference(); };
    var cb = $('settings-markers');
    if (cb) cb.addEventListener('change', function () {
      Store.data.markersOn = this.checked; Store.save();
      var f = $('btn-mark'); if (f) f.style.display = this.checked ? '' : 'none';
      Markers.render();
    });
    var tries = 0;
    var iv = setInterval(function () { if (syncSettings() || ++tries > 16) clearInterval(iv); }, 300);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', wire);
  else wire();
})();
