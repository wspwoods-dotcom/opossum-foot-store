/* Opossum Foot — store build: the full-app unlock (2026-11-22).
   The consumer model, locked 2026-10-19: free is three dozen sets on one
   line, free forever; the full app is $14.99 one time, no subscription,
   every future update included. Billing runs through the stores' own
   systems via @capgo/native-purchases (free plugin) — the app holds no
   account and no payment details, same promise as everything else here.
   In a plain browser there is no store to buy from: the gates still hold
   and the buttons explain where unlocking happens. Existing records are
   never taken away and edits are never gated — the gates stand at the
   doors that ADD: a set past the free measure, a second line, and every
   import that would carry a locked app past the measure (pin files,
   shared lines, and backups alike — one law at every door, Tanner's
   rulings 2026-11-23). Ownership is always checked FIRST and silently:
   a purchase found means the app is unlocked and no import is ever
   counted; the counting only ever happens on an app still locked after
   that check, and it happens at the door, before any content lands. */
var Unlock = (function () {
  var PRODUCT_ID = 'com.opossumfoot.app.full';
  var FREE_SETS = 36;
  var priceText = '$14.99';

  function plugin() {
    try {
      if (window.Capacitor && Capacitor.Plugins && Capacitor.Plugins.NativePurchases) return Capacitor.Plugins.NativePurchases;
    } catch (e) {}
    return null;
  }
  function isUnlocked() {
    return !!(window.Store && Store.data && Store.data.unlocked);
  }
  function setUnlocked(v) {
    if (!window.Store || !Store.data) return;
    Store.data.unlocked = !!v;
    Store.save();
    renderStatus();
    /* an import that was waiting at the door on this unlock walks in */
    if (v && pendingProceed) {
      var p = pendingProceed;
      pendingProceed = null;
      try { p(); } catch (e) {}
    }
  }
  function setsOnLine(lineId) {
    if (!window.Store || !Store.data) return 0;
    var n = 0;
    (Store.data.sets || []).forEach(function (s) { if (s && s.lineId === lineId) n++; });
    return n;
  }
  function lineCount() {
    return (window.Store && Store.data && Store.data.lines) ? Store.data.lines.length : 0;
  }

  /* ---- ownership, checked first and silently (2026-11-23) ----
     The boot check reads the store's own entitlement list
     (getPurchases) and NEVER calls restorePurchases: restore syncs
     with the store and makes iOS demand an account sign-in, which is
     how build 19 greeted Tanner with a sign-in prompt at launch in an
     app that promises "nothing to sign into." Reading entitlements
     prompts for nothing. The sync — and any sign-in — now happens
     only when the user taps Restore himself. Import gates wait for
     this check via whenEntitled, so a paid man's restore is never
     counted; if the check cannot finish (no connection), the gates
     proceed after a short wait with the app still locked, and the
     warning sheet's own Restore button is the remedy. */
  var entitlementDone = false;
  var entitlementWaiters = [];
  var pendingProceed = null;

  function finishEntitlement() {
    if (entitlementDone) return;
    entitlementDone = true;
    var w = entitlementWaiters;
    entitlementWaiters = [];
    w.forEach(function (cb) { try { cb(); } catch (e) {} });
  }
  function checkEntitlementQuiet() {
    var np = plugin();
    if (!np || !np.getPurchases) { finishEntitlement(); return; }
    var timer = setTimeout(finishEntitlement, 4000);
    np.getPurchases().then(function (purchases) {
      clearTimeout(timer);
      if (ownsFullApp(purchases)) setUnlocked(true);
      finishEntitlement();
    }).catch(function () {
      clearTimeout(timer);
      finishEntitlement();
    });
  }
  function whenEntitled(cb) {
    if (entitlementDone) { cb(); return; }
    entitlementWaiters.push(cb);
  }
  /* The unlock sheet was dismissed without unlocking: whatever import
     was waiting at the door is set down, not carried. */
  function sheetDismissed() { pendingProceed = null; }

  /* ---- the gates: true = walk through, false = the sheet is up ---- */
  function gateNewSet(lineId) {
    if (isUnlocked()) return true;
    if (lineCount() > 1 || setsOnLine(lineId) >= FREE_SETS) { openUnlockSheet('sets'); return false; }
    return true;
  }
  function gateNewLine() {
    if (isUnlocked()) return true;
    openUnlockSheet('line');
    return false;
  }
  /* The import gates (2026-11-23): asynchronous, proceed-style. Each
     waits for the silent ownership check first; an unlocked app walks
     through untouched. A locked app is counted AT THE DOOR — before
     any content lands — and an over-measure import stops at the
     warning sheet, which names the free measure, where he stands, and
     the two roads onward (unlock, or restore a purchase). If he
     unlocks from that sheet, the waiting import proceeds. */
  function gateImportLine(incomingSets, proceed) {
    whenEntitled(function () {
      if (isUnlocked()) { proceed(); return; }
      if (lineCount() >= 1) { pendingProceed = proceed; openUnlockSheet('line'); return; }
      if ((incomingSets || 0) > FREE_SETS) { pendingProceed = proceed; openUnlockSheet('transfer', { fileSets: incomingSets }); return; }
      proceed();
    });
  }
  function gatePinImport(info, proceed) {
    whenEntitled(function () {
      if (isUnlocked()) { proceed(); return; }
      if ((info.lineSets || 0) + (info.newSets || 0) > FREE_SETS) {
        pendingProceed = proceed;
        openUnlockSheet('pins', info);
        return;
      }
      proceed();
    });
  }
  function gateBackupRestore(info, proceed) {
    whenEntitled(function () {
      if (isUnlocked()) { proceed(); return; }
      var over = info.mode === 'merge'
        ? (info.mergeLineSets || 0) > FREE_SETS
        : (info.fileSets || 0) > FREE_SETS || (info.fileLines || 1) > 1;
      if (over) { pendingProceed = proceed; openUnlockSheet('backup', info); return; }
      proceed();
    });
  }

  function openUnlockSheet(reason, detail) {
    var copy = $('unlock-copy');
    if (copy) {
      detail = detail || {};
      if (reason === 'line') {
        copy.textContent = 'A second line is part of the full app. Free covers one line — three dozen sets on it, forever.';
      } else if (reason === 'pins') {
        copy.textContent = 'That file would put ' + ((detail.lineSets || 0) + (detail.newSets || 0)) +
          ' sets on this line — free is three dozen sets on one line. Delete sets until it fits, or unlock the full app and bring them all in.';
      } else if (reason === 'backup') {
        copy.textContent = detail.mode === 'merge'
          ? 'That import would put ' + (detail.mergeLineSets || 0) +
            ' sets on this line — free is three dozen sets on one line. Unlock the full app, or restore a purchase you already made, and it all comes in.'
          : 'That backup holds ' + (detail.fileSets || 0) + ' sets' +
            ((detail.fileLines || 1) > 1 ? ' on ' + detail.fileLines + ' lines' : '') +
            ' — past the free tier\u2019s three dozen sets on one line. Unlock the full app, or restore a purchase you already made, and it restores whole.';
      } else if (reason === 'transfer') {
        copy.textContent = 'That shared line carries ' + (detail.fileSets || 0) +
          ' sets — past the free tier\u2019s three dozen on one line. Unlock the full app and it lands whole.';
      } else {
        copy.textContent = 'That is three dozen sets on this line — the free tier\u2019s full measure.';
      }
    }
    renderStatus();
    openSheet('sheet-unlock');
  }

  /* ---- buying ---- */
  function buy() {
    var np = plugin();
    if (!np) { toast('Unlocking happens in the app itself, from the App Store or Google Play.'); return; }
    np.isBillingSupported().then(function (r) {
      if (r && r.isBillingSupported === false) { toast('This device cannot make store purchases.'); return null; }
      return np.purchaseProduct({ productIdentifier: PRODUCT_ID, productType: 'inapp' });
    }).then(function (tx) {
      if (!tx) return;
      setUnlocked(true);
      closeSheets();
      toast('Full app unlocked — every set, every line. Thank you.');
    }).catch(function () {
      toast('The purchase did not go through — nothing was charged.');
    });
  }
  function ownsFullApp(purchases) {
    if (!purchases) return false;
    var list = purchases.purchases || purchases;
    if (!list || !list.length) return false;
    for (var i = 0; i < list.length; i++) {
      var p = list[i];
      if (p && (p.productIdentifier === PRODUCT_ID || p.productId === PRODUCT_ID)) return true;
    }
    return false;
  }
  function restore(quiet) {
    var np = plugin();
    if (!np) { if (!quiet) toast('Restore happens in the app itself, from the App Store or Google Play.'); return; }
    np.restorePurchases().then(function () { return np.getPurchases(); }).then(function (purchases) {
      if (ownsFullApp(purchases)) {
        setUnlocked(true);
        if (!quiet) { closeSheets(); toast('Full app restored — welcome back.'); }
      } else if (!quiet) {
        toast('No full-app purchase was found for this store account.');
      }
    }).catch(function () {
      if (!quiet) toast('Restore could not reach the store — try again with a connection.');
    });
  }

  /* ---- presentation ---- */
  function renderStatus() {
    var status = $('fullapp-status'), actions = $('fullapp-actions'), note = $('fullapp-note');
    if (!status) return;
    if (isUnlocked()) {
      status.textContent = 'Full app — unlocked. Every set, every line.';
      if (actions) actions.style.display = 'none';
      if (note) note.textContent = 'One price, once — paid. Every future update included.';
    } else {
      status.textContent = 'Free — three dozen sets on one line.';
      if (actions) actions.style.display = '';
      if (note) note.textContent = 'One price, once. No subscription — every future update included.';
    }
    var buyBtn = $('btn-unlock'), sheetBuy = $('btn-unlock-buy');
    if (buyBtn) buyBtn.textContent = 'Unlock the full app — ' + priceText;
    if (sheetBuy) sheetBuy.textContent = 'Unlock the full app — ' + priceText;
  }
  function refreshPrice() {
    var np = plugin();
    if (!np || !np.getProducts) return;
    np.getProducts({ productIdentifiers: [PRODUCT_ID], productType: 'inapp' }).then(function (r) {
      var list = (r && r.products) || [];
      var p = list[0];
      if (!p) return;
      var t = p.priceString || p.localizedPrice || (typeof p.price === 'number' ? '$' + p.price.toFixed(2) : null);
      if (t) { priceText = t; renderStatus(); }
    }).catch(function () {});
  }

  function init() {
    var b1 = $('btn-unlock'); if (b1) b1.onclick = buy;
    var b2 = $('btn-unlock-buy'); if (b2) b2.onclick = buy;
    var r1 = $('btn-restore-purchase'); if (r1) r1.onclick = function () { restore(false); };
    var r2 = $('btn-unlock-restore'); if (r2) r2.onclick = function () { restore(false); };
    renderStatus();
    refreshPrice();
    /* dismissing the unlock sheet (its ×, or the scrim) sets down any
       import waiting at its door */
    var scrim = $('scrim');
    if (scrim) scrim.addEventListener('click', sheetDismissed);
    var sheetX = document.querySelector('#sheet-unlock [data-close]');
    if (sheetX) sheetX.addEventListener('click', sheetDismissed);
    /* a trapper who bought, then deleted and reinstalled, should find
       the app already unlocked — read the store's entitlements quietly,
       once, at first launch; this can never raise a sign-in prompt */
    if (isUnlocked()) finishEntitlement();
    else checkEntitlementQuiet();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  return {
    isUnlocked: isUnlocked,
    gateNewSet: gateNewSet,
    gateNewLine: gateNewLine,
    gateImportLine: gateImportLine,
    gatePinImport: gatePinImport,
    gateBackupRestore: gateBackupRestore,
    buy: buy,
    restore: restore,
    renderStatus: renderStatus,
    PRODUCT_ID: PRODUCT_ID,
    FREE_SETS: FREE_SETS,
    _test: {
      setUnlocked: setUnlocked, setsOnLine: setsOnLine, ownsFullApp: ownsFullApp,
      finishEntitlement: finishEntitlement,
      hasPending: function () { return !!pendingProceed; },
      sheetDismissed: sheetDismissed
    }
  };
})();
