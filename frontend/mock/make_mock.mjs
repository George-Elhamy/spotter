// Generates mock fixtures that follow frontend/src/types/contract.ts (spec §10).
// Run: node frontend/mock/make_mock.mjs   → writes meta.json, instance.json, ws_stream.json
// ws_stream.json = [{ at_ms, msg }]; a mock socket replays msg at at_ms after connect.
// Placeholder data for UI development only — the real feed comes from the backend.
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const out = dirname(fileURLToPath(import.meta.url));
let seed = 42;
const rnd = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648);

const RED = [
  [1, "Tomasz Wrona", "GK"], [2, "Callum Reid", "RB"], [4, "Mateo Duarte", "CB"], [5, "Henrik Dahl", "CB"],
  [3, "Yannick Laurent", "LB"], [6, "Pieter de Wit", "CDM"], [8, "Marco Bellini", "CM"], [14, "Elias Brenner", "CM"],
  [7, "Luca Moretti", "RW"], [9, "Jonas Falk", "ST"], [11, "Kofi Asante", "LW"],
];
const WHI = [
  [1, "Mikkel Sørensen", "GK"], [2, "Adrien Fournier", "RB"], [5, "Stefan Vuković", "CB"], [6, "Ollie Grant", "CB"],
  [3, "Sam Whitaker", "LB"], [8, "Lukas Hofer", "CDM"], [18, "Ruben Castillo", "CDM"], [7, "Emil Nyström", "RW"],
  [10, "Andrej Novak", "CAM"], [17, "Jakub Hrubý", "LW"], [9, "Daan Visser", "ST"],
];
// 4-3-3 slots for RED attacking toward x=105 (1st half); y=0 is RED's right touchline side.
const RED_SLOTS = [[5, 34], [30, 8], [25, 26], [25, 42], [30, 60], [40, 34], [50, 22], [50, 46], [70, 10], [75, 34], [70, 58]];
// 4-2-3-1 for WHI attacking toward x=0.
const WHI_SLOTS = [[100, 34], [75, 60], [80, 42], [80, 26], [75, 8], [65, 42], [65, 26], [50, 58], [52, 34], [50, 10], [40, 34]];

const players = [
  ...RED.map(([n, name, pos], i) => ({ id: `RED-${n}`, team_id: "RED", number: n, name, short_name: name.split(" ").slice(-1)[0], position: pos, nationality: "", starter: true, _slot: RED_SLOTS[i] })),
  ...WHI.map(([n, name, pos], i) => ({ id: `WHI-${n}`, team_id: "WHI", number: n, name, short_name: name.split(" ").slice(-1)[0], position: pos, nationality: "", starter: true, _slot: WHI_SLOTS[i] })),
];
if (players.find((p) => p.id === "RED-3")) players.find((p) => p.id === "RED-3").short_name = "Laurent";
const pDeWit = players.find((p) => p.id === "RED-6"); pDeWit.short_name = "de Wit";

const meta = {
  teams: {
    RED: { id: "RED", name: "Redmoor Rovers", short_name: "REDMOOR", color_primary: "#d7263d", color_secondary: "#ffffff", formation: "4-3-3", manager: "Erik Halvorsen", stadium: "Moor Lane" },
    WHI: { id: "WHI", name: "Whitcliffe Athletic", short_name: "WHITCLIFFE", color_primary: "#f2f2f2", color_secondary: "#111111", formation: "4-2-3-1", manager: "Paolo Ricci", stadium: "Cliffside Park" },
  },
  players: players.map(({ _slot, ...p }) => p),
  jump_presets: [0, 8, 17, 26, 37, 51, 60, 66, 80, 87, 90].map((m) => ({ minute: m, label: `${m}'` })),
  key_moments: [
    { t: 540, minute: 9, label: "Whitaker yellow" }, { t: 1085, minute: 18, label: "GOAL Falk 1-0" },
    { t: 1640, minute: 27, label: "VAR: Falk goal disallowed" }, { t: 2290, minute: 38, label: "GOAL Visser 1-1" },
  ],
  duration_t: 5760,
};

const instance = {
  id: "main", name: "EN Analyst", language: "en", audience: "analyst", perspective: "neutral", energy: 3,
  tone: "neutral", focus_player_id: null, ai_voice: true, muted_agents: [], directives: [],
};

// ---- build a short event sequence: 17:00 → 18:30, Falk header goal at 18:05 ----
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const frameAt = (ball, attackBias) => ({
  ball: { x: +ball.x.toFixed(1), y: +ball.y.toFixed(1) },
  players: players.map((p) => {
    const [sx, sy] = p._slot;
    const pull = p.position === "GK" ? 0.05 : 0.3;
    const x = sx + (ball.x - sx) * pull + attackBias + (rnd() - 0.5) * 2;
    const y = sy + (ball.y - sy) * pull * 0.6 + (rnd() - 0.5) * 2;
    return { id: p.id, x: +clamp(x, 0.5, 104.5).toFixed(1), y: +clamp(y, 0.5, 67.5).toFixed(1) };
  }),
});

const events = [];
let id = 600;
let t = 1020;
let ball = { x: 50, y: 34 };
const redOutfield = ["RED-6", "RED-8", "RED-14", "RED-2", "RED-3", "RED-7", "RED-11", "RED-4", "RED-5"];
const push = (e) => {
  const minute = Math.floor(e.t / 60);
  const frame = frameAt(e.end ?? e.start ?? ball, 8);
  if (e.player_id && e.start) {
    const fp = frame.players.find((p) => p.id === e.player_id);
    if (fp) { fp.x = e.start.x; fp.y = e.start.y; }
  }
  events.push({
    id: id++, period: 1, minute, second: Math.floor(e.t % 60), added: 0, subtype: null, related_player_id: null,
    outcome: null, under_pressure: false, body_part: null, xg: null, ball_speed_kmh: null, flight_s: null,
    restart: null, card: null, var: null, ...e, t: +e.t.toFixed(1), frame,
  });
};

while (t < 1078) {
  const from = redOutfield[Math.floor(rnd() * redOutfield.length)];
  let to = redOutfield[Math.floor(rnd() * redOutfield.length)];
  if (to === from) to = "RED-9";
  const start = { ...ball };
  const end = { x: clamp(ball.x + (rnd() - 0.3) * 18, 20, 92), y: clamp(ball.y + (rnd() - 0.5) * 24, 3, 65) };
  const ok = rnd() > 0.15;
  push({ t, type: "pass", team_id: "RED", player_id: from, related_player_id: to, start, end, outcome: ok ? "complete" : "incomplete", under_pressure: rnd() > 0.6, ball_speed_kmh: +(40 + rnd() * 30).toFixed(1), flight_s: 1.1 });
  t += 1.4 + rnd() * 1.8;
  ball = end;
  if (!ok) {
    push({ t, type: "throw_in", team_id: "RED", player_id: "RED-2", start: { x: ball.x, y: 0.5 }, end: { x: ball.x + 5, y: 8 }, outcome: "complete", restart: "throw_in" });
    ball = { x: ball.x + 5, y: 8 };
    t += 7;
  }
}
// The goal move: Moretti dribble past Whitaker → Reid cross → Falk header
push({ t, type: "dribble", team_id: "RED", player_id: "RED-7", related_player_id: "WHI-3", start: { x: 78, y: 12 }, end: { x: 84, y: 9 }, outcome: "complete", under_pressure: true }); t += 1.6;
push({ t, type: "pass", subtype: "cross", team_id: "RED", player_id: "RED-2", related_player_id: "RED-9", start: { x: 88, y: 6 }, end: { x: 97, y: 33 }, outcome: "complete", ball_speed_kmh: 72.4, flight_s: 1.3, under_pressure: true }); t += 1.3;
push({ t, type: "shot", subtype: "header", team_id: "RED", player_id: "RED-9", start: { x: 97, y: 33 }, end: { x: 105, y: 35.5 }, outcome: "goal", body_part: "head", xg: 0.21, ball_speed_kmh: 64.0, flight_s: 0.5 }); t += 0.5;
push({ t, type: "goal", team_id: "RED", player_id: "RED-9", related_player_id: "RED-2", start: { x: 105, y: 35.5 }, outcome: "goal" }); t += 40;
push({ t, type: "kickoff", team_id: "WHI", player_id: "WHI-9", start: { x: 52.5, y: 34 }, end: { x: 45, y: 34 }, outcome: "complete", restart: "kickoff" });

// ---- assemble the ws stream: server t runs at 1×; client must display at t - 2.0 ----
const T0 = 1020;
const stream = [];
const at = (matchT) => Math.max(0, Math.round((matchT - T0) * 1000));
const add = (matchT, msg) => stream.push({ at_ms: at(matchT), msg });

let score = [0, 0];
add(T0, { type: "instance", instance });
add(T0, { type: "directive", directives: [] });
for (const a of ["stats_scout", "tactical", "dossier", "storyline"]) add(T0, { type: "agent_status", agent: a, status: "idle", last_ms: null });
for (let s = T0; s <= t + 5; s += 0.5) {
  if (events.some((e) => e.type === "goal" && e.t <= s)) score = [1, 0];
  add(s, { type: "clock", t: +s.toFixed(1), display_delay_s: 2.0, speed: 1, period: 1, score: [...score], paused: false, cost_cap_reached: false, cost_usd: 0.42, cost_cap_usd: 8 });
  if (Math.abs(s % 2) < 0.01) {
    const chaos = 22 + Math.round(rnd() * 8);
    const red = 60 + Math.round(rnd() * 6);
    add(s, { type: "stats", control: { RED: red, WHI: 100 - red }, chaos, possession: { match: { RED: 58, WHI: 42 }, rolling: { RED: 63, WHI: 37 } }, win_prob: score[0] ? { RED: 0.62, DRAW: 0.24, WHI: 0.14 } : { RED: 0.41, DRAW: 0.3, WHI: 0.29 } });
  }
}
for (const e of events) add(e.t, { type: "event", event: e });

const baseCard = (o) => ({
  category: "stat", player_ids: [], team_id: null, claims: [], evidence_event_ids: [], priority: 3, time_sensitive: true, ttl_s: 30,
  verifier: { ok: null, reason: null, revision_of: null }, producer: { fit: null, reason: null, score: null },
  render: { line: null, language: null, audio_url: null, duration_ms: null }, ...o,
});
const cardSeq = (startT, card, steps) => {
  let c = baseCard({ ...card, created_t: startT, status: "proposed" });
  add(startT, { type: "card", card: c });
  for (const [dt, patch] of steps) {
    c = { ...c, ...patch, verifier: { ...c.verifier, ...(patch.verifier ?? {}) }, producer: { ...c.producer, ...(patch.producer ?? {}) }, render: { ...c.render, ...(patch.render ?? {}) } };
    add(startT + dt, { type: "card", card: c });
  }
};

add(1022, { type: "agent_status", agent: "stats_scout", status: "thinking", last_ms: null });
add(1025, { type: "agent_status", agent: "stats_scout", status: "idle", last_ms: 2840 });
cardSeq(1025, {
  id: "c_0001", agent: "stats_scout", text: "Moretti has completed 5 successful dribbles against Whitaker already, the most by any winger against him this season.",
  player_ids: ["RED-7", "WHI-3"], team_id: "RED", priority: 4,
  claims: [{ kind: "stat", entity: "RED-7", metric: "dribbles_won_vs", against: "WHI-3", window: "match", value: 5 }], evidence_event_ids: [102, 233, 410, 455, 590],
}, [
  [0.5, { status: "verifying" }],
  [1.2, { status: "verified", verifier: { ok: true, reason: "dribbles_won_vs RED-7/WHI-3 = 5 ✓" } }],
  [2.0, { status: "queued", producer: { fit: true, reason: "Strong matchup stat for analysts", score: 71 } }],
  [2.4, { status: "rendering" }],
  [4.0, { status: "ready", render: { line: "Five times now Moretti has gone past Whitaker — nobody's done that to him all season.", language: "en", audio_url: "/mock/silence.mp3", duration_ms: 3800 } }],
]);
add(1033, { type: "trace", t: 1033, agent: "verifier", action: "approved", detail: "c_0001: dribbles_won_vs RED-7/WHI-3 = 5" });

add(1030, { type: "agent_status", agent: "tactical", status: "thinking", last_ms: null });
add(1034, { type: "agent_status", agent: "tactical", status: "idle", last_ms: 3900 });
cardSeq(1034, {
  id: "c_0002", agent: "tactical", category: "tactical", text: "Redmoor's control index sits at 64: 72% of their passes in the last five minutes came in the Whitcliffe half.",
  team_id: "RED", priority: 3, claims: [{ kind: "stat", entity: "RED", metric: "control_index", window: "5min", value: 64 }],
}, [
  [0.5, { status: "verifying" }],
  [1.0, { status: "rejected", verifier: { ok: false, reason: "claimed 72% passes in opp. half, actual 66%" } }],
  [1.5, { status: "revising" }],
]);
add(1035, { type: "trace", t: 1035, agent: "verifier", action: "rejected", detail: "c_0002: claimed 72% in opponent half, actual 66%" });
cardSeq(1038, {
  id: "c_0003", agent: "tactical", category: "tactical", text: "Redmoor's control index sits at 64: 66% of their passes in the last five minutes came in the Whitcliffe half.",
  team_id: "RED", priority: 3, claims: [{ kind: "stat", entity: "RED", metric: "control_index", window: "5min", value: 64 }],
}, [
  [0.4, { status: "verifying", verifier: { revision_of: "c_0002" } }],
  [1.0, { status: "verified", verifier: { ok: true, reason: "all claims within tolerance" } }],
  [1.6, { status: "skipped", producer: { fit: false, reason: "Duplicate angle with c_0001 in the last 60 s", score: 38 } }],
]);
add(1036, { type: "card", card: baseCard({ id: "c_0002", agent: "tactical", category: "tactical", created_t: 1034, status: "discarded", text: "Redmoor's control index sits at 64: 72% of their passes in the last five minutes came in the Whitcliffe half.", verifier: { ok: false, reason: "superseded by revision c_0003", revision_of: null } }) });

cardSeq(1045, {
  id: "c_0004", agent: "dossier", category: "background", ttl_s: 300, time_sensitive: false,
  text: "Falk, 1.93 m, has scored in each of Redmoor's last 3 home games and leads the league in aerial duels won.",
  player_ids: ["RED-9"], team_id: "RED", priority: 3,
  claims: [{ kind: "stat", entity: "RED-9", metric: "home_scoring_streak", window: "season", value: 3 }],
}, [
  [0.5, { status: "verifying" }],
  [1.1, { status: "verified", verifier: { ok: true, reason: "home_scoring_streak RED-9 = 3 ✓" } }],
  [1.8, { status: "queued", producer: { fit: true, reason: "Falk involved in current attack", score: 64 } }],
  [3.0, { status: "ready", render: { line: "Falk — 1.93 metres, scored in each of the last 3 home games.", language: "en", audio_url: "/mock/silence.mp3", duration_ms: 3500 } }],
]);

cardSeq(1052, {
  id: "c_0005", agent: "storyline", category: "story", text: "Whitaker, booked on 9 minutes, keeps being isolated against Moretti on Redmoor's right.",
  player_ids: ["WHI-3", "RED-7"], team_id: "WHI", priority: 2, ttl_s: 25,
}, [[0.5, { status: "verifying" }], [1.2, { status: "verified", verifier: { ok: true, reason: "qualitative: supported" } }], [1.8, { status: "queued", producer: { fit: true, reason: "ok", score: 40 } }], [26, { status: "expired" }]]);

// Play-by-play calls, timed to display time of their events.
const goalEv = events.find((e) => e.type === "goal");
const shotEv = events.find((e) => e.type === "shot");
const crossEv = events.find((e) => e.subtype === "cross");
const call = (sid, ev, text, dur) => add(ev.t - 1.5, { type: "speech", id: sid, kind: "call", card_id: null, text, subtitle_en: null, audio_url: "/mock/silence.mp3", play_at_t: ev.t, duration_ms: dur });
call("s_0001", crossEv, "Reid whips it in from the right…", 1500);
call("s_0002", shotEv, "Falk rises — HEADER!", 1200);
call("s_0003", goalEv, "GOAL! Jonas Falk! Redmoor lead, one-nil at Moor Lane!", 3600);
add(goalEv.t + 4, { type: "card", card: baseCard({ id: "c_0004", agent: "dossier", category: "background", created_t: 1045, ttl_s: 300, status: "airing", text: "Falk, 1.93 m, has scored in each of Redmoor's last 3 home games and leads the league in aerial duels won.", player_ids: ["RED-9"], team_id: "RED", verifier: { ok: true, reason: "ok", revision_of: null }, producer: { fit: true, reason: "Falk involved in current attack", score: 88 }, render: { line: "Falk — 1.93 metres, scored in each of the last 3 home games.", language: "en", audio_url: "/mock/silence.mp3", duration_ms: 3500 } }) });
add(goalEv.t + 4, { type: "speech", id: "s_0004", kind: "card", card_id: "c_0004", text: "Falk — 1.93 metres, scored in each of the last 3 home games.", subtitle_en: null, audio_url: "/mock/silence.mp3", play_at_t: goalEv.t + 6, duration_ms: 3500 });
add(goalEv.t + 10, { type: "card", card: baseCard({ id: "c_0004", agent: "dossier", category: "background", created_t: 1045, ttl_s: 300, status: "aired", text: "Falk, 1.93 m, has scored in each of Redmoor's last 3 home games and leads the league in aerial duels won.", player_ids: ["RED-9"], team_id: "RED", verifier: { ok: true, reason: "ok", revision_of: null }, producer: { fit: true, reason: "aired in goal celebration", score: 88 }, render: { line: "Falk — 1.93 metres.", language: "en", audio_url: "/mock/silence.mp3", duration_ms: 3500 } }) });
add(goalEv.t + 12, { type: "directive", directives: [{ id: "d_1", type: "focus_player", target: "WHI-10", expires_t: null, source: "human", text: "focus on Novak" }] });

stream.sort((a, b) => a.at_ms - b.at_ms);
writeFileSync(join(out, "meta.json"), JSON.stringify(meta, null, 2));
writeFileSync(join(out, "instance.json"), JSON.stringify(instance, null, 2));
writeFileSync(join(out, "ws_stream.json"), JSON.stringify(stream));
console.log(`events=${events.length} messages=${stream.length} span=${(stream.at(-1).at_ms / 1000).toFixed(0)}s`);
