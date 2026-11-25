/* ================= Keyboard regime (2026-11-25, Tanner: "Change the
   keyboard regime") =================
   The pan era is over. On iOS, WKWebView does not resize the layout
   viewport for the keyboard — it PANS its outer scroll view to center
   the focused field, and that pan is what flung fields off-screen,
   parked the tab bar mid-screen over a void (Builds 74/80), and beat
   every timed scroll correction the app threw at it (the native side
   resolves ~900–1100 ms after keyboardWillShow — capacitor-keyboard
   #24 — so corrections at 120/450/950 ms were steering a moving
   frame). The production pattern for a fixed shell with inner
   scrollers (external research 2026-11-25, recommendation #1;
   capacitor #1366; DrawerDeck's keyboard guide; Ionic's
   scroll-padding doctrine) is PREVENTION, in four parts:

   1. resize:"none" in the Capacitor config (native package) — the
      plugin never resizes the WebView; the keyboard OVERLAYS.
   2. Keyboard.setScroll({isDisabled:true}) — the plugin sets the
      WebView scroll view's scrollEnabled=NO and installs itself as
      its delegate, forcing contentOffset back to CGPointZero on
      every scroll event (installed 8.0.6 source, Keyboard.m). The
      outer pan is zeroed at the source; the only scrollers left are
      the app's own inner panes and sheet bodies.
   3. The keyboard is an INSET, never a shell resize. The single
      height source is keyboardWillShow's keyboardHeight, published
      as the --kb-inset CSS variable. While the keyboard is open,
      fitAppHeight() (app.js) is FROZEN — the shell keeps its
      keyboard-closed height — and the inner scrollers wear the
      inset as padding-bottom + scroll-padding-bottom (styles.css,
      html.kb-open rules). No second height source, no double
      compensation.
   4. The tab bar hides while the keyboard is open (styles.css) —
      under an overlay keyboard it could only ever be covered or
      displaced; it returns on keyboardWillHide.

   iOS only: Android's WebView resizes honestly under
   windowSoftInputMode="adjustResize" (MainActivity), so the inset
   regime stays out of its way — applying both would double-count.
   In a plain browser there is no plugin and this file no-ops; the
   bench drives it through a stub of the plugin's JS surface. */
(function () {
  var root = document.documentElement;
  window.__ofKbOpen = false;
  var kb = null;
  try {
    if (window.Capacitor && Capacitor.Plugins && Capacitor.Plugins.Keyboard) kb = Capacitor.Plugins.Keyboard;
    if (!kb) return;
    if (Capacitor.getPlatform && Capacitor.getPlatform() !== 'ios') return;
  } catch (e) { return; }
  try { kb.setScroll({ isDisabled: true }); } catch (e) { /* older plugin: config + inset still apply */ }
  function onShow(info) {
    var h = 0;
    try { h = Math.round((info && info.keyboardHeight) || 0); } catch (e) { /* keep 0 */ }
    window.__ofKbOpen = true;
    root.style.setProperty('--kb-inset', h + 'px');
    root.classList.add('kb-open');
    /* One deliberate inner scroll, event-driven (not a timed
       correction): with the inset now published, the scroller's
       scroll-padding-bottom makes the browser's own scrollIntoView
       math stop the focused field above the keyboard line. Only the
       inner pane/sheet body can move — the outer scroll view is
       frozen by setScroll. Fields already resting clear don't move
       (block:'nearest'). */
    try {
      var el = document.activeElement;
      if (el && el !== document.body && el.closest && el.closest('.sheet-body, .scroll')) {
        el.scrollIntoView({ block: 'nearest' });
      }
    } catch (e) { /* the inset alone still clears the field on the next manual scroll */ }
  }
  function onHide() {
    window.__ofKbOpen = false;
    root.style.setProperty('--kb-inset', '0px');
    root.classList.remove('kb-open');
    /* The freeze lifts: resync the shell to the true height now the
       keyboard is gone (a rotation while open lands here too). */
    try { if (typeof window.fitAppHeight === 'function') window.fitAppHeight(); } catch (e) { /* noop */ }
  }
  try {
    kb.addListener('keyboardWillShow', onShow);
    kb.addListener('keyboardWillHide', onHide);
  } catch (e) { /* listeners are the inset's only source; without them the shell simply never freezes */ }
})();
