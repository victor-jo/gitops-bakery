// Vanilla JS controller for the phone UI: profile, genres, poster marking and weekend picks
"use strict";

const VIEWERS = [
  { id: "me", label: "🙋 나", name: "나" },
  { id: "wife", label: "🙋‍♀️ 아내", name: "아내" },
];
const PAGE = 30;
const PICKS_PAGE = 20;
const FETCH_TIMEOUT_MS = 15000;

const screen = document.getElementById("screen");
const bar = document.getElementById("bar");
let viewer = null;
let observer = null;

function saved() {
  try { return localStorage.getItem("viewer"); } catch (e) { return null; }
}
function genresDone(id) {
  try { return localStorage.getItem("genres_" + id) === "1"; } catch (e) { return false; }
}
function markGenresDone(id) {
  try { localStorage.setItem("genres_" + id, "1"); } catch (e) { /* storage unavailable */ }
}
function save(id) {
  try { localStorage.setItem("viewer", id); } catch (e) { /* storage unavailable */ }
}

// Small DOM helper: el("div", {class: "x"}, child, "text")
function el(tag, attrs, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const kid of kids) node.append(kid);
  return node;
}

async function api(path, body) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), FETCH_TIMEOUT_MS);
  try {
    const res = await fetch(path, body === undefined ? { signal: ctl.signal } : {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: ctl.signal,
    });
    if (!res.ok) throw new Error("http " + res.status);
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

function stopObserver() {
  if (observer) { observer.disconnect(); observer = null; }
}

function show(...nodes) {
  stopObserver();
  screen.replaceChildren(...nodes);
  window.scrollTo(0, 0);
}

// Put one retry box into a container, replacing any earlier one.
function showError(container, retry) {
  container.querySelectorAll(":scope > .err").forEach((n) => n.remove());
  container.append(errorBox(() => { container.querySelectorAll(":scope > .err").forEach((n) => n.remove()); retry(); }));
}

function errorBox(retry) {
  return el("div", { class: "err" },
    el("p", {}, "연결에 문제가 있어요. 잠시 후 다시 시도해 주세요."),
    el("button", { class: "primary", type: "button", onclick: retry }, "다시 시도"));
}

// Run a loader with a loading line; on failure show the Korean error with a retry button.
async function guarded(run) {
  show(el("p", { class: "msg" }, "불러오는 중…"));
  try {
    await run();
  } catch (e) {
    show(errorBox(() => guarded(run)));
  }
}

function poster(m, container) {
  const box = container || el("div", { class: "poster" });
  const placeholder = () => box.replaceChildren(el("div", { class: "ph" }, m.title));
  if (m.poster_url) {
    const img = el("img", { src: m.poster_url, alt: m.title, loading: "lazy" });
    img.addEventListener("error", placeholder);
    box.append(img);
  } else {
    placeholder();
  }
  return box;
}

// ---- 1. profile ----
function profileScreen() {
  bar.hidden = true;
  show(
    el("h1", {}, "누가 보나요?"),
    ...VIEWERS.map((v) => el("button", {
      class: "block", type: "button", onclick: () => choose(v.id, genresDone(v.id) ? picksScreen : genresScreen),
    }, v.label)));
}

function choose(id, next) {
  viewer = id;
  save(id);
  bar.hidden = false;
  next();
}

// ---- 2. genres ----
function genresScreen() {
  if (!viewer) { profileScreen(); return; }
  guarded(async () => {
    const genres = await api("/api/genres");
    const picked = new Set();
    const next = el("button", { class: "primary block", type: "button", disabled: "" }, "다음");
    const chips = genres.map((g) => {
      const chip = el("button", { class: "chip", type: "button", "aria-pressed": "false" }, g.label);
      chip.addEventListener("click", () => {
        const on = !picked.has(g.id);
        if (on) picked.add(g.id); else picked.delete(g.id);
        chip.classList.toggle("on", on);
        chip.setAttribute("aria-pressed", String(on));
        next.disabled = picked.size === 0;
      });
      return chip;
    });
    next.addEventListener("click", () => {
      guarded(async () => {
        await api("/api/viewer/" + viewer + "/genres", { genres: [...picked] });
        markGenresDone(viewer);
        onboardScreen();
      });
    });
    show(
      el("h1", {}, "어떤 장르를 좋아하세요?"),
      el("p", { class: "hint" }, "여러 개 고를 수 있어요."),
      el("div", { class: "chips" }, ...chips),
      next,
      el("button", { class: "block", type: "button", onclick: () => picksScreen() }, "추천 보기"));
  });
}

// ---- 3. poster grid ----
function onboardScreen() {
  if (!viewer) { profileScreen(); return; }
  const grid = el("div", { class: "grid" });
  const status = el("div", {});
  const sentinel = el("div", { class: "sentinel" });
  const done = el("div", { class: "bottom" },
    el("button", { class: "primary", type: "button", onclick: () => picksScreen() }, "추천 보기"));
  let loading = false;
  let exhausted = false;
  let open = null;

  function select(card) {
    if (open && open !== card) open.querySelector(".votes")?.remove();
    open = card;
    if (card.querySelector(".votes")) return;
    const vote = (liked) => async (ev) => {
      if (ev) ev.stopPropagation();
      try {
        await api("/api/mark", { viewer, movie_key: card.dataset.key, liked, source: "onboarding" });
        card.querySelector(".votes")?.remove();
        card.querySelector(".tag")?.remove();
        card.classList.add("seen");
        card.append(el("span", { class: "tag" }, liked ? "👍" : "👎"));
        if (open === card) open = null;
      } catch (e) {
        showError(status, () => vote(liked)());
      }
    };
    card.append(el("div", { class: "votes" },
      el("button", { type: "button", "aria-label": "좋았어요", onclick: vote(true) }, "👍"),
      el("button", { type: "button", "aria-label": "별로였어요", onclick: vote(false) }, "👎")));
  }

  async function more() {
    if (loading || exhausted) return;
    loading = true;
    status.replaceChildren(el("p", { class: "msg" }, "불러오는 중…"));
    try {
      // The server leaves marked movies out of its list, so the offset counts only the unmarked posters shown
      const offset = grid.querySelectorAll(".poster:not(.seen)").length;
      const items = await api("/api/onboarding?viewer=" + viewer + "&offset=" + offset + "&limit=" + PAGE);
      const shown = new Set([...grid.children].map((c) => c.dataset.key));
      for (const m of items) {
        if (shown.has(m.movie_key)) continue;
        const card = el("div", { class: "poster", "data-key": m.movie_key, role: "button", tabindex: "0" });
        poster(m, card);
        card.addEventListener("click", () => select(card));
        grid.append(card);
      }
      if (items.length === 0) {
        exhausted = true;
        status.replaceChildren(el("p", { class: "msg" },
          grid.children.length ? "더 이상 없어요." : "고른 장르의 영화가 없어요. 장르를 바꿔 보세요."));
      } else {
        status.replaceChildren();
      }
    } catch (e) {
      status.replaceChildren(errorBox(() => { status.replaceChildren(); more(); }));
    } finally {
      loading = false;
    }
  }

  show(
    el("h1", {}, "본 영화를 눌러 주세요"),
    el("p", { class: "hint" }, "본 것만 눌러 👍/👎를 고르고, 안 본 건 그냥 지나가세요."),
    grid, status, sentinel, done);
  observer = new IntersectionObserver((entries) => {
    if (entries.some((e) => e.isIntersecting)) more();
  }, { rootMargin: "400px" });
  observer.observe(sentinel);
}

// ---- 4. weekend picks ----
// Picks newest first, then the popular fallback under an '인기' divider, loaded page by page while scrolling.
function picksScreen() {
  if (!viewer) { profileScreen(); return; }
  const list = el("div", {});
  const status = el("div", {});
  const sentinel = el("div", { class: "sentinel" });
  let loading = false;
  let exhausted = false;

  async function more() {
    if (loading || exhausted) return;
    loading = true;
    status.replaceChildren(el("p", { class: "msg" }, "불러오는 중…"));
    try {
      // A movie marked watched leaves the server's list, so the offset counts only the cards still in it
      const offset = list.querySelectorAll(".pick:not(.watched)").length;
      const items = await api("/api/recommendations?offset=" + offset + "&limit=" + PICKS_PAGE);
      const shown = new Set([...list.querySelectorAll(".pick")].map((c) => c.dataset.key));
      for (const m of items) {
        if (shown.has(m.movie_key)) continue;
        if (m.source === "popular" && !list.querySelector(".divider")) {
          list.append(el("h2", { class: "divider" }, "인기"));
        }
        list.append(pickCard(m));
      }
      exhausted = items.length < PICKS_PAGE;
      if (exhausted && !list.querySelector(".pick")) {
        status.replaceChildren(
          el("p", { class: "msg" }, "아직 추천할 영화가 없어요. 장르를 고르고 본 영화를 표시해 보세요."),
          el("button", { class: "primary block", type: "button", onclick: () => genresScreen() }, "장르 고르기"));
      } else {
        status.replaceChildren(...(exhausted ? [el("p", { class: "msg" }, "더 이상 없어요.")] : []));
      }
    } catch (e) {
      status.replaceChildren(errorBox(() => { status.replaceChildren(); more(); }));
    } finally {
      loading = false;
    }
    // Observing again reports the sentinel's current state, so a page too short to fill the screen loads the next
    if (!exhausted && observer === io) { io.unobserve(sentinel); io.observe(sentinel); }
  }

  show(el("h1", {}, "이번 주말 후보"), list, status, sentinel);
  const io = new IntersectionObserver((entries) => {
    if (entries.some((e) => e.isIntersecting)) more();
  }, { rootMargin: "400px" });
  observer = io;
  io.observe(sentinel);
}

function pickCard(m) {
  const badges = el("div", {}, ...m.services.map((s) => el("span", { class: "badge" }, s)));
  if (m.new_this_week) badges.append(el("span", { class: "badge new" }, "이번 주 새로 올라옴"));
  const actions = el("div", { class: "actions" });
  const watched = el("button", { type: "button" }, "같이 봤어요");
  const card = el("section", { class: "pick", "data-key": m.movie_key });
  const send = async () => {
    watched.disabled = true;
    try {
      await api("/api/watched", { movie_key: m.movie_key });
      card.classList.add("watched");
      rateWatched(actions, m);
    } catch (e) {
      watched.disabled = false;
      showError(actions, send);
    }
  };
  watched.addEventListener("click", send);
  actions.append(watched);
  card.append(
    poster(m),
    el("div", { class: "info" }, el("h2", {}, m.title), badges, el("p", { class: "reason" }, m.reason)),
    actions);
  return card;
}

// After "watched": one 👍/👎 row per person; refresh the picks once both have answered.
function rateWatched(actions, m) {
  let answered = 0;
  actions.replaceChildren(...VIEWERS.map((v) => {
    const row = el("div", { class: "who" }, el("span", {}, v.label));
    const buttons = [true, false].map((liked) => {
      const b = el("button", { type: "button", "aria-label": v.name + (liked ? " 좋았어요" : " 별로였어요") },
        liked ? "👍" : "👎");
      b.addEventListener("click", async () => {
        buttons.forEach((x) => { x.disabled = true; });
        try {
          await api("/api/mark", { viewer: v.id, movie_key: m.movie_key, liked, source: "watched" });
          b.classList.add("picked");
          answered += 1;
          if (answered === VIEWERS.length) picksScreen();
        } catch (e) {
          buttons.forEach((x) => { x.disabled = false; });
          row.append(el("small", {}, "저장 실패, 다시 눌러 주세요."));
        }
      });
      return b;
    });
    row.append(...buttons);
    return row;
  }), el("button", { type: "button", onclick: () => picksScreen() }, "평가 없이 목록 새로고침"));
}

// ---- wiring ----
document.getElementById("btn-switch").addEventListener("click", profileScreen);
document.getElementById("btn-genres").addEventListener("click", genresScreen);

(function start() {
  const id = saved();
  if (VIEWERS.some((v) => v.id === id)) choose(id, picksScreen); else profileScreen();
})();
