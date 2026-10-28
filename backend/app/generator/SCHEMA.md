# Generated data schema

`python -m app.generator.generate` writes five UTF-8 JSON files to `backend/app/data/`.
The generator uses Python's deterministic `random.Random(42)` streams and emits stable
key ordering/formatting. `match_events.json` is compact JSON to keep the per-event
position frames below the 6 MB target. Numeric pitch coordinates are metres on a
105 × 68 m pitch.

## `teams.json`

```json
{
  "teams": [
    {
      "id": "RED",
      "name": "Redmoor Rovers",
      "short_name": "Redmoor",
      "color_primary": "#d7263d",
      "color_secondary": "#ffffff",
      "formation": "4-3-3",
      "style": {
        "possession": 0.72,
        "press": 0.48,
        "directness": 0.35,
        "tempo": 0.58
      },
      "stadium": "Moor Lane",
      "manager": "Erik Halvorsen"
    }
  ]
}
```

`teams` has 12 entries: RED, WHI and the ten fictional league teams. `style` values
are floats from 0 through 1. Colors are six-digit CSS hex strings. WHI is
`#f2f2f2` / `#111111`; RED is `#d7263d` / `#ffffff`.

## `squads.json`

The root object maps `RED` and `WHI` to arrays of exactly 18 player objects:

```json
{
  "RED": [
    {
      "id": "RED-7",
      "team_id": "RED",
      "number": 7,
      "name": "Luca Moretti",
      "short_name": "Moretti",
      "position": "RW",
      "nationality": "ITA",
      "age": 27,
      "height_cm": 176,
      "foot": "right",
      "starter": true,
      "attrs": {
        "pace": 94,
        "passing": 67,
        "finishing": 84,
        "defending": 70,
        "dribbling": 98,
        "aerial": 63
      }
    }
  ],
  "WHI": []
}
```

`foot` is `right` or `left`; `starter` is boolean. All six `attrs` are integer
ratings in [1, 99]. Player IDs are the team code and shirt number. The array order
is the seed roster order, which is also used for the initial lineups.

## `league_history.json`

```json
{
  "matchdays": [
    {
      "md": 1,
      "results": [
        {"home": "RED", "away": "WHI", "home_goals": 1, "away_goals": 0}
      ]
    }
  ],
  "player_lines": [
    {
      "md": 1,
      "player_id": "RED-7",
      "team_id": "RED",
      "opponent": "WHI",
      "home": true,
      "started": true,
      "minutes": 90,
      "goals": 0,
      "assists": 0,
      "shots": 2,
      "passes": 72,
      "passes_completed": 61,
      "key_passes": 2,
      "progressive_passes": 8,
      "dribbles_attempted": 15,
      "dribbles_won": 13,
      "tackles": 1,
      "aerials_won": 0,
      "yellow": 0,
      "red": 0,
      "top_speed_kmh": 34.2,
      "rating": 7.2,
      "penalties_faced": 0,
      "penalties_saved": 0,
      "sub_goals": 0
    }
  ],
  "player_lines_league_leaders": [
    {
      "metric": "dribbles_won_per90",
      "leaders": [
        {"player_id": "RED-7", "team_id": "RED", "name": "Luca Moretti", "value": 9.8, "minutes": 820}
      ]
    }
  ],
  "head_to_head": [
    {"season": "2025/26", "home": "WHI", "away": "RED", "home_goals": 2, "away_goals": 1}
  ],
  "table": [
    {"team_id": "ASH", "p": 10, "w": 9, "d": 0, "l": 1, "gf": 20, "ga": 7, "gd": 13, "pts": 27, "position": 1}
  ]
}
```

`matchdays` contains ten days and six results per day (every team plays on each day).
`player_lines` contains a line only when a RED/WHI player appeared. `passes_completed`
cannot exceed `passes`; card counts and all match statistics are integers, while
`top_speed_kmh` and `rating` are one-decimal floats.

`player_lines_league_leaders` is an array indexed by `metric`. Each `leaders` list is
sorted descending by `value` (player ID breaks ties); per-90 metric names end in
`_per90`, and rows include the measured minutes. It contains RED/WHI totals plus
summary rows for fictional players from the other ten clubs so the pinned league
ranks have a league-wide comparison.

`head_to_head` is the three most recent previous-season meetings. `table` is
recomputed from all 60 match results and sorted by points, goal difference, goals
for, then team ID. `p`, `w`, `d`, `l`, `gf`, `ga`, `gd`, `pts`, and `position` are
derived values, not manually authored table totals.

## `dossiers.json`

```json
{
  "players": {
    "RED-7": {
      "number": 7,
      "position": "RW",
      "age": 27,
      "nationality": "ITA",
      "height_cm": 176,
      "foot": "right",
      "apps": 10,
      "starts": 10,
      "minutes": 870,
      "goals": 0,
      "assists": 2,
      "shots": 22,
      "pass_accuracy": 83.7,
      "key_passes": 24,
      "dribbles_won": 90,
      "tackles": 12,
      "yellow": 0,
      "red": 0,
      "top_speed_kmh": 34.2,
      "last5_ratings": [7.1, 7.4, 6.9, 7.8, 7.2],
      "per90": {"goals": 0.0, "assists": 0.207, "shots": 2.276},
      "league_ranks": {"dribbles_won_per90": 1},
      "penalties_faced": 0,
      "penalties_saved": 0,
      "sub_goals": 0,
      "story_facts": ["Averages 9.31 successful dribbles per 90"]
    }
  },
  "teams": {
    "WHI": {
      "position": 2,
      "p": 10,
      "w": 7,
      "d": 2,
      "l": 1,
      "pts": 23,
      "form_last5": ["W", "W", "W", "D", "W"],
      "unbeaten_run": 7,
      "h2h_summary": {"played": 3, "wins": 2, "draws": 1, "losses": 0},
      "story_facts": ["Unbeaten in the last 7 league matches"]
    }
  }
}
```

`players` has an entry for every RED/WHI squad member, including players with no
appearances. Counting fields, `pass_accuracy`, `top_speed_kmh`, `last5_ratings`,
`per90`, and `league_ranks` are derived from `player_lines` and the leader summary.
`per90` includes goals, assists, shots, key passes, dribbles won, tackles, progressive
passes and aerials won. `league_ranks` maps each available leader metric to a
1-based rank. `story_facts` contains one or two strings assembled from those derived
numbers. Team dossier `form_last5` is oldest-to-newest; `unbeaten_run` counts back
from matchday 10.

## `match_events.json`

The file is a compact object with `meta` and `events`:

```json
{
  "meta": {
    "seed": 42,
    "period_start_t": {"1": 0.0, "2": 2821.0},
    "half_time_t": 2820.0,
    "full_time_t": 5887.0,
    "lineups": {"RED": ["RED-1"], "WHI": ["WHI-1"]},
    "final_score": [3, 2],
    "attack_direction": {"1": {"RED": "+x", "WHI": "-x"}, "2": {"RED": "-x", "WHI": "+x"}}
  },
  "events": [
    {
      "id": 1,
      "t": 0.0,
      "period": 1,
      "minute": 0,
      "second": 0,
      "added": 0,
      "type": "kickoff",
      "subtype": null,
      "team_id": "RED",
      "player_id": "RED-6",
      "related_player_id": null,
      "start": {"x": 48.0, "y": 34.0},
      "end": {"x": 54.0, "y": 34.0},
      "outcome": null,
      "under_pressure": false,
      "body_part": null,
      "xg": null,
      "ball_speed_kmh": null,
      "flight_s": null,
      "restart": "kickoff",
      "card": null,
      "var": null,
      "frame": {
        "ball": {"x": 48.0, "y": 34.0},
        "players": [{"id": "RED-1", "x": 5.0, "y": 34.0}]
      }
    }
  ]
}
```

Every event includes all event fields from `frontend/src/types/contract.ts`
`MatchEvent`, with `null` for inapplicable optional values. IDs are sequential from
1 and events are strictly time-sorted. `t` is continuous elapsed match seconds;
second-half kickoff is exactly one second after the half-time event. `minute` is
capped at 45/90 and `added` stores overflow minutes. `period` is 1 or 2. `team_id`
is RED, WHI or null for match-wide events; player IDs are null only where no player
is applicable. Event `start`/`end`, `xg`, speed, flight, restart, card and VAR fields
follow the TypeScript contract. The `frame` always contains `ball` and every active
player (22 before Duarte's dismissal, 21 after); frame player entries contain `id`,
`x`, and `y` only.

Supported `type` values are `kickoff`, `pass`, `carry`, `dribble`, `shot`, `save`,
`goal`, `tackle`, `interception`, `clearance`, `block`, `duel`, `foul`, `card`,
`free_kick`, `corner`, `throw_in`, `goal_kick`, `offside`, `var_check`,
`var_decision`, `penalty_awarded`, `penalty_taken`, `injury`, `stoppage`,
`substitution`, `added_time`, `half_time`, and `full_time`.

## Determinism and validation

Generated objects use seed 42 and no current time, external data or model output.
Run `python -m app.generator.generate` twice to verify byte identity. Run
`python -m app.generator.validate` to check schemas, scores, pinned facts, table and
dossier recomputation, on-pitch rosters, pitch bounds, movement limits, shot/pass
volumes, and frame-derived peak speed; successful validation prints the realism
report.
