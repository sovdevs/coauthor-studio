"use strict";

// ── Dark mode ───────────────────────────────────────────────────────────────

(function () {
  const DARK_KEY = "af_dark_mode";
  const btn      = document.getElementById("dark-toggle");

  function applyDark(on) {
    document.documentElement.classList.toggle("dark", on);
    if (btn) btn.textContent = on ? "◑ light" : "◑ dark";
  }

  applyDark(localStorage.getItem(DARK_KEY) === "true");

  if (btn) {
    btn.addEventListener("click", function () {
      const next = !document.documentElement.classList.contains("dark");
      localStorage.setItem(DARK_KEY, next ? "true" : "false");
      applyDark(next);
    });
  }
})();

// ── Typewriter sound layer ──────────────────────────────────────────────────

const sounds = (function () {
  const STORAGE_KEY = "af_sounds_enabled";

  let ctx         = null;
  let initPromise = null;
  const buffers   = {};

  // Initialise AudioContext and load buffers on first play() call.
  // Must happen inside a user-gesture handler so the context isn't suspended.
  function init() {
    if (initPromise) return initPromise;
    initPromise = (async () => {
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      await Promise.all([
        _loadBuffer("key",    "/static/sounds/return.wav"),
        _loadBuffer("return", "/static/sounds/key1.wav"),
      ]);
    })();
    return initPromise;
  }

  async function _loadBuffer(name, url) {
    try {
      const res = await fetch(url);
      const raw = await res.arrayBuffer();
      buffers[name] = await ctx.decodeAudioData(raw);
    } catch (_) {}
  }

  async function play(name) {
    if (!enabled()) return;
    try {
      await init();
      if (ctx.state === "suspended") await ctx.resume();
      const buf = buffers[name];
      if (!buf) return;
      const src  = ctx.createBufferSource();
      src.buffer = buf;
      const gain = ctx.createGain();
      gain.gain.value = 0.5;
      src.connect(gain);
      gain.connect(ctx.destination);
      src.start(0);
    } catch (_) {}
  }

  function enabled()        { return localStorage.getItem(STORAGE_KEY) === "true"; }
  function setEnabled(val)  { localStorage.setItem(STORAGE_KEY, val ? "true" : "false"); }

  return { play, enabled, setEnabled };
})();

// ── Main app ────────────────────────────────────────────────────────────────

(function () {
  const form            = document.getElementById("sentence-form");
  const field           = document.getElementById("sentence-field");
  const statusEl        = document.getElementById("submit-status");
  const btn             = document.getElementById("submit-btn");
  const manuscriptEl    = document.getElementById("manuscript-content");
  const commandOutput   = document.getElementById("command-output");
  const chapterSelect   = document.getElementById("chapter-select");
  const newChapterBtn   = document.getElementById("new-chapter-btn");
  const soundToggle     = document.getElementById("sound-toggle");

  if (!form) return;

  const projectId       = window.AF_PROJECT_ID;
  const chaptersEnabled = window.AF_CHAPTERS_ENABLED === true;

  // ── Sound toggle init ─────────────────────────────────────────────────────
  if (soundToggle) {
    soundToggle.checked = sounds.enabled();
    soundToggle.addEventListener("change", function () {
      sounds.setEnabled(soundToggle.checked);
    });
  }

  // ── Keyboard sounds ───────────────────────────────────────────────────────
  field.addEventListener("keydown", function (e) {
    // Cmd+Enter / Ctrl+Enter — submit + return sound
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      sounds.play("return");
      form.requestSubmit();   // fires a real, cancelable submit event
      return;
    }
    // Plain Enter — newline + key sound (carriage return feel)
    if (e.key === "Enter") {
      sounds.play("key");
      return;
    }
    // Printable characters and space — key sound
    if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
      sounds.play("key");
    }
  });

  form.addEventListener("submit", async function (e) {
    e.preventDefault();

    const text = field.value.trim();
    if (!text) return;

    btn.disabled = true;
    statusEl.textContent = "…";
    hideCommandOutput();

    try {
      const body = new FormData();
      body.append("sentence", text);

      const res  = await fetch(`/project/${projectId}/submit`, { method: "POST", body });
      const data = await res.json();

      if (!res.ok || data.error) {
        setStatus("Error: " + (data.error || res.statusText), true);
        return;
      }

      updateManuscript(data.finalized);

      if (data.kind === "command") {
        showCommandOutput(data.output, data.error);
        setStatus("", false);
      } else {
        field.value = "";
        setStatus("Saved (" + data.sentence_id + ")", false);
        setTimeout(() => setStatus("", false), 3000);
      }

      if (chaptersEnabled && data.current_chapter) {
        updateChapterUI(data.current_chapter);
      }

      field.focus();

    } catch (err) {
      setStatus("Network error.", true);
    } finally {
      btn.disabled = false;
    }
  });

  // Chapter select change → submit a :c command
  if (chapterSelect) {
    chapterSelect.addEventListener("change", async function () {
      const chapterId = chapterSelect.value;
      const body = new FormData();
      body.append("sentence", `:c ${chapterId}`);
      try {
        const res  = await fetch(`/project/${projectId}/submit`, { method: "POST", body });
        const data = await res.json();
        if (data.finalized) updateManuscript(data.finalized);
        if (data.current_chapter) updateChapterUI(data.current_chapter);
      } catch (_) {}
    });
  }

  // New chapter button
  if (newChapterBtn) {
    newChapterBtn.addEventListener("click", async function () {
      const title = prompt("New chapter title (leave blank for default):", "");
      if (title === null) return;
      const body = new FormData();
      body.append("title", title);
      try {
        const res  = await fetch(`/project/${projectId}/chapter/new`, { method: "POST", body });
        const data = await res.json();
        if (data.chapter_id) window.location.reload();
      } catch (_) {}
    });
  }

  // ── Helpers ────────────────────────────────────────────────────────────────

  function updateManuscript(segments) {
    if (!segments || !manuscriptEl) return;
    if (!segments.length) {
      manuscriptEl.innerHTML = '<div class="manuscript-empty">(no segments yet)</div>';
      return;
    }
    manuscriptEl.innerHTML = segments
      .map(s => `<div class="manuscript-segment">${escapeHtml(s)}</div>`)
      .join("");
  }

  function showCommandOutput(text, isError) {
    commandOutput.textContent = text;
    commandOutput.className = "command-output" + (isError ? " command-error" : "");
    commandOutput.hidden = false;
  }

  function hideCommandOutput() {
    commandOutput.hidden = true;
  }

  function setStatus(msg, isError) {
    statusEl.textContent = msg;
    statusEl.className = "submit-status" + (isError ? " submit-error" : "");
  }

  function updateChapterUI(chapterId) {
    if (chapterSelect) chapterSelect.value = chapterId;
  }

  function escapeHtml(str) {
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

}());
