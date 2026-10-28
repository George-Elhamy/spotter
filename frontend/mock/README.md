# Mock fixtures (spec §10)

Types: `frontend/src/types/contract.ts` (backend mirror: `backend/app/models.py`).

- `meta.json` — `GET /api/match/meta` response (`MatchMeta`)
- `instance.json` — `GET /api/instance` response (`InstanceSettings`)
- `ws_stream.json` — `[{ at_ms, msg: WsMessage }]`. A mock socket replays each `msg` `at_ms` after connect.
  Covers 17:00 → ~18:50: passing spell, Moretti dribble → Reid cross → Falk header goal (1–0),
  card lifecycles (verified → queued → ready → airing → aired; rejected → revised; skipped; expired),
  agent status changes, play-by-play `speech` calls, a trace and a directive chip.
- Regenerate: `node frontend/mock/make_mock.mjs`.

Contract notes beyond the spec text (all additive):
- `clock.cost_cap_reached` drives the "cost cap reached" badge (§0.1, §12.8).
- `{type:"reset", t}` is sent on seek: the client clears its board, audio queue and event buffer.
- `{type:"instance", instance}` is sent on connect and whenever settings change.
- Cards are re-sent in full on every status change; the client upserts by `card.id`.
- Pitch is displayed at `clock.t - display_delay_s`. Interpolate player/ball positions between consecutive event frames.
- `audio_url` may 404 (mocks point at `/mock/silence.mp3`, which does not exist); treat audio errors as subtitle-only.
