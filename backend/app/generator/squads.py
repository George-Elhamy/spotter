"""Fictional league, squad and player seed data for Spotter."""

from __future__ import annotations

TEAM_ROWS = [
    ("RED", "Redmoor Rovers", "Redmoor", "#d7263d", "#ffffff", "4-3-3", "Moor Lane", "Erik Halvorsen", (0.72, 0.48, 0.35, 0.58)),
    ("WHI", "Whitcliffe Athletic", "Whitcliffe", "#f2f2f2", "#111111", "4-2-3-1", "Cliffside Park", "Paolo Ricci", (0.56, 0.86, 0.68, 0.82)),
    ("ASH", "Ashgrove City", "Ashgrove", "#257a54", "#f5f1dc", "4-3-3", "Willow Ground", "Marek Varga", (0.61, 0.67, 0.51, 0.63)),
    ("BLK", "Blackwater FC", "Blackwater", "#182c45", "#d0aa58", "4-4-2", "Foundry Field", "Niall Keegan", (0.48, 0.64, 0.69, 0.57)),
    ("EAS", "Eastholm United", "Eastholm", "#6d3a83", "#f4e7c5", "4-2-3-1", "East Mere", "Lena Hartmann", (0.62, 0.58, 0.48, 0.61)),
    ("FEN", "Fenwick Town", "Fenwick", "#2786a4", "#e9d88b", "3-4-2-1", "Fenwick Common", "Owen Macrae", (0.53, 0.73, 0.57, 0.76)),
    ("GRE", "Greystone Athletic", "Greystone", "#b38b27", "#173c32", "4-3-3", "Quarry End", "Sorin Petrescu", (0.59, 0.71, 0.62, 0.69)),
    ("HAR", "Harwick Rangers", "Harwick", "#4064aa", "#f4f4f0", "4-4-1-1", "Ranger's Heath", "Declan Byrne", (0.47, 0.79, 0.61, 0.71)),
    ("IRN", "Ironvale FC", "Ironvale", "#9b4337", "#d9d5cd", "4-1-4-1", "Vale Park", "Tomas Eklund", (0.55, 0.62, 0.53, 0.55)),
    ("LAR", "Larkspur Albion", "Larkspur", "#568c45", "#f1d7e2", "4-3-3", "Larkspur Field", "Rafiq Suleiman", (0.66, 0.59, 0.65, 0.66)),
    ("MIL", "Millbrook Town", "Millbrook", "#765548", "#e6ddc9", "4-2-3-1", "Millbrook Green", "Ewan Sato", (0.58, 0.65, 0.55, 0.62)),
    ("OAK", "Oakhaven City", "Oakhaven", "#3b7182", "#e7c85b", "5-3-2", "Harbour Rise", "Anika Solberg", (0.51, 0.72, 0.59, 0.58)),
]

TEAM_DATA = [
    {
        "id": row[0], "name": row[1], "short_name": row[2],
        "color_primary": row[3], "color_secondary": row[4],
        "formation": row[5],
        "style": dict(zip(("possession", "press", "directness", "tempo"), row[8])),
        "stadium": row[6], "manager": row[7],
    }
    for row in TEAM_ROWS
]

_SQUADS = {
    "RED": [
        (1, "Tomasz Wrona", "GK", "POL", True), (2, "Callum Reid", "RB", "SCO", True),
        (4, "Mateo Duarte", "CB", "POR", True), (5, "Henrik Dahl", "CB", "DEN", True),
        (3, "Yannick Laurent", "LB", "FRA", True), (6, "Pieter de Wit", "CDM", "NED", True),
        (8, "Marco Bellini", "CM", "ITA", True), (14, "Elias Brenner", "CM", "AUT", True),
        (7, "Luca Moretti", "RW", "ITA", True), (9, "Jonas Falk", "ST", "GER", True),
        (11, "Kofi Asante", "LW", "GHA", True), (13, "Rory Kavanagh", "GK", "IRL", False),
        (15, "Bastien Leroy", "CB", "FRA", False), (16, "Arda Kaplan", "CM", "TUR", False),
        (17, "Diego Salcedo", "FW", "ESP", False), (19, "Theo Lindqvist", "ST", "SWE", False),
        (20, "Joel Ahonen", "RB", "FIN", False), (22, "Ivo Petrov", "CM", "BUL", False),
    ],
    "WHI": [
        (1, "Mikkel Sørensen", "GK", "DEN", True), (2, "Adrien Fournier", "RB", "FRA", True),
        (5, "Stefan Vuković", "CB", "SRB", True), (6, "Ollie Grant", "CB", "ENG", True),
        (3, "Sam Whitaker", "LB", "ENG", True), (8, "Lukas Hofer", "CDM", "AUT", True),
        (18, "Ruben Castillo", "CDM", "ESP", True), (7, "Emil Nyström", "RW", "SWE", True),
        (10, "Andrej Novak", "CAM", "CRO", True), (17, "Jakub Hrubý", "LW", "CZE", True),
        (9, "Daan Visser", "ST", "NED", True), (12, "Ben Holloway", "GK", "ENG", False),
        (4, "Kristian Berg", "CB", "NOR", False), (11, "Nico Ferreira", "FW", "BRA", False),
        (14, "Marcel Kühn", "CM", "GER", False), (16, "Aurelio Conti", "RW", "ITA", False),
        (20, "Finn O'Brien", "LB", "IRL", False), (23, "Viktor Lund", "CM", "SWE", False),
    ],
}

_PINNED = {
    "RED-7": {"pace": 94, "dribbling": 98, "height_cm": 176},
    "RED-9": {"aerial": 96, "height_cm": 193},
    "RED-1": {"height_cm": 190}, "WHI-10": {"passing": 96},
    "WHI-3": {"defending": 81}, "RED-16": {"passing": 82},
    "RED-19": {"age": 19},
}


def build_squads() -> dict[str, list[dict]]:
    squads: dict[str, list[dict]] = {}
    for team_id, rows in _SQUADS.items():
        players = []
        for number, name, position, nationality, starter in rows:
            player_id = f"{team_id}-{number}"
            short_name = "de Wit" if name == "Pieter de Wit" else name.split()[-1]
            keeper = position == "GK"
            # Stable, role-shaped attributes; the number-based offsets avoid clones.
            base = (number * 7 + (0 if team_id == "RED" else 13)) % 17
            attrs = {
                "pace": 55 + base + (15 if position in {"RW", "LW", "FW", "ST"} else 0),
                "passing": 58 + (base * 2) % 23 + (12 if position in {"CM", "CDM", "CAM"} else 0),
                "finishing": 54 + (base * 2) % 24 + (15 if position in {"FW", "ST", "RW", "LW"} else 0),
                "defending": 55 + (base * 2) % 24 + (13 if position in {"CB", "LB", "RB", "CDM"} else 0),
                "dribbling": 54 + (base * 2) % 24 + (12 if position in {"RW", "LW", "CAM"} else 0),
                "aerial": 52 + (base * 2) % 24 + (17 if position in {"CB", "ST", "GK"} else 0),
            }
            if keeper:
                attrs.update({"pace": 43 + base % 10, "passing": 54 + base % 15,
                              "finishing": 10 + base % 10, "defending": 67 + base % 20,
                              "dribbling": 35 + base % 15, "aerial": 66 + base % 20})
            pinned = _PINNED.get(player_id, {})
            for key in attrs:
                attrs[key] = max(1, min(99, int(pinned.get(key, attrs[key]))))
            players.append({
                "id": player_id, "team_id": team_id, "number": number,
                "name": name, "short_name": short_name, "position": position,
                "nationality": nationality,
                "age": int(pinned.get("age", 21 + (number * 3 + len(name)) % 13)),
                "height_cm": int(pinned.get("height_cm", 168 + (number * 5 + base) % 26)),
                "foot": "left" if (number + len(team_id)) % 4 == 0 else "right",
                "starter": starter, "attrs": attrs,
            })
        squads[team_id] = players
    return squads
