/* eChipHub Assistant - chat bubble for any page.
   Add before </body>:
     <script src="https://YOUR-BOT-ADDRESS/static/widget.js" defer></script>
   Optional attributes: data-api="https://YOUR-BOT-ADDRESS"  data-title="eChipHub Assistant"  data-open="true"
   Everything lives in a Shadow DOM, so the website's CSS cannot break it (and it cannot break the website). */
(function () {
  "use strict";
  if (window.__echiphubAssistant) return;
  window.__echiphubAssistant = true;

  var script = document.currentScript || document.querySelector('script[src*="widget.js"]');
  var API = ((script && script.getAttribute("data-api")) || (script ? new URL(script.src).origin : location.origin)).replace(/\/$/, "");
  var TITLE = (script && script.getAttribute("data-title")) || "eChipHub Assistant";
  var START_OPEN = script && script.getAttribute("data-open") === "true";
  var STORE = "echiphub-assistant-v1";
  var SUGGESTIONS = ["Which workshops are coming up?", "What is the ChipCraft course?", "How do I get access to the PDK?"];

  var css = `
  :host { all: initial; }
  * { box-sizing: border-box; }
  .wrap { --die:#0E5C46; --die-2:#0A4636; --pad:#C9A227; --ink:#18231F; --muted:#56655F; --paper:#FFFFFF;
          --mist:#EAF1EE; --line:#D5E0DB; --danger:#A33A2B;
          font: 14.5px/1.5 "Segoe UI", system-ui, -apple-system, Roboto, "Noto Sans", Arial, sans-serif;
          color: var(--ink); position: fixed; right: 20px; bottom: 20px; z-index: 2147483000; }
  @media (prefers-color-scheme: dark) {
    .wrap { --ink:#E3EDE9; --muted:#9DB0A8; --paper:#13201C; --mist:#1E302A; --line:#2A3F38; --danger:#E08A7C; }
  }
  button { font: inherit; cursor: pointer; }
  :focus-visible { outline: 2px solid var(--pad); outline-offset: 2px; }

  /* the launcher: a small chip package with pins */
  .chip { position: relative; width: 58px; height: 58px; border: 0; border-radius: 9px; background: var(--die);
          color: #fff; display: grid; place-items: center; box-shadow: 0 6px 18px rgba(14,92,70,.35); }
  .chip::before, .chip::after { content: ""; position: absolute; top: 12px; bottom: 12px; width: 6px;
          background: repeating-linear-gradient(to bottom, var(--pad) 0 4px, transparent 4px 9px); }
  .chip::before { left: -6px; } .chip::after { right: -6px; }
  .chip .notch { position: absolute; top: 6px; left: 6px; width: 7px; height: 7px; border-radius: 50%;
          background: rgba(255,255,255,.35); }
  .chip:hover { background: var(--die-2); }
  .open .chip { display: none; }

  .panel { display: none; width: 384px; height: min(620px, calc(100vh - 40px)); background: var(--paper);
           border: 1px solid var(--line); border-radius: 14px; overflow: hidden; flex-direction: column;
           box-shadow: 0 18px 50px rgba(10,40,30,.28); }
  .open .panel { display: flex; animation: rise .18s ease-out; }
  @keyframes rise { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }
  @media (prefers-reduced-motion: reduce) { .open .panel { animation: none; } .spinner { animation: none; } }

  header { background: var(--die); color: #fff; padding: 12px 14px; display: flex; align-items: center; gap: 10px;
           border-bottom: 3px solid var(--pad); }
  header .t { flex: 1; min-width: 0; }
  header b { display: block; font-size: 15px; font-weight: 600; letter-spacing: .01em; }
  header small { opacity: .8; font-size: 12px; }
  header button { background: transparent; border: 0; color: #fff; width: 34px; height: 34px; border-radius: 8px;
                  display: grid; place-items: center; }
  header button:hover { background: rgba(255,255,255,.12); }

  .log { flex: 1; overflow-y: auto; padding: 14px; display: flex; flex-direction: column; gap: 12px;
         scroll-behavior: smooth; }
  .msg { max-width: 88%; padding: 9px 12px; border-radius: 12px; word-wrap: break-word; overflow-wrap: anywhere; }
  .me { align-self: flex-end; background: var(--die); color: #fff; border-bottom-right-radius: 4px; }
  .bot { align-self: flex-start; background: var(--mist); border-bottom-left-radius: 4px; }
  .bot p { margin: 0 0 6px; } .bot p:last-child { margin-bottom: 0; }
  .bot ul, .bot ol { margin: 4px 0 6px 18px; padding: 0; }
  .bot a { color: var(--die); font-weight: 600; text-underline-offset: 2px; }
  @media (prefers-color-scheme: dark) { .bot a { color: #7FD1B3; } }
  sup a { text-decoration: none; font-size: 11px; background: var(--pad); color: #1d1600 !important;
          border-radius: 4px; padding: 0 4px; margin-left: 1px; }
  .src { margin-top: 8px; padding-top: 7px; border-top: 1px dashed var(--line); font-size: 12.5px; }
  .src div { color: var(--muted); margin-bottom: 2px; }
  .src a { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; }
  .fb { display: flex; gap: 6px; margin-top: 6px; align-items: center; }
  .fb-me { justify-content: flex-end; margin-top: 4px; }
  .fb button[data-v] { border: 1px solid var(--line); background: var(--paper); color: var(--muted); border-radius: 6px;
                       padding: 2px 8px; font-size: 12px; }
  .fb button[data-v][aria-pressed="true"] { border-color: var(--die); color: var(--die); }
  button.copy-btn, .copy-btn {
    border: none !important; background: transparent !important; box-shadow: none !important;
    outline: none !important; border-radius: 0 !important; padding: 0 !important; margin: 0;
    width: auto !important; height: auto !important; min-width: 0 !important; min-height: 0 !important;
    display: inline-flex !important; align-items: center; justify-content: center;
    cursor: pointer; color: var(--muted); opacity: .65; transition: opacity .15s, color .15s;
    line-height: 1; flex-shrink: 0;
  }
  button.copy-btn:hover, button.copy-btn.copied {
    border: none !important; background: transparent !important; box-shadow: none !important;
    opacity: 1; color: var(--die);
  }
  @media (prefers-color-scheme: dark) {
    button.copy-btn:hover, button.copy-btn.copied { color: #7FD1B3; }
  }
  .me button.copy-btn {
    color: #fff; opacity: .65; border: none !important; background: transparent !important; box-shadow: none !important;
  }
  .me button.copy-btn:hover, .me button.copy-btn.copied {
    color: #fff; opacity: 1; border: none !important; background: transparent !important; box-shadow: none !important;
  }
  .me .txt { white-space: pre-wrap; word-break: break-word; }
  .err { color: var(--danger); }
  .typing { display: inline-flex; align-items: center; justify-content: center; padding: 2px 0; }
  .spinner { width: 20px; height: 20px; color: var(--muted); animation: spin .8s steps(8, start) infinite; display: block; }
  @keyframes spin { to { transform: rotate(360deg); } }

  .intro { color: var(--muted); }
  .sugg { display: flex; flex-direction: column; gap: 6px; margin-top: 4px; }
  .sugg button { text-align: left; background: var(--paper); border: 1px solid var(--line); color: var(--ink);
                 border-radius: 10px; padding: 8px 11px; }
  .sugg button:hover { border-color: var(--die); }

  form { display: flex; gap: 8px; padding: 10px; border-top: 1px solid var(--line); background: var(--paper); }
  textarea { flex: 1; resize: none; border: 1px solid var(--line); border-radius: 10px; padding: 9px 11px;
             font: inherit; color: var(--ink); background: var(--paper); max-height: 110px; min-height: 40px; }
  textarea:focus { outline: none; border-color: var(--die); box-shadow: 0 0 0 2px rgba(201,162,39,.45); }
  form button { border: 0; background: var(--die); color: #fff; border-radius: 10px; width: 44px;
                display: grid; place-items: center; }
  form button:disabled { opacity: .5; cursor: default; }
  .note { font-size: 11.5px; color: var(--muted); padding: 0 12px 9px; background: var(--paper); }

  @media (max-width: 480px) {
    .wrap { right: 12px; bottom: 12px; }
    .open.wrap { inset: 0; right: 0; bottom: 0; }
    .panel { width: 100vw; height: 100dvh; border-radius: 0; border: 0; }
  }`;

  var ICON_CHAT = '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/></svg>';
  var ICON_X = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>';
  var ICON_NEW = '<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/></svg>';
  var ICON_SEND = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>';
  var ICON_COPY = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
  var ICON_CHECK = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>';
  var ICON_SPINNER = '<svg class="spinner" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" aria-hidden="true">' +
    '<line x1="12" y1="2.5" x2="12" y2="6.8" opacity="1"/>' +
    '<line x1="12" y1="2.5" x2="12" y2="6.8" transform="rotate(45 12 12)" opacity="0.875"/>' +
    '<line x1="12" y1="2.5" x2="12" y2="6.8" transform="rotate(90 12 12)" opacity="0.75"/>' +
    '<line x1="12" y1="2.5" x2="12" y2="6.8" transform="rotate(135 12 12)" opacity="0.625"/>' +
    '<line x1="12" y1="2.5" x2="12" y2="6.8" transform="rotate(180 12 12)" opacity="0.5"/>' +
    '<line x1="12" y1="2.5" x2="12" y2="6.8" transform="rotate(225 12 12)" opacity="0.375"/>' +
    '<line x1="12" y1="2.5" x2="12" y2="6.8" transform="rotate(270 12 12)" opacity="0.25"/>' +
    '<line x1="12" y1="2.5" x2="12" y2="6.8" transform="rotate(315 12 12)" opacity="0.125"/>' +
  '</svg>';

  var host = document.createElement("div");
  host.id = "echiphub-assistant";
  document.body.appendChild(host);
  var root = host.attachShadow({ mode: "open" });
  root.innerHTML = '<style>' + css + '</style>' +
    '<div class="wrap">' +
      '<button class="chip" type="button" aria-label="Open ' + esc(TITLE) + '"><span class="notch"></span>' + ICON_CHAT + '</button>' +
      '<section class="panel" role="dialog" aria-label="' + esc(TITLE) + '">' +
        '<header><div class="t"><b>' + esc(TITLE) + '</b></div>' +
          '<button type="button" class="new" aria-label="Start a new chat" title="New chat">' + ICON_NEW + '</button>' +
          '<button type="button" class="close" aria-label="Close chat" title="Close">' + ICON_X + '</button></header>' +
        '<div class="log" aria-live="polite"></div>' +
        '<form><textarea rows="1" maxlength="500" placeholder="Ask about courses, workshops, labs…" aria-label="Your question"></textarea>' +
          '<button type="submit" aria-label="Send">' + ICON_SEND + '</button></form>' +
        '<div class="note">Answers can be incomplete. Check important details on the linked page.</div>' +
      '</section></div>';

  var wrap = root.querySelector(".wrap"), log = root.querySelector(".log"), form = root.querySelector("form"),
      input = root.querySelector("textarea"), sendBtn = form.querySelector("button");
  var state = load(), busy = false;

  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function load() { try { return JSON.parse(sessionStorage.getItem(STORE)) || { open: false, msgs: [] }; } catch (e) { return { open: false, msgs: [] }; } }
  function save() { try { state.msgs = state.msgs.slice(-30); sessionStorage.setItem(STORE, JSON.stringify(state)); } catch (e) {} }

  /* small, safe markdown: escapes everything first, then allows links (http/https only), bold and lists */
  function md(text, sources) {
    var urls = {};
    (sources || []).forEach(function (s) { urls[s.n] = s.url; });
    var lines = esc(text || "").split(/\n/), html = "", list = null;
    function inline(s) {
      s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
      s = s.replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
      s = s.replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, '$1<a href="$2" target="_blank" rel="noopener">$2</a>');
      s = s.replace(/\[(\d{1,2})\]/g, function (m, n) {
        return urls[n] ? '<sup><a href="' + urls[n] + '" target="_blank" rel="noopener" title="Source ' + n + '">' + n + '</a></sup>' : "";
      });
      return s;
    }
    lines.forEach(function (l) {
      var m = l.match(/^\s*([-*•]|\d+[.)])\s+(.*)$/);
      if (m) {
        var t = /\d/.test(m[1]) ? "ol" : "ul";
        if (list !== t) { if (list) html += "</" + list + ">"; html += "<" + t + ">"; list = t; }
        html += "<li>" + inline(m[2]) + "</li>";
      } else {
        if (list) { html += "</" + list + ">"; list = null; }
        if (l.trim()) html += "<p>" + inline(l.replace(/^#+\s*/, "")) + "</p>";
      }
    });
    if (list) html += "</" + list + ">";
    return html;
  }

  function scroll() { log.scrollTop = log.scrollHeight; }

  function copyText(text, btn) {
    function done() {
      btn.classList.add("copied");
      btn.innerHTML = ICON_CHECK;
      btn.setAttribute("title", "Copied!");
      btn.setAttribute("aria-label", "Copied!");
      setTimeout(function () {
        btn.classList.remove("copied");
        btn.innerHTML = ICON_COPY;
        btn.setAttribute("title", "Copy");
        btn.setAttribute("aria-label", "Copy");
      }, 1500);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(function () {
        if (fallbackCopy(text)) done();
      });
    } else if (fallbackCopy(text)) {
      done();
    }
  }

  function fallbackCopy(text) {
    try {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      ta.style.top = "0";
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      var ok = document.execCommand("copy");
      document.body.removeChild(ta);
      return ok;
    } catch (e) {
      return false;
    }
  }

  function bubble(m) {
    var el = document.createElement("div");
    el.className = "msg " + (m.role === "user" ? "me" : "bot");
    if (m.role === "user") paintUser(el, m);
    else paintBot(el, m);
    log.appendChild(el);
    return el;
  }

  function paintUser(el, m) {
    el.innerHTML = '<div class="txt">' + esc(m.content) + '</div>' +
      '<div class="fb fb-me"><button type="button" class="copy-btn" title="Copy" aria-label="Copy">' + ICON_COPY + '</button></div>';
    var copyBtn = el.querySelector(".copy-btn");
    if (copyBtn) {
      copyBtn.addEventListener("click", function () { copyText(m.content, copyBtn); });
    }
  }

  function paintBot(el, m) {
    var html = m.error ? '<p class="err">' + esc(m.content) + "</p>" : md(m.content, m.sources);
    if (m.sources && m.sources.length) {
      html += '<div class="src"><div>Sources</div>' + m.sources.map(function (s) {
        return '<a href="' + esc(s.url) + '" target="_blank" rel="noopener">' + s.n + ". " + esc(s.title || s.url) + "</a>";
      }).join("") + "</div>";
    }
    if (m.content) {
      html += '<div class="fb">' +
              '<button type="button" class="copy-btn" title="Copy" aria-label="Copy">' + ICON_COPY + '</button>';
      if (m.id && !m.error) {
        html += '<button type="button" data-v="1" aria-pressed="' + (m.fb === 1) + '">Helpful</button>' +
                '<button type="button" data-v="0" aria-pressed="' + (m.fb === 0) + '">Not helpful</button>';
      }
      html += '</div>';
    }
    el.innerHTML = html;
    var copyBtn = el.querySelector(".copy-btn");
    if (copyBtn) {
      copyBtn.addEventListener("click", function () { copyText(m.content, copyBtn); });
    }
    el.querySelectorAll(".fb button[data-v]").forEach(function (b) {
      b.addEventListener("click", function () {
        m.fb = +b.getAttribute("data-v"); save(); paintBot(el, m);
        fetch(API + "/api/feedback", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: m.id, helpful: m.fb === 1 }) }).catch(function () {});
      });
    });
  }

  function intro() {
    var el = document.createElement("div");
    el.className = "msg bot";
    el.innerHTML = '<p>Hello! I answer questions using the eChipHub websites: courses, workshops and bootcamps, labs, the PDK, events and the community.</p>' +
      '<div class="sugg">' + SUGGESTIONS.map(function (s) { return '<button type="button">' + esc(s) + "</button>"; }).join("") + "</div>";
    el.querySelectorAll(".sugg button").forEach(function (b) { b.addEventListener("click", function () { ask(b.textContent); }); });
    log.appendChild(el);
  }

  function render() {
    log.innerHTML = "";
    if (!state.msgs.length) intro();
    state.msgs.forEach(bubble);
    scroll();
  }

  function setOpen(v) {
    state.open = v; save();
    wrap.classList.toggle("open", v);
    if (v) { render(); setTimeout(function () { input.focus(); }, 50); }
    else root.querySelector(".chip").focus();
  }

  function errorText(status, detail) {
    if (status === 429) return detail || "Too many questions in a minute. Please wait a moment and try again.";
    if (status === 503) return detail || "The assistant is being updated. Please try again in a few minutes.";
    if (status === 0) return "Could not reach the assistant. Check your internet connection and try again.";
    return detail || "Something went wrong. Please try again.";
  }

  async function ask(text) {
    text = (text || "").trim();
    if (!text || busy) return;
    busy = true; sendBtn.disabled = true;
    var history = state.msgs.filter(function (m) { return !m.error; }).slice(-4)
      .map(function (m) { return { role: m.role, content: m.content.slice(0, 1500) }; });
    if (!state.msgs.length) log.innerHTML = "";
    var mine = { role: "user", content: text };
    state.msgs.push(mine); bubble(mine);
    var bot = { role: "assistant", content: "", sources: [] };
    var el = document.createElement("div");
    el.className = "msg bot";
    el.innerHTML = '<span class="typing" aria-label="Writing an answer">' + ICON_SPINNER + '</span>';
    log.appendChild(el); scroll();
    try {
      var res = await fetch(API + "/api/chat/stream", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, history: history }) });
      if (!res.ok || !res.body) {
        var detail = ""; try { detail = (await res.json()).detail; } catch (e) {}
        throw { status: res.status, detail: detail };
      }
      var reader = res.body.getReader(), dec = new TextDecoder(), buf = "";
      while (true) {
        var r = await reader.read();
        if (r.done) break;
        buf += dec.decode(r.value, { stream: true });
        var parts = buf.split("\n\n"); buf = parts.pop();
        parts.forEach(function (block) {
          var ev = (block.match(/^event: (.*)$/m) || [])[1], data = (block.match(/^data: (.*)$/m) || [])[1];
          if (!ev || !data) return;
          data = JSON.parse(data);
          if (ev === "token") { bot.content += data.t; paintBot(el, bot); scroll(); }
          else if (ev === "done") { bot.id = data.id; bot.sources = data.sources || []; }
          else if (ev === "error") { bot.error = !bot.content; if (!bot.content) bot.content = data.message; }
        });
      }
      if (!bot.content) throw { status: 500 };
    } catch (e) {
      bot.error = true; bot.content = errorText(e && e.status !== undefined ? e.status : 0, e && e.detail);
    }
    paintBot(el, bot); state.msgs.push(bot); save(); scroll();
    busy = false; sendBtn.disabled = false; input.focus();
  }

  root.querySelector(".chip").addEventListener("click", function () { setOpen(true); });
  root.querySelector(".close").addEventListener("click", function () { setOpen(false); });
  root.querySelector(".new").addEventListener("click", function () { state.msgs = []; save(); render(); input.focus(); });
  form.addEventListener("submit", function (e) { e.preventDefault(); var t = input.value; input.value = ""; input.style.height = ""; ask(t); });
  input.addEventListener("keydown", function (e) { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });
  input.addEventListener("input", function () { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 110) + "px"; });
  wrap.addEventListener("keydown", function (e) { if (e.key === "Escape" && state.open) setOpen(false); });

  if (state.open || START_OPEN) setOpen(true);
})();
