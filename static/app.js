const CATEGORY_ORDER = [
  "ones", "twos", "threes", "fours", "fives", "sixes",
  "two_of_a_kind", "three_of_a_kind", "four_of_a_kind", "two_pairs",
  "lower_straight", "upper_straight", "full_house", "chance", "yatzee",
];
const UPPER_CATEGORIES = new Set(["ones", "twos", "threes", "fours", "fives", "sixes"]);
// Face value behind each upper category -- the bonus pace for a filled box
// is 3x its face (three-of-a-kind average), used for the upper-total delta.
const UPPER_FACE = { ones: 1, twos: 2, threes: 3, fours: 4, fives: 5, sixes: 6 };
const FACE_PIPS = {
  1: ["c"],
  2: ["tl", "br"],
  3: ["tl", "c", "br"],
  4: ["tl", "tr", "bl", "br"],
  5: ["tl", "tr", "c", "bl", "br"],
  6: ["tl", "tr", "ml", "mr", "bl", "br"],
};
const LABELS = {
  ones: "Ones", twos: "Twos", threes: "Threes", fours: "Fours", fives: "Fives", sixes: "Sixes",
  two_of_a_kind: "Two of a Kind", three_of_a_kind: "Three of a Kind", four_of_a_kind: "Four of a Kind",
  two_pairs: "Two Pairs", lower_straight: "Small Straight", upper_straight: "Large Straight",
  full_house: "Full House", chance: "Chance", yatzee: "Yatzy",
};

// Groups of dice faces used to draw each category as a little dice pictogram,
// the way a real Scandinavian Yatzy scorecard shows categories (a separate
// group per "cluster", e.g. full house = a triplet group + a pair group).
const CATEGORY_ICON_GROUPS = {
  ones: [[1]],
  twos: [[2]],
  threes: [[3]],
  fours: [[4]],
  fives: [[5]],
  sixes: [[6]],
  two_of_a_kind: [[5, 5]],
  three_of_a_kind: [[4, 4, 4]],
  four_of_a_kind: [[3, 3, 3, 3]],
  two_pairs: [[2, 2], [5, 5]],
  lower_straight: [[1, 2, 3, 4, 5]],
  upper_straight: [[2, 3, 4, 5, 6]],
  full_house: [[3, 3, 3], [5, 5]],
  chance: [[2, 4, 6, 1, 3]],
  yatzee: [[6, 6, 6, 6, 6]],
};

const ROLL_ANIMATION_MS = 450;
const ROLL_TICK_MS = 90;

let session = null;       // latest server-reported state (session.dice is server-canonical order)
let held = new Set();     // client-local selection of on-screen slot indices currently marked "keep"
let displayDice = [];     // on-screen dice values, one per slot -- decoupled from the server's
                           // array order so held dice can stay put in their slot across a reroll

const el = (id) => document.getElementById(id);

function randomFace() {
  return 1 + Math.floor(Math.random() * 6);
}

function setDieFace(dieEl, face) {
  dieEl.innerHTML = "";
  FACE_PIPS[face].forEach((pos) => {
    const pip = document.createElement("span");
    pip.className = `pip ${pos}`;
    dieEl.appendChild(pip);
  });
}

function buildMiniDie(face) {
  const d = document.createElement("div");
  d.className = "mini-die";
  FACE_PIPS[face].forEach((pos) => {
    const pip = document.createElement("span");
    pip.className = `pip ${pos}`;
    d.appendChild(pip);
  });
  return d;
}

function buildCategoryIcon(cat) {
  const wrap = document.createElement("div");
  wrap.className = "dice-icon-group";
  wrap.title = LABELS[cat];
  CATEGORY_ICON_GROUPS[cat].forEach((group, gi) => {
    if (gi > 0) {
      const sep = document.createElement("div");
      sep.className = "dice-icon-sep";
      wrap.appendChild(sep);
    }
    group.forEach((face) => wrap.appendChild(buildMiniDie(face)));
  });
  return wrap;
}

// Rapidly cycles the given die elements through random faces for a fixed
// duration, so the reroll reads as a dice-roll rather than an instant swap.
function animateRolling(dieEls, animateIdx) {
  return new Promise((resolve) => {
    const interval = setInterval(() => {
      animateIdx.forEach((i) => setDieFace(dieEls[i], randomFace()));
    }, ROLL_TICK_MS);
    setTimeout(() => {
      clearInterval(interval);
      resolve();
    }, ROLL_ANIMATION_MS);
  });
}

async function api(path, body, method = "POST") {
  const opts = { method };
  if (body) {
    opts.headers = { "Content-Type": "application/json" };
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "request failed");
  }
  return res.json();
}

// Finds, for each value in keptValues, one matching (not-yet-used) index in
// newDice. Used to translate "these values were kept" into the index
// positions the server's own (freshly re-sorted) dice array expects.
function matchKeptIndices(newDice, keptValues) {
  const pool = [...newDice];
  const usedIndices = new Set();
  const result = new Set();
  for (const v of keptValues) {
    const idx = pool.findIndex((x, i) => x === v && !usedIndices.has(i));
    if (idx !== -1) {
      usedIndices.add(idx);
      result.add(idx);
    }
  }
  return result;
}

// values minus subtract, as multisets (e.g. [3,3,5] minus [3] -> [3,5]).
function multisetDiff(values, subtract) {
  const remaining = [...values];
  for (const v of subtract) {
    const idx = remaining.indexOf(v);
    if (idx !== -1) remaining.splice(idx, 1);
  }
  return remaining;
}

let currentNickname = "";

async function newGame() {
  held.clear();
  displayDice = [];
  el("final-modal").hidden = true;
  clearDiceFeedback();
  session = await api("/api/new_game", { nickname: currentNickname });
  render();
}

function startWithNickname(nickname) {
  currentNickname = nickname;
  localStorage.setItem("nickname", nickname);
  el("nickname-modal").hidden = true;
  newGame();
}

async function rollOrReroll() {
  const rollBtn = el("roll-btn");
  rollBtn.disabled = true;
  const row = el("dice-row");
  row.innerHTML = "";

  try {
    if (session.dice.length === 0) {
      clearDiceFeedback();
      const dieEls = [];
      for (let i = 0; i < 5; i++) {
        const d = document.createElement("div");
        d.className = "die rolling";
        setDieFace(d, randomFace());
        row.appendChild(d);
        dieEls.push(d);
      }
      const animation = animateRolling(dieEls, [0, 1, 2, 3, 4]);
      const { state } = await api("/api/roll", { session_id: session.session_id });
      session = state;
      held.clear();
      displayDice = [...session.dice]; // nothing held yet, order doesn't matter
      await animation;
    } else {
      // Keep held dice in their exact on-screen slot across the reroll: work
      // entirely in displayDice for rendering, and only translate to the
      // server's own (re-sorted) array when sending keep_indices.
      const keptValues = [...held].map((i) => displayDice[i]);
      const dieEls = [];
      const animateIdx = [];
      displayDice.forEach((face, i) => {
        const d = document.createElement("div");
        const isHeld = held.has(i);
        d.className = "die" + (isHeld ? " held" : " rolling");
        setDieFace(d, face);
        row.appendChild(d);
        dieEls.push(d);
        if (!isHeld) animateIdx.push(i);
      });
      const animation = animateRolling(dieEls, animateIdx);
      const serverKeepIndices = matchKeptIndices(session.dice, keptValues);
      // Judge the move and show the verdict as soon as it's known, rather
      // than waiting for the dice animation to finish settling.
      const { judgment, state } = await api("/api/hold", {
        session_id: session.session_id,
        keep_indices: [...serverKeepIndices],
      });
      session = state;

      // Rebuild displayDice: held slots keep their existing value (that die
      // wasn't rerolled), and the freshly-rolled values fill the other
      // slots -- `held` itself doesn't need to change, since the slots
      // didn't move.
      const newRolledValues = multisetDiff(session.dice, keptValues);
      displayDice = displayDice.map((face, i) => (held.has(i) ? face : newRolledValues.shift()));

      popDiceFeedback(judgment);
      await animation;
    }
    render();
  } catch (e) {
    alert(e.message);
  }
}

async function fillCategory(category) {
  try {
    const { judgment, state, final } = await api("/api/fill", { session_id: session.session_id, category });
    session = state;
    held.clear();
    render();
    if (judgment.optimal) {
      popRowBadge(category, "Optimal!", "optimal");
    } else {
      popRowBadge(judgment.optimal_category, "Optimal was here", "suboptimal");
    }
    if (final) showFinal(final);
  } catch (e) {
    alert(e.message);
  }
}

function toggleHold(i) {
  if (session.rerolls_remaining === 0) return;
  if (held.has(i)) held.delete(i); else held.add(i);
  renderDice();
}

const DICE_FEEDBACK_POP_MS = 2000;
const FEEDBACK_POP_MS = 2600;
const FEEDBACK_FADE_MS = 250;

let diceFeedbackTimer = null;

function clearDiceFeedback() {
  clearTimeout(diceFeedbackTimer);
  const badge = el("dice-feedback");
  badge.classList.remove("visible");
  badge.textContent = "";
}

// Pops "Optimal!" / "Optimal was [...]" over the Roll button, then fades
// out on its own after 2s. Positioned absolutely (see CSS) so its text
// never affects the roll box's size.
function popDiceFeedback(judgment) {
  clearTimeout(diceFeedbackTimer);
  const badge = el("dice-feedback");
  badge.textContent = judgment.optimal
    ? "Optimal!"
    : `Optimal was [${judgment.optimal_hold_dice.join(", ") || "nothing"}]`;
  badge.className = "dice-feedback " + (judgment.optimal ? "optimal" : "suboptimal") + " visible";
  diceFeedbackTimer = setTimeout(() => {
    badge.classList.remove("visible");
  }, DICE_FEEDBACK_POP_MS);
}

// Pops a small badge next to a scorecard row's Fill button (right side of
// that category), then removes itself after a few seconds. `cat` is which
// row to attach to -- the category just filled when optimal, or the
// category that should have been filled instead when suboptimal.
function popRowBadge(cat, text, kind) {
  const cell = document.querySelector(`tr[data-cat="${cat}"] .action-inner`);
  if (!cell) return;
  const badge = document.createElement("span");
  badge.className = `row-feedback ${kind}`;
  badge.textContent = text;
  cell.prepend(badge);
  requestAnimationFrame(() => badge.classList.add("visible"));
  setTimeout(() => {
    badge.classList.remove("visible");
    setTimeout(() => badge.remove(), FEEDBACK_FADE_MS);
  }, FEEDBACK_POP_MS);
}

function formatScoreLoss(loss) {
  return loss < 0.005 ? "Best" : `−${loss.toFixed(2)}`;
}

function buildTooltipRow(iconEl, scoreLoss, isChosen) {
  const row = document.createElement("div");
  row.className = "tooltip-row" + (isChosen ? " chosen" : "");
  const iconWrap = document.createElement("div");
  iconWrap.className = "tooltip-icon";
  iconWrap.appendChild(iconEl);
  const lossSpan = document.createElement("span");
  lossSpan.className = "tooltip-loss";
  lossSpan.textContent = formatScoreLoss(scoreLoss);
  row.append(iconWrap, lossSpan);
  if (isChosen) {
    const tag = document.createElement("span");
    tag.className = "tooltip-tag";
    tag.textContent = "Your pick";
    row.appendChild(tag);
  }
  return row;
}

function buildHoldIcon(dice) {
  const wrap = document.createElement("div");
  wrap.className = "dice-icon-group";
  if (dice.length === 0) {
    const span = document.createElement("span");
    span.className = "tooltip-empty-hold";
    span.textContent = "Reroll all";
    wrap.appendChild(span);
  } else {
    dice.forEach((face) => wrap.appendChild(buildMiniDie(face)));
  }
  return wrap;
}

// The tooltip is a single shared element appended directly to <body> (see
// index.html), positioned with `position: fixed` via getBoundingClientRect.
// It deliberately does NOT live inside the scrollable modal: a tooltip
// nested in a scrolling ancestor gets clipped by that ancestor's overflow
// (real problem for the topmost table rows, which have no room above them
// inside the modal) -- escaping the modal via a "portal" element sidesteps
// that entirely, and also stops the (still-laid-out-when-hidden) tooltip
// from inflating the table wrapper's scrollable content box every row.
function showCellTooltip(anchorEl, entries, iconBuilder) {
  const tip = el("cell-tooltip");
  tip.innerHTML = "";
  entries.forEach((entry) => {
    tip.appendChild(buildTooltipRow(iconBuilder(entry), entry.score_loss, entry.is_chosen));
  });
  tip.hidden = false;

  const rect = anchorEl.getBoundingClientRect();
  const tipRect = tip.getBoundingClientRect();
  // Bound the tooltip to the modal card itself, not just the viewport --
  // otherwise it can visually poke out above/beside the popup even though
  // it's technically still on-screen.
  const modalEl = anchorEl.closest(".modal");
  const bounds = modalEl
    ? modalEl.getBoundingClientRect()
    : { top: 0, bottom: window.innerHeight, left: 0, right: window.innerWidth };
  const gap = 8;
  let top = rect.top - tipRect.height - gap;
  if (top < bounds.top + gap) top = rect.bottom + gap; // not enough room above -> flip below
  let left = rect.left + rect.width / 2 - tipRect.width / 2;
  left = Math.max(bounds.left + gap, Math.min(left, bounds.right - tipRect.width - gap));

  tip.style.top = `${top}px`;
  tip.style.left = `${left}px`;
}

function hideCellTooltip() {
  el("cell-tooltip").hidden = true;
}

function buildBreakdownCell(entry, topList, iconBuilder) {
  const td = document.createElement("td");
  td.className = "breakdown-cell";
  const inner = document.createElement("div");
  inner.className = "breakdown-cell-inner";
  const marker = document.createElement("span");
  marker.className = "marker " + (entry.optimal ? "marker-good" : "marker-bad");
  marker.textContent = entry.optimal ? "✓" : "✗";
  inner.appendChild(marker);
  inner.addEventListener("mouseenter", () => showCellTooltip(inner, topList, iconBuilder));
  inner.addEventListener("mouseleave", hideCellTooltip);
  td.appendChild(inner);
  return td;
}

function renderBreakdownTable(history) {
  const body = el("breakdown-body");
  body.innerHTML = "";
  history.forEach((turn) => {
    const tr = document.createElement("tr");
    const roundTd = document.createElement("td");
    roundTd.className = "breakdown-round";
    roundTd.textContent = turn.turn;
    tr.appendChild(roundTd);
    tr.appendChild(buildBreakdownCell(turn.hold1, turn.hold1.top_holds, (h) => buildHoldIcon(h.dice)));
    tr.appendChild(buildBreakdownCell(turn.hold2, turn.hold2.top_holds, (h) => buildHoldIcon(h.dice)));
    tr.appendChild(buildBreakdownCell(turn.fill, turn.fill.top_fills, (f) => buildCategoryIcon(f.category)));
    body.appendChild(tr);
  });
}

function showFinal(final) {
  el("final-modal").hidden = false;
  el("final-score-value").textContent = final.score;
  const pct = session.accuracy * 100;
  const accuracyEl = el("final-accuracy-value");
  accuracyEl.textContent = `${pct.toFixed(1)}%`;
  accuracyEl.style.color = accuracyColor(pct);
  el("final-lost-value").textContent = session.ev_lost_total.toFixed(1);
  el("final-rank-value").textContent = final.ranks
    ? `#${final.ranks.accuracy_rank}/${final.ranks.total_games}`
    : "—";
  renderBreakdownTable(final.history);
}

let currentHiscoresSort = "accuracy";
const HISCORES_PAGE_SIZE = 20;
let currentHiscoresLimit = HISCORES_PAGE_SIZE;

function formatDuration(seconds) {
  const total = Math.round(seconds);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function formatDate(isoString) {
  return new Date(isoString).toLocaleDateString(undefined, {
    year: "numeric", month: "short", day: "numeric",
  });
}

function renderHiscores(rows) {
  const body = el("hiscores-body");
  body.innerHTML = "";
  if (rows.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 6;
    td.className = "hiscores-empty";
    td.textContent = "No games recorded yet.";
    tr.appendChild(td);
    body.appendChild(tr);
    return;
  }
  rows.forEach((row, i) => {
    const rank = i + 1;
    const tr = document.createElement("tr");
    if (rank <= 3) tr.classList.add(`rank-${rank}`);

    const rankTd = document.createElement("td");
    rankTd.className = "hiscores-rank";
    rankTd.textContent = rank;

    const nameTd = document.createElement("td");
    nameTd.textContent = row.nickname;

    const scoreTd = document.createElement("td");
    scoreTd.className = "hiscores-score";
    scoreTd.textContent = row.total_score;

    const pct = row.accuracy * 100;
    const accTd = document.createElement("td");
    accTd.className = "hiscores-accuracy";
    accTd.textContent = `${pct.toFixed(1)}%`;
    accTd.style.color = accuracyColor(pct);

    const timeTd = document.createElement("td");
    timeTd.textContent = formatDuration(row.completion_seconds);

    const dateTd = document.createElement("td");
    dateTd.textContent = formatDate(row.played_at);

    tr.append(rankTd, nameTd, scoreTd, accTd, timeTd, dateTd);
    body.appendChild(tr);
  });
}

async function fetchAndRenderHiscores() {
  const { rows } = await api(
    `/api/hiscores?sort=${currentHiscoresSort}&limit=${currentHiscoresLimit}`,
    null,
    "GET",
  );
  renderHiscores(rows);
  // If we got back fewer rows than we asked for, we've hit the end.
  el("hiscores-more-btn").hidden = rows.length < currentHiscoresLimit;
}

async function openHiscores(sort) {
  currentHiscoresSort = sort;
  currentHiscoresLimit = HISCORES_PAGE_SIZE;
  el("sort-accuracy-btn").classList.toggle("active", sort === "accuracy");
  el("sort-score-btn").classList.toggle("active", sort === "score");
  el("hiscores-modal").hidden = false;
  try {
    await fetchAndRenderHiscores();
  } catch (e) {
    alert(e.message);
  }
}

async function loadMoreHiscores() {
  currentHiscoresLimit += HISCORES_PAGE_SIZE;
  try {
    await fetchAndRenderHiscores();
  } catch (e) {
    alert(e.message);
  }
}

// Red at/below 50%, amber around 80%, green at 100%, linearly interpolated
// between those anchors.
const ACCURACY_COLOR_STOPS = [
  { pct: 50, rgb: [201, 42, 42] },   // --bad
  { pct: 80, rgb: [202, 160, 0] },   // amber
  { pct: 100, rgb: [26, 138, 74] },  // --good
];

function accuracyColor(pct) {
  const stops = ACCURACY_COLOR_STOPS;
  if (pct <= stops[0].pct) return `rgb(${stops[0].rgb.join(",")})`;
  if (pct >= stops[stops.length - 1].pct) return `rgb(${stops[stops.length - 1].rgb.join(",")})`;
  for (let i = 0; i < stops.length - 1; i++) {
    const a = stops[i];
    const b = stops[i + 1];
    if (pct >= a.pct && pct <= b.pct) {
      const t = (pct - a.pct) / (b.pct - a.pct);
      const rgb = a.rgb.map((v, j) => Math.round(v + (b.rgb[j] - v) * t));
      return `rgb(${rgb.join(",")})`;
    }
  }
  return `rgb(${stops[stops.length - 1].rgb.join(",")})`;
}

function renderStats() {
  const el_ = el("stat-accuracy");
  if (session.moves_total === 0) {
    el_.textContent = "NaN";
    el_.style.color = "var(--muted)";
  } else {
    const pct = session.accuracy * 100;
    el_.textContent = `${pct.toFixed(1)}% (${session.moves_optimal}/${session.moves_total})`;
    el_.style.color = accuracyColor(pct);
  }
}

function renderDice() {
  const row = el("dice-row");
  row.innerHTML = "";
  const notRolledYet = session.dice.length === 0;
  const locked = session.rerolls_remaining === 0 || session.game_over;

  displayDice.forEach((face, i) => {
    const d = document.createElement("div");
    d.className = "die" + (held.has(i) ? " held" : "") + (locked ? " locked" : "");
    setDieFace(d, face);
    if (!locked) d.onclick = () => toggleHold(i);
    row.appendChild(d);
  });

  const rollBtn = el("roll-btn");
  rollBtn.disabled = locked || session.game_over;
  rollBtn.textContent = "Roll";

  if (session.game_over) {
    el("rerolls-label").textContent = "Game over";
  } else if (notRolledYet) {
    // A truly empty element collapses its line box to 0 height in most
    // browsers, which would shrink the dice box; a non-breaking space
    // keeps the line (and the box's height) reserved but invisible.
    el("rerolls-label").textContent = " ";
  } else if (locked) {
    el("rerolls-label").textContent = "Pick a category to fill";
  } else {
    el("rerolls-label").textContent = `Rerolls remaining: ${session.rerolls_remaining}`;
  }
}

function summaryRow(label, value, className, extra) {
  const tr = document.createElement("tr");
  tr.className = className;
  const nameTd = document.createElement("td");
  nameTd.className = "cat-name";
  nameTd.textContent = label;
  const scoreTd = document.createElement("td");
  scoreTd.className = "cat-score";
  scoreTd.textContent = value;
  if (extra) {
    const extraSpan = document.createElement("span");
    extraSpan.className = "score-extra";
    extraSpan.textContent = ` (${extra})`;
    scoreTd.appendChild(extraSpan);
  }
  const actionTd = document.createElement("td");
  actionTd.className = "cat-action";
  tr.append(nameTd, scoreTd, actionTd);
  return tr;
}

function renderScorecard() {
  const upperBody = el("scorecard-upper");
  const summaryBody = el("scorecard-upper-summary");
  const lowerBody = el("scorecard-lower");
  const footerBody = el("scorecard-footer");
  upperBody.innerHTML = "";
  summaryBody.innerHTML = "";
  lowerBody.innerHTML = "";
  footerBody.innerHTML = "";
  const canFill = session.rerolls_remaining === 0 && session.dice.length > 0 && !session.game_over;

  CATEGORY_ORDER.forEach((cat) => {
    const tr = document.createElement("tr");
    tr.dataset.cat = cat;
    const isFilled = Object.prototype.hasOwnProperty.call(session.filled, cat);
    if (isFilled) tr.className = "filled";

    const nameTd = document.createElement("td");
    nameTd.className = "cat-name";
    nameTd.appendChild(buildCategoryIcon(cat));

    const scoreTd = document.createElement("td");
    scoreTd.className = "cat-score";
    if (isFilled) {
      scoreTd.textContent = session.filled[cat];
    } else if (canFill && cat in session.dice_category_preview) {
      scoreTd.textContent = session.dice_category_preview[cat];
    } else {
      scoreTd.textContent = "-";
    }

    const actionTd = document.createElement("td");
    actionTd.className = "cat-action";
    const actionInner = document.createElement("div");
    actionInner.className = "action-inner";
    // Always reserve the button's space, even when it's not clickable (or
    // the category is already filled), so the card never resizes based on
    // whether a Fill button happens to be usable right now.
    const btn = document.createElement("button");
    btn.className = "fill-btn";
    btn.textContent = "Fill";
    if (!isFilled && canFill) {
      btn.onclick = () => fillCategory(cat);
    } else {
      btn.disabled = true;
      btn.classList.add("fill-btn-placeholder");
    }
    actionInner.appendChild(btn);
    actionTd.appendChild(actionInner);

    tr.append(nameTd, scoreTd, actionTd);
    (UPPER_CATEGORIES.has(cat) ? upperBody : lowerBody).appendChild(tr);
  });

  const upperTotal = [...UPPER_CATEGORIES].reduce((sum, cat) => sum + (session.filled[cat] || 0), 0);
  // Pace vs. bonus, judged only against the boxes actually filled so far:
  // each filled upper box is compared to its own 3x-face-value target.
  const upperDelta = [...UPPER_CATEGORIES].reduce((sum, cat) => {
    if (!(cat in session.filled)) return sum;
    return sum + (session.filled[cat] - 3 * UPPER_FACE[cat]);
  }, 0);
  const deltaText = upperDelta >= 0 ? `+${upperDelta}` : `${upperDelta}`;
  const bonus = session.u >= 63 ? 50 : 0;
  summaryBody.appendChild(summaryRow("Upper Total", upperTotal, "summary-row", deltaText));
  summaryBody.appendChild(summaryRow("Bonus", bonus, "summary-row"));

  footerBody.appendChild(summaryRow("Total", session.total, "grand-total-row"));
}

// ---------------------------------------------------------------------------
// Game Analysis: a standalone what-if sandbox, fully decoupled from the live
// game session -- stateless backend (POST /api/analyze takes no session_id),
// starts blank every time, never reads or writes `session`. The one place it
// *does* look at `session` is to disable its own entry point while a game is
// in progress (see updateAnalysisButtonState) -- a deliberate deterrent
// against using it to look up the live game's answer, not a security
// boundary: a second tab could always describe the same board by hand.
// ---------------------------------------------------------------------------
let analysisOpen = {};
let analysisU = 0;
let analysisRerolls = 2;
let analysisDice = [1, 1, 1, 1, 1];
let analysisDraftCounts = [0, 0, 0, 0, 0, 0];

function updateAnalysisButtonState() {
  // Only block once dice are actually on the table (i.e. after the first
  // roll of a turn) -- not just because a game exists. Re-enables between
  // turns (dice reset to empty while awaiting the next roll) and once the
  // game is over (game_over is checked separately since a finished game's
  // `dice` is left showing the final turn's roll, not cleared to empty).
  const blocked = !!(session && !session.game_over && session.dice.length > 0);
  const btn = el("analysis-btn");
  btn.disabled = blocked;
  btn.title = blocked
    ? "Game Analysis is disabled while dice are in play — finish this turn's decision first."
    : "";
}

function openAnalysis() {
  analysisOpen = {};
  CATEGORY_ORDER.forEach((cat) => {
    analysisOpen[cat] = true;
  });
  analysisU = 0;
  analysisRerolls = 2;
  analysisDice = [1, 1, 1, 1, 1];
  el("analysis-u-input").value = "0";
  el("analysis-rerolls-value").textContent = "2";
  renderAnalysisScorecard();
  renderAnalysisDice();
  el("analysis-results-heading").textContent = "";
  el("analysis-results-list").innerHTML = "";
  el("analysis-modal").hidden = false;
}

function toggleAnalysisCategory(cat) {
  analysisOpen[cat] = !analysisOpen[cat];
  renderAnalysisScorecard();
}

function renderAnalysisScorecard() {
  const upperBody = el("analysis-scorecard-upper");
  const lowerBody = el("analysis-scorecard-lower");
  upperBody.innerHTML = "";
  lowerBody.innerHTML = "";

  CATEGORY_ORDER.forEach((cat) => {
    const tr = document.createElement("tr");
    tr.classList.toggle("closed", !analysisOpen[cat]);
    tr.onclick = () => toggleAnalysisCategory(cat);

    const nameTd = document.createElement("td");
    nameTd.className = "cat-name";
    nameTd.appendChild(buildCategoryIcon(cat));

    const statusTd = document.createElement("td");
    statusTd.className = "analysis-status";
    statusTd.textContent = analysisOpen[cat] ? "Open" : "Closed";

    tr.append(nameTd, statusTd);
    (UPPER_CATEGORIES.has(cat) ? upperBody : lowerBody).appendChild(tr);
  });
}

function renderAnalysisDice() {
  const row = el("analysis-dice-display");
  row.innerHTML = "";
  analysisDice.forEach((face) => {
    const d = document.createElement("div");
    d.className = "die";
    setDieFace(d, face);
    row.appendChild(d);
  });
}

function adjustAnalysisRerolls(delta) {
  analysisRerolls = Math.max(0, Math.min(2, analysisRerolls + delta));
  el("analysis-rerolls-value").textContent = analysisRerolls;
}

function commitAnalysisU(rewriteDisplay) {
  const input = el("analysis-u-input");
  let n = parseInt(input.value, 10);
  if (isNaN(n)) n = 0;
  n = Math.max(0, Math.min(63, n));
  analysisU = n;
  if (rewriteDisplay) input.value = String(n);
}

function openSetDicePopup() {
  analysisDraftCounts = [0, 0, 0, 0, 0, 0];
  analysisDice.forEach((face) => {
    analysisDraftCounts[face - 1]++;
  });
  renderSetDiceRows();
  el("set-dice-modal").hidden = false;
}

function adjustSetDiceCount(faceIdx, delta) {
  analysisDraftCounts[faceIdx] = Math.max(0, analysisDraftCounts[faceIdx] + delta);
  renderSetDiceRows();
}

function setDiceTotal() {
  return analysisDraftCounts.reduce((a, b) => a + b, 0);
}

function renderSetDiceRows() {
  const container = el("set-dice-rows");
  container.innerHTML = "";
  for (let faceIdx = 0; faceIdx < 6; faceIdx++) {
    const row = document.createElement("div");
    row.className = "set-dice-row";
    row.appendChild(buildMiniDie(faceIdx + 1));

    const stepper = document.createElement("div");
    stepper.className = "stepper";
    const minus = document.createElement("button");
    minus.className = "ghost";
    minus.textContent = "−";
    minus.onclick = () => adjustSetDiceCount(faceIdx, -1);
    const countSpan = document.createElement("span");
    countSpan.textContent = analysisDraftCounts[faceIdx];
    const plus = document.createElement("button");
    plus.className = "ghost";
    plus.textContent = "+";
    plus.onclick = () => adjustSetDiceCount(faceIdx, 1);
    stepper.append(minus, countSpan, plus);
    row.appendChild(stepper);

    container.appendChild(row);
  }
  updateSetDiceState();
}

function updateSetDiceState() {
  const total = setDiceTotal();
  el("set-dice-total").textContent = `Total: ${total}/5`;
  el("set-dice-confirm-btn").disabled = total !== 5;
}

function confirmSetDice() {
  analysisDice = analysisDraftCounts.flatMap((c, i) => Array(c).fill(i + 1));
  renderAnalysisDice();
  el("set-dice-modal").hidden = true;
}

function cancelSetDice() {
  el("set-dice-modal").hidden = true;
}

function buildAnalysisRow(iconEl, scoreLoss, isBest) {
  const row = document.createElement("div");
  row.className = "analysis-result-row" + (isBest ? " best" : "");
  const iconWrap = document.createElement("div");
  iconWrap.className = "analysis-result-icon";
  iconWrap.appendChild(iconEl);
  const lossSpan = document.createElement("span");
  lossSpan.className = "analysis-result-loss";
  lossSpan.textContent = formatScoreLoss(scoreLoss);
  row.append(iconWrap, lossSpan);
  return row;
}

function renderAnalysisResults(mode, results) {
  el("analysis-results-heading").textContent =
    mode === "holds" ? "Top 10 Holds by EV" : "All Open Categories by EV";
  const list = el("analysis-results-list");
  list.innerHTML = "";
  results.forEach((entry, i) => {
    const iconEl = mode === "holds" ? buildHoldIcon(entry.dice) : buildCategoryIcon(entry.category);
    list.appendChild(buildAnalysisRow(iconEl, entry.score_loss, i === 0));
  });
}

async function runAnalysis() {
  const open_categories = {};
  CATEGORY_ORDER.forEach((cat) => {
    open_categories[cat] = !!analysisOpen[cat];
  });
  try {
    const { mode, results } = await api("/api/analyze", {
      open_categories,
      u: analysisU,
      dice: analysisDice,
      rerolls_remaining: analysisRerolls,
    });
    renderAnalysisResults(mode, results);
  } catch (e) {
    alert(e.message);
  }
}

function render() {
  renderStats();
  renderDice();
  renderScorecard();
  updateAnalysisButtonState();
}

el("new-game-btn").onclick = newGame;
el("final-new-game-btn").onclick = newGame;
el("roll-btn").onclick = rollOrReroll;

el("nickname-form").onsubmit = (e) => {
  e.preventDefault();
  const nickname = el("nickname-input").value.trim();
  if (!nickname) return;
  startWithNickname(nickname);
};

el("hiscores-btn").onclick = () => openHiscores(currentHiscoresSort);
el("final-hiscores-btn").onclick = () => {
  el("final-modal").hidden = true;
  openHiscores(currentHiscoresSort);
};
el("hiscores-close-btn").onclick = () => {
  el("hiscores-modal").hidden = true;
};
el("sort-accuracy-btn").onclick = () => openHiscores("accuracy");
el("sort-score-btn").onclick = () => openHiscores("score");
el("hiscores-more-btn").onclick = loadMoreHiscores;

el("analysis-btn").onclick = openAnalysis;
el("analysis-close-btn").onclick = () => {
  el("analysis-modal").hidden = true;
};
el("analysis-run-btn").onclick = runAnalysis;
el("analysis-rerolls-minus").onclick = () => adjustAnalysisRerolls(-1);
el("analysis-rerolls-plus").onclick = () => adjustAnalysisRerolls(1);
el("analysis-u-input").oninput = () => {
  const input = el("analysis-u-input");
  input.value = input.value.replace(/\D/g, "").slice(0, 2);
  commitAnalysisU(false);
};
el("analysis-u-input").onchange = () => commitAnalysisU(true);
el("analysis-set-dice-btn").onclick = openSetDicePopup;
el("set-dice-cancel-btn").onclick = cancelSetDice;
el("set-dice-confirm-btn").onclick = confirmSetDice;

// The tooltip's position is computed once on hover; if the modal scrolls
// underneath it, just hide it rather than let it float in the wrong spot.
document.querySelector("#final-modal .modal").addEventListener("scroll", hideCellTooltip);

const savedNickname = localStorage.getItem("nickname");
if (savedNickname) {
  startWithNickname(savedNickname);
}
