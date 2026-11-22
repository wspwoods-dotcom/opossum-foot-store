/* Opossum Foot — store build: the full-app unlock (2026-11-22).
   The consumer model, locked 2026-10-19: free is three dozen sets on one
   line, free forever; the full app is $14.99 one time, no subscription,
   every future update included. Billing runs through the stores' own
   systems via @capgo/native-purchases (free plugin) — the app holds no
   account and no payment details, same promise as everything else here.
   In a plain browser there is no store to buy from: the gates still hold
   and the buttons explain where unlocking happens. Existing records are
   never taken away — the gates only stand at the doors that ADD a set
   past the free measure, a second line, or an imported second line.
   Restoring your own backup is never gated. */
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
  function gateImportLine() {
    if (isUnlocked()) return true;
    if (lineCount() >= 1) { openUnlockSheet('line'); return false; }
    return true;
  }

  function openUnlockSheet(reason) {
    var copy = $('unlock-copy');
    if (copy) {
      copy.textContent = reason === 'line'
        ? 'A second line is part of the full app. Free covers one line — three dozen sets on it, forever.'
        : 'That is three dozen sets on this line — the free tier\u2019s full measure.';
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
    /* a trapper who bought, then deleted and reinstalled, should find the
       app already unlocked — ask the store quietly, once, at first launch */
    if (plugin() && !isUnlocked()) restore(true);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  return {
    isUnlocked: isUnlocked,
    gateNewSet: gateNewSet,
    gateNewLine: gateNewLine,
    gateImportLine: gateImportLine,
    buy: buy,
    restore: restore,
    renderStatus: renderStatus,
    PRODUCT_ID: PRODUCT_ID,
    FREE_SETS: FREE_SETS,
    _test: { setUnlocked: setUnlocked, setsOnLine: setsOnLine, ownsFullApp: ownsFullApp }
  };
})();
