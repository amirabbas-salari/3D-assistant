/**
 * Sam — Floating Widget
 * Usage:
 *   <script src="https://sam.yourdomain.com/widget.js"
 *           data-sam-url="https://sam.yourdomain.com"
 *           data-sam-position="bottom-right"
 *           data-sam-color="#244f91"
 *           async></script>
 *
 * The script creates a round launcher button and a popup iframe. All
 * secrets stay on sam.yourdomain.com; the host site never sees them.
 */
(function () {
  var currentScript = document.currentScript;
  // Allow manual init: SamWidget.init({ url, position, color })
  function getConfig() {
    var ds = (currentScript && currentScript.dataset) || {};
    var w = window.SamWidgetConfig || {};
    return {
      url: (w.url || ds.samUrl || '').replace(/\/$/, '') || null,
      position: w.position || ds.samPosition || 'bottom-right',
      color: w.color || ds.samColor || '#244f91',
      greeting: w.greeting || ds.samGreeting || '',
    };
  }

  function init(userConfig) {
    if (userConfig) {
      window.SamWidgetConfig = Object.assign({}, window.SamWidgetConfig || {}, userConfig);
      currentScript = null; // force reading from window.SamWidgetConfig
    }
    var cfg = getConfig();
    if (!cfg.url) {
      console.warn('[sam-widget] data-sam-url missing. Example: <script src=".../widget.js" data-sam-url="https://sam.yourdomain.com">');
      return;
    }
    if (document.getElementById('sam-widget-root')) return; // already mounted

    var isLeft = cfg.position === 'bottom-left';
    var side = isLeft ? 'left' : 'right';

    // --- Styles ---
    var style = document.createElement('style');
    style.textContent = [
      '#sam-widget-root{position:fixed;bottom:20px;' + side + ':20px;z-index:999999;font-family:Vazirmatn,Tahoma,sans-serif;direction:rtl}',
      '#sam-widget-btn{width:60px;height:60px;border-radius:50%;border:0;cursor:pointer;display:flex;align-items:center;justify-content:center;box-shadow:0 4px 16px rgba(0,0,0,.25);color:#fff;transition:transform .15s,box-shadow .15s}',
      '#sam-widget-btn:hover{transform:scale(1.06);box-shadow:0 6px 20px rgba(0,0,0,.3)}',
      '#sam-widget-btn svg{width:28px;height:28px}',
      '#sam-widget-panel{position:fixed;bottom:90px;' + side + ':20px;width:420px;height:min(72vh,640px);max-height:640px;background:#fff;border:1px solid #dbe1e7;border-radius:16px;box-shadow:0 12px 40px rgba(0,0,0,.18);overflow:hidden;display:none;flex-direction:column}',
      '#sam-widget-panel.sam-open{display:flex}',
      '#sam-widget-panel iframe{flex:1;width:100%;height:100%;border:0}',
      '#sam-widget-header{height:48px;display:flex;align-items:center;justify-content:space-between;padding:0 14px;color:#fff;flex-shrink:0}',
      '#sam-widget-header strong{font-size:13px}',
      '#sam-widget-header small{font-size:10px;opacity:.85}',
      '#sam-widget-close{background:rgba(255,255,255,.2);border:0;color:#fff;width:30px;height:30px;border-radius:50%;cursor:pointer;display:grid;place-items:center}',
      '#sam-widget-close:hover{background:rgba(255,255,255,.32)}',
      '@media(max-width:480px){#sam-widget-panel{inset:0;width:auto;height:auto;max-height:none;border-radius:0;bottom:0;top:0;left:0;right:0}#sam-widget-root{bottom:16px;' + side + ':16px}}',
    ].join('');
    document.head.appendChild(style);

    // --- Root ---
    var root = document.createElement('div');
    root.id = 'sam-widget-root';

    // --- Launcher button ---
    var btn = document.createElement('button');
    btn.id = 'sam-widget-btn';
    btn.setAttribute('aria-label', 'گفتگو با دستیار سام');
    btn.style.background = cfg.color;
    btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-1.9.5 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7A8.38 8.38 0 0 1 3 11.5 8.5 8.5 0 0 1 11.5 3a8.38 8.38 0 0 1 5.7 1.9L21 11.5z"/><path d="M8 12h8"/><path d="M8 8h5"/></svg>';
    root.appendChild(btn);

    // --- Panel ---
    var panel = document.createElement('div');
    panel.id = 'sam-widget-panel';
    panel.innerHTML =
      '<div id="sam-widget-header" style="background:' + esc(cfg.color) + '">' +
      '  <div><strong>سام — مشاور مارکتینگ</strong><small>آنلاین · پاسخ فوری</small></div>' +
      '  <button id="sam-widget-close" aria-label="بستن">✕</button>' +
      '</div>' +
      '<iframe src="' + esc(cfg.url) + '" allow="microphone; camera; autoplay" title="دستیار سام"></iframe>';
    // panel is outside root to allow full-screen on mobile
    document.body.appendChild(panel);
    document.body.appendChild(root);

    var open = false;
    function toggle() {
      open = !open;
      panel.classList.toggle('sam-open', open);
      btn.innerHTML = open
        ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M18 6L6 18"/><path d="M6 6l12 12"/></svg>'
        : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-1.9.5 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7A8.38 8.38 0 0 1 3 11.5 8.5 8.5 0 0 1 11.5 3a8.38 8.38 0 0 1 5.7 1.9L21 11.5z"/><path d="M8 12h8"/><path d="M8 8h5"/></svg>';
    }
    btn.addEventListener('click', toggle);
    panel.querySelector('#sam-widget-close').addEventListener('click', toggle);

    // expose API
    window.SamWidget = {
      open: function () { if (!open) toggle(); },
      close: function () { if (open) toggle(); },
      toggle: toggle,
      init: init,
    };

    function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;'); }
  }

  // Auto-init on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { init(); });
  } else {
    init();
  }

  // Allow manual init
  window.SamWidget = window.SamWidget || {};
  window.SamWidget.init = init;
})();
