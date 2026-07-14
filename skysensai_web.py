from flask import Flask, render_template_string, request, jsonify
import csv
import os
import re
from itertools import combinations

app = Flask(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Global traffic state
# ─────────────────────────────────────────────────────────────────────────────

aircraft = {}
active_alerts = set()

ADSB_REPLAY_FILE = "sample_e16_adsb_history.csv"
adsb_replay_rows = []

PATTERN_STATES = {
    "downwind", "base", "final", "short_final", "crosswind", "upwind",
    "forty_five_entry", "departing", "entering_runway", "landed_rollout"
}

CRITICAL_STATES = {
    "entering_runway", "departing", "short_final", "final", "landed_rollout"
}


# ─────────────────────────────────────────────────────────────────────────────
# Built-in ADS-B sample data
# ─────────────────────────────────────────────────────────────────────────────

SAMPLE_ADSB_CSV = """time_sec,timestamp,callsign,icao24,runway,state,latitude,longitude,x,y,altitude_ft,groundspeed_kt,track_deg,on_ground,source
0,2026-06-20T18:00:00Z,N56T,a1b2c3,14,downwind,37.1010,-121.5750,500,330,1200,92,140,false,simulated_adsb
8,2026-06-20T18:00:08Z,N56T,a1b2c3,14,downwind,37.0960,-121.5780,500,330,1180,90,145,false,simulated_adsb
16,2026-06-20T18:00:16Z,N23A,b2c3d4,14,forty_five_entry,37.1045,-121.5625,560,238,1300,95,230,false,simulated_adsb
24,2026-06-20T18:00:24Z,N56T,a1b2c3,14,base,37.0830,-121.5850,420,625,1050,85,230,false,simulated_adsb
32,2026-06-20T18:00:32Z,N23A,b2c3d4,14,downwind,37.0990,-121.5765,500,330,1200,91,140,false,simulated_adsb
40,2026-06-20T18:00:40Z,N45X,c3d4e5,14,forty_five_entry,37.1050,-121.5615,560,238,1300,94,230,false,simulated_adsb
48,2026-06-20T18:00:48Z,N56T,a1b2c3,14,final,37.0750,-121.6030,206,618,850,78,320,false,simulated_adsb
56,2026-06-20T18:00:56Z,N23A,b2c3d4,14,base,37.0835,-121.5860,420,625,1050,84,230,false,simulated_adsb
64,2026-06-20T18:01:04Z,N45X,c3d4e5,14,downwind,37.0980,-121.5770,500,330,1200,90,140,false,simulated_adsb
72,2026-06-20T18:01:12Z,N56T,a1b2c3,14,short_final,37.0790,-121.5980,222,583,500,72,320,false,simulated_adsb
80,2026-06-20T18:01:20Z,N23A,b2c3d4,14,final,37.0755,-121.6025,206,618,850,78,320,false,simulated_adsb
88,2026-06-20T18:01:28Z,N45X,c3d4e5,14,base,37.0840,-121.5865,420,625,1050,84,230,false,simulated_adsb
96,2026-06-20T18:01:36Z,N56T,a1b2c3,14,landed_rollout,37.0818,-121.5965,258,440,300,45,320,true,simulated_adsb
104,2026-06-20T18:01:44Z,N23A,b2c3d4,14,short_final,37.0792,-121.5983,222,583,520,72,320,false,simulated_adsb
112,2026-06-20T18:01:52Z,N56T,a1b2c3,14,entered_taxiway,37.0820,-121.5960,302,490,280,15,0,true,simulated_adsb
120,2026-06-20T18:02:00Z,N45X,c3d4e5,14,final,37.0758,-121.6028,206,618,850,78,320,false,simulated_adsb
128,2026-06-20T18:02:08Z,N23A,b2c3d4,14,landed_rollout,37.0817,-121.5967,258,440,300,45,320,true,simulated_adsb
136,2026-06-20T18:02:16Z,N45X,c3d4e5,14,short_final,37.0791,-121.5981,222,583,520,72,320,false,simulated_adsb
144,2026-06-20T18:02:24Z,N23A,b2c3d4,14,entered_taxiway,37.0821,-121.5961,302,490,280,15,0,true,simulated_adsb
152,2026-06-20T18:02:32Z,N45X,c3d4e5,14,landed_rollout,37.0816,-121.5968,258,440,300,45,320,true,simulated_adsb
160,2026-06-20T18:02:40Z,N45X,c3d4e5,14,entered_taxiway,37.0822,-121.5962,302,490,280,15,0,true,simulated_adsb
"""


def create_sample_adsb_file():
    with open(ADSB_REPLAY_FILE, "w", encoding="utf-8", newline="") as file:
        file.write(SAMPLE_ADSB_CSV)


# ─────────────────────────────────────────────────────────────────────────────
# Built-in timeline simulation scenarios
# ─────────────────────────────────────────────────────────────────────────────

SIM_SCENARIOS = {
    "three_plane_pattern": {
        "name": "Three Aircraft Pattern Flow",
        "steps": [
            {
                "message": "T+0: Three aircraft established around runway 14.",
                "updates": [
                    {"callsign": "Cherokee 56T", "state": "downwind", "runway": "14"},
                    {"callsign": "Cessna 23A", "state": "forty_five_entry", "runway": "14"},
                    {"callsign": "Diamond 45X", "state": "holding_short", "runway": "14"},
                ]
            },
            {
                "message": "T+1: Lead aircraft turns base, second aircraft joins downwind.",
                "updates": [
                    {"callsign": "Cherokee 56T", "state": "base", "runway": "14"},
                    {"callsign": "Cessna 23A", "state": "downwind", "runway": "14"},
                    {"callsign": "Diamond 45X", "state": "holding_short", "runway": "14"},
                ]
            },
            {
                "message": "T+2: Lead aircraft turns final, second aircraft continues downwind.",
                "updates": [
                    {"callsign": "Cherokee 56T", "state": "final", "runway": "14"},
                    {"callsign": "Cessna 23A", "state": "downwind", "runway": "14"},
                    {"callsign": "Diamond 45X", "state": "holding_short", "runway": "14"},
                ]
            },
            {
                "message": "T+3: Lead aircraft short final, second aircraft turns base.",
                "updates": [
                    {"callsign": "Cherokee 56T", "state": "short_final", "runway": "14"},
                    {"callsign": "Cessna 23A", "state": "base", "runway": "14"},
                    {"callsign": "Diamond 45X", "state": "holding_short", "runway": "14"},
                ]
            },
            {
                "message": "T+4: Lead aircraft lands, second aircraft holds base, departure waits.",
                "updates": [
                    {"callsign": "Cherokee 56T", "state": "landed_rollout", "runway": "14"},
                    {"callsign": "Cessna 23A", "state": "base", "runway": "14"},
                    {"callsign": "Diamond 45X", "state": "holding_short", "runway": "14"},
                ]
            },
            {
                "message": "T+5: Lead aircraft clears runway, departure enters runway.",
                "updates": [
                    {"callsign": "Cherokee 56T", "state": "entered_taxiway", "runway": "14"},
                    {"callsign": "Cessna 23A", "state": "base", "runway": "14"},
                    {"callsign": "Diamond 45X", "state": "entering_runway", "runway": "14"},
                ]
            },
            {
                "message": "T+6: Departure rolling, second aircraft remains on base.",
                "updates": [
                    {"callsign": "Cessna 23A", "state": "base", "runway": "14"},
                    {"callsign": "Diamond 45X", "state": "departing", "runway": "14"},
                ]
            },
            {
                "message": "T+7: Second aircraft turns final, departure climbs upwind.",
                "updates": [
                    {"callsign": "Cessna 23A", "state": "final", "runway": "14"},
                    {"callsign": "Diamond 45X", "state": "upwind", "runway": "14"},
                ]
            },
            {
                "message": "T+8: Second aircraft short final, departure turns crosswind.",
                "updates": [
                    {"callsign": "Cessna 23A", "state": "short_final", "runway": "14"},
                    {"callsign": "Diamond 45X", "state": "crosswind", "runway": "14"},
                ]
            },
            {
                "message": "T+9: Second aircraft lands, departure joins downwind.",
                "updates": [
                    {"callsign": "Cessna 23A", "state": "landed_rollout", "runway": "14"},
                    {"callsign": "Diamond 45X", "state": "downwind", "runway": "14"},
                ]
            },
            {
                "message": "T+10: Second aircraft clears runway, third aircraft turns base.",
                "updates": [
                    {"callsign": "Cessna 23A", "state": "entered_taxiway", "runway": "14"},
                    {"callsign": "Diamond 45X", "state": "base", "runway": "14"},
                ]
            },
            {
                "message": "T+11: Third aircraft turns final.",
                "updates": [
                    {"callsign": "Diamond 45X", "state": "final", "runway": "14"},
                ]
            },
            {
                "message": "T+12: Third aircraft short final.",
                "updates": [
                    {"callsign": "Diamond 45X", "state": "short_final", "runway": "14"},
                ]
            },
            {
                "message": "T+13: Third aircraft lands.",
                "updates": [
                    {"callsign": "Diamond 45X", "state": "landed_rollout", "runway": "14"},
                ]
            },
            {
                "message": "T+14: Third aircraft clears runway.",
                "updates": [
                    {"callsign": "Diamond 45X", "state": "entered_taxiway", "runway": "14"},
                ]
            },
        ]
    },

    "three_plane_conflict": {
        "name": "Three Aircraft With Spacing Conflict",
        "steps": [
            {
                "message": "T+0: Two aircraft approach the same entry area.",
                "updates": [
                    {"callsign": "Cherokee 56T", "state": "downwind", "runway": "14"},
                    {"callsign": "Cessna 23A", "state": "forty_five_entry", "runway": "14"},
                    {"callsign": "Diamond 45X", "state": "forty_five_entry", "runway": "14"},
                ]
            },
            {
                "message": "T+1: Two aircraft are now on downwind.",
                "updates": [
                    {"callsign": "Cherokee 56T", "state": "base", "runway": "14"},
                    {"callsign": "Cessna 23A", "state": "downwind", "runway": "14"},
                    {"callsign": "Diamond 45X", "state": "downwind", "runway": "14"},
                ]
            },
            {
                "message": "T+2: Two aircraft turn base at the same time.",
                "updates": [
                    {"callsign": "Cherokee 56T", "state": "final", "runway": "14"},
                    {"callsign": "Cessna 23A", "state": "base", "runway": "14"},
                    {"callsign": "Diamond 45X", "state": "base", "runway": "14"},
                ]
            },
            {
                "message": "T+3: Two aircraft converge on final.",
                "updates": [
                    {"callsign": "Cherokee 56T", "state": "short_final", "runway": "14"},
                    {"callsign": "Cessna 23A", "state": "final", "runway": "14"},
                    {"callsign": "Diamond 45X", "state": "final", "runway": "14"},
                ]
            },
            {
                "message": "T+4: Two aircraft are short final.",
                "updates": [
                    {"callsign": "Cessna 23A", "state": "short_final", "runway": "14"},
                    {"callsign": "Diamond 45X", "state": "short_final", "runway": "14"},
                ]
            },
        ]
    },

    "runway_occupied": {
        "name": "Runway Occupied + Final Conflict",
        "steps": [
            {
                "message": "T+0: Departure waiting, arrival established final.",
                "updates": [
                    {"callsign": "Cessna 23A", "state": "holding_short", "runway": "14"},
                    {"callsign": "Cherokee 56T", "state": "final", "runway": "14"},
                    {"callsign": "Diamond 45X", "state": "downwind", "runway": "14"},
                ]
            },
            {
                "message": "T+1: Aircraft enters runway while arrival is short final.",
                "updates": [
                    {"callsign": "Cessna 23A", "state": "entering_runway", "runway": "14"},
                    {"callsign": "Cherokee 56T", "state": "short_final", "runway": "14"},
                    {"callsign": "Diamond 45X", "state": "base", "runway": "14"},
                ]
            },
            {
                "message": "T+2: Departure rolling with following traffic turning final.",
                "updates": [
                    {"callsign": "Cessna 23A", "state": "departing", "runway": "14"},
                    {"callsign": "Diamond 45X", "state": "final", "runway": "14"},
                ]
            },
        ]
    },

    "opposite_direction": {
        "name": "Opposite Direction Runway Conflict",
        "steps": [
            {
                "message": "T+0: Runway 14 arrival and runway 32 departure develop opposite-direction conflict.",
                "updates": [
                    {"callsign": "Cherokee 56T", "state": "final", "runway": "14"},
                    {"callsign": "Diamond 45X", "state": "downwind", "runway": "14"},
                    {"callsign": "Cessna 23A", "state": "departing", "runway": "32"},
                ]
            },
            {
                "message": "T+1: Opposite-direction conflict continues.",
                "updates": [
                    {"callsign": "Cherokee 56T", "state": "short_final", "runway": "14"},
                    {"callsign": "Diamond 45X", "state": "base", "runway": "14"},
                    {"callsign": "Cessna 23A", "state": "entering_runway", "runway": "32"},
                ]
            },
        ]
    }
}


# ─────────────────────────────────────────────────────────────────────────────
# Map positions
# ─────────────────────────────────────────────────────────────────────────────

BACKEND_STATE_POSITIONS_RWY14 = {
    "taxiing": (300, 380),
    "holding_short": (268, 508),
    "entering_runway": (248, 518),
    "departing": (255, 460),
    "landed_rollout": (258, 440),
    "short_final": (222, 583),
    "final": (206, 618),
    "base": (420, 625),
    "downwind": (500, 330),
    "crosswind": (350, 88),
    "upwind": (192, 330),
    "forty_five_entry": (560, 238),
    "entered_taxiway": (302, 490),
    "clear_of_runway": (302, 490),
    "unknown": (260, 335),
}

BACKEND_STATE_POSITIONS_RWY32 = {
    "taxiing": (290, 380),
    "holding_short": (274, 172),
    "entering_runway": (278, 162),
    "departing": (265, 220),
    "landed_rollout": (264, 240),
    "short_final": (330, 112),
    "final": (370, 75),
    "base": (150, 95),
    "downwind": (140, 360),
    "crosswind": (350, 610),
    "upwind": (370, 320),
    "forty_five_entry": (105, 250),
    "entered_taxiway": (290, 200),
    "clear_of_runway": (290, 200),
    "unknown": (260, 335),
}


def get_backend_position(state, runway):
    pos_map = BACKEND_STATE_POSITIONS_RWY32 if runway == "32" else BACKEND_STATE_POSITIONS_RWY14
    return pos_map.get(state, pos_map["unknown"])


# ─────────────────────────────────────────────────────────────────────────────
# CTAF call generator
# ─────────────────────────────────────────────────────────────────────────────

def make_ctaf_call(callsign, state, runway):
    airport = "San Martin traffic"

    phrases = {
        "taxiing": f"{callsign} taxiing to runway {runway}",
        "holding_short": f"{callsign} holding short runway {runway}",
        "entering_runway": f"{callsign} entering runway {runway}",
        "departing": f"{callsign} departing runway {runway}",
        "upwind": f"{callsign} upwind runway {runway}",
        "crosswind": f"{callsign} turning crosswind runway {runway}",
        "downwind": f"{callsign} downwind runway {runway}",
        "base": f"{callsign} turning base runway {runway}",
        "final": f"{callsign} final runway {runway}",
        "short_final": f"{callsign} short final runway {runway}",
        "forty_five_entry": f"{callsign} entering forty-five for runway {runway}",
        "landed_rollout": f"{callsign} landed rollout runway {runway}",
        "entered_taxiway": f"{callsign} clear of runway {runway}",
        "clear_of_runway": f"{callsign} clear of runway {runway}",
    }

    phrase = phrases.get(state, f"{callsign} position update runway {runway}")
    return f"{airport}, {phrase}, San Martin."


# ─────────────────────────────────────────────────────────────────────────────
# Aircraft state and conflict detection
# ─────────────────────────────────────────────────────────────────────────────

def reset_aircraft():
    aircraft.clear()
    active_alerts.clear()


def get_all_aircraft():
    return [{"callsign": callsign, **data} for callsign, data in aircraft.items()]


def safe_float(value):
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(value)
    except ValueError:
        return None


def set_aircraft_without_check(callsign, state, runway="14", source="manual", x=None, y=None):
    if x is None or y is None:
        x, y = get_backend_position(state, runway)

    aircraft[callsign] = {
        "state": state,
        "runway": runway,
        "label": callsign,
        "x": float(x),
        "y": float(y),
        "source": source
    }


def apply_aircraft_update(callsign, state, runway="14", source="manual", x=None, y=None):
    set_aircraft_without_check(callsign, state, runway, source, x, y)
    conflicts = check_conflicts()

    return {
        "callsign": callsign,
        "state": state,
        "runway": runway,
        "conflicts": conflicts,
        "aircraft": get_all_aircraft()
    }


def check_conflicts():
    global active_alerts

    alerts = []
    current_alerts = set()
    ac_list = list(aircraft.items())

    same_state_pair_keys = set()
    runway_conflict_pair_keys = set()

    groups = {}

    for callsign, data in ac_list:
        key = (data["state"], data.get("runway", ""))
        groups.setdefault(key, []).append(callsign)

    for (state, runway), callsigns in groups.items():
        if state in PATTERN_STATES and len(callsigns) >= 2:
            for a, b in combinations(callsigns, 2):
                same_state_pair_keys.add(tuple(sorted([a, b])))

    for runway in ["14", "32"]:
        final_aircraft = [
            cs for cs, d in ac_list
            if d["state"] in ("final", "short_final") and d.get("runway") == runway
        ]

        runway_aircraft = [
            cs for cs, d in ac_list
            if d["state"] in ("entering_runway", "departing", "landed_rollout") and d.get("runway") == runway
        ]

        for final_ac in final_aircraft:
            for runway_ac in runway_aircraft:
                runway_conflict_pair_keys.add(tuple(sorted([final_ac, runway_ac])))

    def emit_once(signature, alert_type, message):
        current_alerts.add(signature)

        if signature not in active_alerts:
            alerts.append({
                "type": alert_type,
                "message": message
            })

    # Rule 1: proximity conflict
    for i in range(len(ac_list)):
        cs1, d1 = ac_list[i]

        for j in range(i + 1, len(ac_list)):
            cs2, d2 = ac_list[j]

            pair_key = tuple(sorted([cs1, cs2]))

            if pair_key in same_state_pair_keys or pair_key in runway_conflict_pair_keys:
                continue

            if d1["state"] not in PATTERN_STATES or d2["state"] not in PATTERN_STATES:
                continue

            x1, y1 = d1.get("x"), d1.get("y")
            x2, y2 = d2.get("x"), d2.get("y")

            if None in (x1, y1, x2, y2):
                continue

            distance_px = ((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5

            if distance_px < 35:
                emit_once(
                    ("proximity_critical", pair_key),
                    "critical",
                    f"CRITICAL ALERT: {cs1} and {cs2} are very close in the pattern. Verify spacing immediately."
                )

            elif distance_px < 75:
                emit_once(
                    ("proximity_advisory", pair_key),
                    "advisory",
                    f"ADVISORY: {cs1} and {cs2} are close to each other in the pattern. Monitor spacing and sequence."
                )

    # Rule 2: same leg conflict
    for (state, runway), callsigns in groups.items():
        if state in PATTERN_STATES and len(callsigns) >= 2:
            names = " and ".join(callsigns)

            emit_once(
                ("same_state", state, runway, tuple(sorted(callsigns))),
                "critical",
                f"CRITICAL ALERT: Multiple aircraft in {state.replace('_', ' ')} runway {runway}: {names}. Verify spacing and position."
            )

    # Rule 3: 45-entry and downwind
    for runway in ["14", "32"]:
        entries = [
            cs for cs, d in ac_list
            if d["state"] == "forty_five_entry" and d.get("runway") == runway
        ]

        downwinds = [
            cs for cs, d in ac_list
            if d["state"] == "downwind" and d.get("runway") == runway
        ]

        for entry in entries:
            for downwind in downwinds:
                pair_key = tuple(sorted([entry, downwind]))

                if pair_key in same_state_pair_keys or pair_key in runway_conflict_pair_keys:
                    continue

                emit_once(
                    ("entry_downwind", runway, pair_key),
                    "advisory",
                    f"ADVISORY: {entry} is on 45° entry and {downwind} is on downwind runway {runway}. Verify spacing and sequence."
                )

    # Rule 4: runway occupied while someone is on final
    for runway in ["14", "32"]:
        final_aircraft = [
            cs for cs, d in ac_list
            if d["state"] in ("final", "short_final") and d.get("runway") == runway
        ]

        runway_aircraft = [
            cs for cs, d in ac_list
            if d["state"] in ("entering_runway", "departing", "landed_rollout") and d.get("runway") == runway
        ]

        for final_ac in final_aircraft:
            for runway_ac in runway_aircraft:
                pair_key = tuple(sorted([final_ac, runway_ac]))

                emit_once(
                    ("runway_occupied", runway, pair_key),
                    "critical",
                    f"CRITICAL ALERT: {final_ac} is on final and {runway_ac} is on runway {runway}. Runway conflict."
                )

    # Rule 5: opposite direction
    rwy14_active = [
        cs for cs, d in ac_list
        if d.get("runway") == "14" and d["state"] in PATTERN_STATES
    ]

    rwy32_active = [
        cs for cs, d in ac_list
        if d.get("runway") == "32" and d["state"] in PATTERN_STATES
    ]

    if rwy14_active and rwy32_active:
        emit_once(
            ("opposite_direction", tuple(sorted(rwy14_active)), tuple(sorted(rwy32_active))),
            "critical",
            f"CRITICAL ALERT: Opposite-direction traffic. Runway 14: {', '.join(rwy14_active)}. Runway 32: {', '.join(rwy32_active)}. Verify traffic direction."
        )

    active_alerts = current_alerts
    return alerts


# ─────────────────────────────────────────────────────────────────────────────
# Built-in simulation
# ─────────────────────────────────────────────────────────────────────────────

def process_sim_step(scenario_key, step_index):
    scenario = SIM_SCENARIOS.get(scenario_key)

    if not scenario:
        return {
            "error": "Unknown simulation scenario",
            "aircraft": get_all_aircraft(),
            "conflicts": []
        }

    steps = scenario["steps"]

    if step_index >= len(steps):
        return {
            "done": True,
            "message": f"Simulation complete: {scenario['name']}",
            "aircraft": get_all_aircraft(),
            "conflicts": []
        }

    step = steps[step_index]
    updates = step.get("updates", [step])

    ctaf_calls = []

    for update in updates:
        callsign = update["callsign"]
        state = update["state"]
        runway = update.get("runway", "14")

        set_aircraft_without_check(
            callsign=callsign,
            state=state,
            runway=runway,
            source="simulated"
        )

        ctaf_calls.append(make_ctaf_call(callsign, state, runway))

    conflicts = check_conflicts()

    return {
        "done": False,
        "step": step_index,
        "scenario": scenario_key,
        "message": step.get("message", f"SIM TIME {step_index}: updated {len(updates)} aircraft"),
        "ctaf_calls": ctaf_calls,
        "conflicts": conflicts,
        "aircraft": get_all_aircraft()
    }


# ─────────────────────────────────────────────────────────────────────────────
# ADS-B replay
# ─────────────────────────────────────────────────────────────────────────────

def normalize_csv_row(row):
    return {
        str(key).strip(): str(value).strip()
        for key, value in row.items()
        if key is not None
    }


def load_adsb_replay_file():
    global adsb_replay_rows

    adsb_replay_rows = []
    note = ""

    hidden_txt_name = ADSB_REPLAY_FILE + ".txt"

    if not os.path.exists(ADSB_REPLAY_FILE) and os.path.exists(hidden_txt_name):
        return False, f"Found {hidden_txt_name}, but the app needs {ADSB_REPLAY_FILE}. Rename it exactly to {ADSB_REPLAY_FILE}."

    if not os.path.exists(ADSB_REPLAY_FILE):
        create_sample_adsb_file()
        note = f"{ADSB_REPLAY_FILE} was missing, so SkySensAI created a sample ADS-B file automatically."

    if os.path.getsize(ADSB_REPLAY_FILE) == 0:
        create_sample_adsb_file()
        note = f"{ADSB_REPLAY_FILE} was empty, so SkySensAI replaced it with sample ADS-B data."

    with open(ADSB_REPLAY_FILE, newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)

        for raw_row in reader:
            row = normalize_csv_row(raw_row)
            callsign = row.get("callsign") or row.get("flight")
            state = row.get("state")

            if not callsign or not state:
                continue

            adsb_replay_rows.append(row)

    if len(adsb_replay_rows) == 0:
        create_sample_adsb_file()

        with open(ADSB_REPLAY_FILE, newline="", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)

            for raw_row in reader:
                row = normalize_csv_row(raw_row)
                callsign = row.get("callsign") or row.get("flight")
                state = row.get("state")

                if callsign and state:
                    adsb_replay_rows.append(row)

        note = f"{ADSB_REPLAY_FILE} had no usable data rows, so SkySensAI replaced it with sample ADS-B data."

    if len(adsb_replay_rows) == 0:
        return False, "ADS-B file still has zero usable rows. Check the CSV header and data."

    print(f"Loaded {len(adsb_replay_rows)} ADS-B rows from {ADSB_REPLAY_FILE}")
    return True, note or f"Loaded {len(adsb_replay_rows)} ADS-B rows from {ADSB_REPLAY_FILE}."


def process_adsb_replay_step(step_index):
    if not adsb_replay_rows:
        loaded, note = load_adsb_replay_file()

        if not loaded:
            return {
                "error": note,
                "aircraft": get_all_aircraft(),
                "conflicts": []
            }

    else:
        note = ""

    if step_index >= len(adsb_replay_rows):
        return {
            "done": True,
            "message": "ADS-B replay complete.",
            "aircraft": get_all_aircraft(),
            "conflicts": []
        }

    row = adsb_replay_rows[step_index]

    callsign = (row.get("callsign") or row.get("flight") or "UNKNOWN").strip()
    runway = (row.get("runway") or "14").strip()
    state = (row.get("state") or "unknown").strip()

    x = safe_float(row.get("x"))
    y = safe_float(row.get("y"))

    result = apply_aircraft_update(
        callsign=callsign,
        state=state,
        runway=runway,
        source="adsb_replay",
        x=x,
        y=y
    )

    ctaf_call = make_ctaf_call(callsign, state, runway)

    result["done"] = False
    result["step"] = step_index
    result["ctaf_call"] = ctaf_call
    result["message"] = f"ADS-B REPLAY CTAF: {ctaf_call}"

    if step_index == 0 and note:
        result["load_note"] = note

    return result


# ─────────────────────────────────────────────────────────────────────────────
# CTAF parser
# ─────────────────────────────────────────────────────────────────────────────

PHONETIC_DIGITS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "niner": "9"
}

PHONETIC_ALPHA = {
    "alpha": "A", "bravo": "B", "charlie": "C", "delta": "D", "echo": "E",
    "foxtrot": "F", "golf": "G", "hotel": "H", "india": "I", "juliet": "J",
    "kilo": "K", "lima": "L", "mike": "M", "november": "N", "oscar": "O",
    "papa": "P", "quebec": "Q", "romeo": "R", "sierra": "S", "tango": "T",
    "uniform": "U", "victor": "V", "whiskey": "W", "xray": "X", "x-ray": "X",
    "yankee": "Y", "zulu": "Z"
}

AIRCRAFT_TYPES = [
    "cherokee", "cessna", "piper", "diamond", "beechcraft", "cirrus",
    "mooney", "bonanza", "archer", "warrior", "skyhawk", "skylane",
    "seminole", "seneca", "twin", "king air", "baron"
]


def normalize_spoken(text):
    text = text.lower()

    for word, digit in PHONETIC_DIGITS.items():
        text = re.sub(r'\b' + word + r'\b', digit, text)

    for word, letter in PHONETIC_ALPHA.items():
        text = re.sub(r'\b' + word + r'\b', letter, text)

    return text


def extract_callsign(text):
    """
    Extract aircraft type + callsign from a CTAF call.

    This fixes typed calls like:
    'San Martin traffic, Cessna 7TX downwind runway 14, San Martin.'

    Old bad parse:
    Cessna 7TXDOWNWIND

    Correct parse:
    Cessna 7TX
    """

    norm = normalize_spoken(text.lower())

    stop_words = [
        "entering", "turning", "on", "departing", "holding", "clear",
        "landing", "taking", "line", "runway", "traffic", "san martin",
        "downwind", "base", "final", "short final", "crosswind", "upwind",
        "forty five", "forty-five", "45", "taxiing", "taxi", "rollout",
        "left", "right", "straight", "straight in", "left downwind",
        "right downwind", "left base", "right base"
    ]

    stop_pattern = "|".join(re.escape(word) for word in stop_words)

    for aircraft_type in AIRCRAFT_TYPES:
        pattern = (
            rf'\b{aircraft_type}\s+'
            rf'([a-zA-Z0-9\s]{{1,12}}?)'
            rf'(?=\s+(?:{stop_pattern})\b|,|$)'
        )

        match = re.search(pattern, norm)

        if match:
            raw = match.group(1).strip()
            callsign_id = re.sub(r'\s+', '', raw).upper()
            return f"{aircraft_type.capitalize()} {callsign_id}"

    return None


def extract_runway(text):
    norm = normalize_spoken(text.lower())

    if re.search(r'runway\s+14\b|runway\s+1\s*4\b|one\s+four\b|\b14\b', norm):
        return "14"

    if re.search(r'runway\s+32\b|runway\s+3\s*2\b|three\s+two\b|\b32\b', norm):
        return "32"

    return None


def extract_state(text):
    text = text.lower()

    if re.search(r'short\s+final', text):
        return "short_final"

    if re.search(r'45\s*degree\s*entry|45\s*entry|forty[\s-]?five\s*entry|entering\s*45|entering\s*forty[\s-]?five|on\s+the\s+45|on\s+45', text):
        return "forty_five_entry"

    if re.search(r'clear\s+of\s+runway|clear\s+runway|exited\s+runway|off\s+runway|on\s+taxiway|entered\s+taxiway|entered\s+the\s+taxiway', text):
        return "entered_taxiway"

    if re.search(r'holding\s+short', text):
        return "holding_short"

    if re.search(r'entering\s+runway|taking\s+the\s+runway|line\s+up', text):
        return "entering_runway"

    if re.search(r'taking\s+off|departing|departure', text):
        return "departing"

    if re.search(r'downwind', text):
        return "downwind"

    if re.search(r'crosswind', text):
        return "crosswind"

    if re.search(r'upwind', text):
        return "upwind"

    if re.search(r'\bbase\b', text):
        return "base"

    if re.search(r'\bfinal\b', text):
        return "final"

    if re.search(r'landed|rollout', text):
        return "landed_rollout"

    if re.search(r'taxi', text):
        return "taxiing"

    return None


def process_ctaf(text):
    callsign = extract_callsign(text)
    runway = extract_runway(text)
    state = extract_state(text)

    if not callsign:
        return {"error": "Could not identify callsign", "text": text}

    if not state:
        return {"error": f"Could not identify state for {callsign}", "text": text}

    previous_runway = aircraft.get(callsign, {}).get("runway")
    selected_runway = runway or previous_runway or "14"

    return apply_aircraft_update(
        callsign=callsign,
        state=state,
        runway=selected_runway,
        source="ctaf"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Flask routes
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML_PAGE)


@app.route("/api/ctaf", methods=["POST"])
def api_ctaf():
    data = request.json or {}
    text = data.get("text", "")
    return jsonify(process_ctaf(text))


@app.route("/api/reset", methods=["POST"])
def api_reset():
    reset_aircraft()
    return jsonify({"status": "reset", "aircraft": []})


@app.route("/api/aircraft", methods=["GET"])
def api_aircraft():
    return jsonify({"aircraft": get_all_aircraft()})


@app.route("/api/sim/step", methods=["POST"])
def api_sim_step():
    data = request.json or {}
    scenario = data.get("scenario", "three_plane_pattern")
    step = int(data.get("step", 0))
    return jsonify(process_sim_step(scenario, step))


@app.route("/api/adsb/step", methods=["POST"])
def api_adsb_step():
    data = request.json or {}
    step = int(data.get("step", 0))
    return jsonify(process_adsb_replay_step(step))


# ─────────────────────────────────────────────────────────────────────────────
# HTML / CSS / JS
# ─────────────────────────────────────────────────────────────────────────────

HTML_PAGE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>SkySensAI</title>

<style>
:root {
  --bg: #0a0e1a;
  --panel: #111827;
  --border: #1e2d45;
  --accent: #00c8ff;
  --accent2: #00ffa3;
  --warn: #ffb300;
  --crit: #ff3b3b;
  --text: #cdd9e5;
  --muted: #5a7a99;
  --grass: #0d1f12;
}

* {
  box-sizing: border-box;
}

html,
body {
  margin: 0;
  width: 100%;
  height: 100%;
  overflow: hidden;
}

body {
  background: var(--bg);
  color: var(--text);
  font-family: "Courier New", monospace;
  display: flex;
  flex-direction: column;
}

header {
  height: 58px;
  flex: 0 0 58px;
  background: var(--panel);
  border-bottom: 1px solid var(--border);
  padding: 10px 24px;
}

h1 {
  margin: 0;
  color: var(--accent);
  font-size: 1.1rem;
  letter-spacing: 0.08em;
}

.subtitle {
  color: var(--muted);
  font-size: 0.72rem;
  margin-top: 4px;
}

.main {
  flex: 1;
  min-height: 0;
  display: flex;
  overflow: hidden;
}

.left-panel {
  width: 380px;
  flex: 0 0 380px;
  min-height: 0;
  background: var(--panel);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.section-label {
  font-size: 0.65rem;
  color: var(--muted);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  padding: 10px 14px 6px;
  border-bottom: 1px solid var(--border);
}

.input-area {
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
}

textarea {
  width: 100%;
  min-height: 64px;
  background: #0d1624;
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 8px;
  font-family: inherit;
  resize: vertical;
}

.btn-row {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

button {
  font-family: inherit;
  font-size: 0.72rem;
  text-transform: uppercase;
  padding: 7px 10px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text);
  cursor: pointer;
}

#submit-btn {
  background: var(--accent);
  color: black;
  border-color: var(--accent);
  flex: 1;
  font-weight: bold;
}

#sim-btn,
#adsb-btn {
  color: var(--accent2);
  border-color: var(--accent2);
  flex: 1;
}

#sim-btn.running,
#adsb-btn.running {
  background: var(--accent2);
  color: black;
}

#step-btn,
#adsb-step-btn {
  color: var(--warn);
  border-color: var(--warn);
}

#reset-btn {
  color: var(--crit);
  border-color: var(--crit);
}

.sim-box {
  margin-top: 12px;
  padding: 10px;
  border: 1px solid var(--border);
  background: #0d1624;
  border-radius: 4px;
}

.sim-title {
  font-size: 0.62rem;
  color: var(--accent2);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  margin-bottom: 8px;
}

select {
  width: 100%;
  background: #0a0e1a;
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 7px;
  font-family: inherit;
  font-size: 0.72rem;
}

.alert-feed {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px 0;
}

.alert-item {
  padding: 8px 14px;
  border-left: 3px solid transparent;
  font-size: 0.75rem;
  line-height: 1.45;
  border-bottom: 1px solid rgba(30,45,69,0.5);
}

.alert-item.info {
  border-left-color: var(--accent);
  color: var(--text);
  background: rgba(0,200,255,0.04);
}

.alert-item.ctaf {
  border-left-color: var(--accent2);
  color: #b8ffe4;
  background: rgba(0,255,163,0.05);
}

.alert-item.advisory {
  border-left-color: var(--warn);
  color: #ffe08a;
  background: rgba(255,179,0,0.06);
}

.alert-item.critical {
  border-left-color: var(--crit);
  color: #ffaaaa;
  background: rgba(255,59,59,0.07);
}

.ts {
  color: var(--muted);
  font-size: 0.65rem;
  margin-bottom: 2px;
}

.ac-table {
  border-top: 1px solid var(--border);
  max-height: 180px;
  overflow-y: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.72rem;
}

th {
  background: #0d1624;
  color: var(--muted);
  font-weight: normal;
  padding: 5px 10px;
  text-align: left;
  font-size: 0.65rem;
}

td {
  padding: 5px 10px;
  border-top: 1px solid rgba(30,45,69,0.5);
}

.state-badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 0.65rem;
  background: rgba(0,200,255,0.12);
  color: var(--accent);
  border: 1px solid rgba(0,200,255,0.25);
}

.state-badge.critical-state {
  background: rgba(255,59,59,0.15);
  color: var(--crit);
  border-color: rgba(255,59,59,0.3);
}

.map-area {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.map-title {
  height: 34px;
  flex: 0 0 34px;
  padding: 8px 16px;
  font-size: 0.65rem;
  color: var(--muted);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  border-bottom: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
}

#airport-map {
  flex: 1;
  min-width: 0;
  min-height: 0;
  background: var(--grass);
  position: relative;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 10px;
}

#map-svg {
  display: block;
  width: 100%;
  height: 100%;
  max-width: 100%;
  max-height: 100%;
  background: #0d1f12;
  border: 1px solid rgba(30,45,69,0.55);
  border-radius: 8px;
}

.legend {
  position: absolute;
  bottom: 18px;
  right: 18px;
  background: rgba(10,14,26,0.88);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 8px 12px;
  font-size: 0.62rem;
  color: var(--muted);
  line-height: 1.9;
}

.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
  margin-right: 6px;
}
</style>
</head>

<body>
<header>
  <h1>SkySensAI</h1>
  <div class="subtitle">San Martin Airport E16 · Runway Safety Advisory Demo</div>
</header>

<div class="main">
  <div class="left-panel">
    <div class="section-label">CTAF Input</div>

    <div class="input-area">
      <textarea id="ctaf-input" placeholder="Example: San Martin traffic, Cessna 7TX downwind runway 14, San Martin."></textarea>

      <div class="btn-row">
        <button id="submit-btn" onclick="submitCTAF()">Transmit</button>
        <button id="mic-btn" onclick="toggleMic()">🎙</button>
        <button id="reset-btn" onclick="resetAll()">Reset</button>
      </div>

      <div class="sim-box">
        <div class="sim-title">Built-In Timeline Simulation</div>

        <select id="scenario-select">
          <option value="three_plane_pattern">Three Aircraft Pattern Flow</option>
          <option value="three_plane_conflict">Three Aircraft With Spacing Conflict</option>
          <option value="runway_occupied">Runway Occupied + Final Conflict</option>
          <option value="opposite_direction">Opposite Direction Conflict</option>
        </select>

        <div class="btn-row">
          <button id="sim-btn" onclick="toggleSimulation()">Start Sim</button>
          <button id="step-btn" onclick="stepSimulation()">Step</button>
        </div>
      </div>

      <div class="sim-box">
        <div class="sim-title">Historical ADS-B Replay</div>

        <div class="btn-row">
          <button id="adsb-btn" onclick="toggleAdsbReplay()">Start ADS-B Replay</button>
          <button id="adsb-step-btn" onclick="stepAdsbReplay()">ADS-B Step</button>
        </div>
      </div>
    </div>

    <div class="section-label">Runway Safety Advisory Feed</div>

    <div class="alert-feed" id="alert-feed">
      <div class="alert-item info">
        <div class="ts">SYSTEM</div>
        SkySensAI online. This is a non-controlling advisory demo only.
      </div>
    </div>

    <div class="ac-table">
      <div class="section-label">Known Traffic</div>
      <table>
        <thead>
          <tr>
            <th>Callsign</th>
            <th>State</th>
            <th>Rwy</th>
          </tr>
        </thead>
        <tbody id="ac-tbody"></tbody>
      </table>
    </div>
  </div>

  <div class="map-area">
    <div class="map-title">
      <span>San Martin Airport · E16</span>
      <span style="color:var(--accent2)">Timeline Snapshot View · RWY 14/32</span>
    </div>

    <div id="airport-map">
      <svg id="map-svg" viewBox="0 0 700 680" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet">
        <defs>
          <filter id="glow">
            <feGaussianBlur stdDeviation="2" result="blur"/>
            <feMerge>
              <feMergeNode in="blur"/>
              <feMergeNode in="SourceGraphic"/>
            </feMerge>
          </filter>

          <marker id="arrow" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">
            <path d="M0,0 L6,3 L0,6 Z" fill="rgba(0,200,255,0.6)"/>
          </marker>

          <marker id="arrow-warn" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">
            <path d="M0,0 L6,3 L0,6 Z" fill="rgba(255,179,0,0.7)"/>
          </marker>
        </defs>

        <rect x="0" y="0" width="700" height="680" fill="#0d1f12"/>

        <rect x="20" y="20" width="660" height="640" rx="8"
          fill="none" stroke="#1a2a3a" stroke-width="2" stroke-dasharray="6,10" opacity="0.45"/>

        <polygon points="296,140 268,140 224,530 252,530"
          fill="#2c3a4e" stroke="#4a5e78" stroke-width="1"/>

        <line x1="282" y1="150" x2="238" y2="520"
          stroke="#fff" stroke-width="1" stroke-dasharray="20,14" opacity="0.45"/>

        <text x="282" y="136" fill="#fff" font-size="12" font-family="monospace" text-anchor="middle">32</text>
        <text x="237" y="545" fill="#fff" font-size="12" font-family="monospace" text-anchor="middle">14</text>

        <polygon points="310,165 296,165 252,530 266,530"
          fill="#1e2d3e" stroke="#2a4060" stroke-width="1" opacity="0.9"/>

        <polygon points="308,200 370,195 380,320 320,328 306,330"
          fill="#182535" stroke="#243650" stroke-width="1"/>

        <polygon points="266,190 296,185 310,200 278,205" fill="#1e2d3e" stroke="#2a4060"/>
        <polygon points="246,360 302,352 306,367 250,375" fill="#1e2d3e" stroke="#2a4060"/>
        <polygon points="231,505 296,498 300,512 235,519" fill="#1e2d3e" stroke="#2a4060"/>

        <rect x="378" y="195" width="52" height="30" rx="2" fill="#1a2a3e" stroke="#2a4060"/>
        <rect x="434" y="195" width="52" height="30" rx="2" fill="#1a2a3e" stroke="#2a4060"/>
        <rect x="490" y="195" width="52" height="30" rx="2" fill="#1a2a3e" stroke="#2a4060"/>
        <rect x="378" y="232" width="52" height="30" rx="2" fill="#1a2a3e" stroke="#2a4060"/>
        <rect x="434" y="232" width="52" height="30" rx="2" fill="#1a2a3e" stroke="#2a4060"/>
        <rect x="490" y="232" width="52" height="30" rx="2" fill="#1a2a3e" stroke="#2a4060"/>
        <rect x="378" y="269" width="52" height="30" rx="2" fill="#1a2a3e" stroke="#2a4060"/>
        <rect x="434" y="269" width="52" height="30" rx="2" fill="#1a2a3e" stroke="#2a4060"/>

        <line x1="176" y1="540" x2="220" y2="148"
          stroke="rgba(0,200,255,0.35)" stroke-width="2" stroke-dasharray="8,5"
          marker-end="url(#arrow)"/>
        <text x="168" y="360" fill="rgba(0,200,255,0.7)" font-size="11"
          font-family="monospace" text-anchor="middle" transform="rotate(-77,168,360)">UPWIND</text>

        <line x1="220" y1="148" x2="480" y2="78"
          stroke="rgba(0,200,255,0.35)" stroke-width="2" stroke-dasharray="8,5"
          marker-end="url(#arrow)"/>
        <text x="350" y="96" fill="rgba(0,200,255,0.7)" font-size="11"
          font-family="monospace" text-anchor="middle">CROSSWIND</text>

        <line x1="480" y1="78" x2="525" y2="555"
          stroke="rgba(0,200,255,0.35)" stroke-width="2" stroke-dasharray="8,5"
          marker-end="url(#arrow)"/>
        <text x="546" y="330" fill="rgba(0,200,255,0.7)" font-size="11"
          font-family="monospace" text-anchor="middle" transform="rotate(-77,546,330)">DOWNWIND</text>

        <line x1="525" y1="555" x2="200" y2="635"
          stroke="rgba(0,200,255,0.35)" stroke-width="2" stroke-dasharray="8,5"
          marker-end="url(#arrow)"/>
        <text x="360" y="632" fill="rgba(0,200,255,0.7)" font-size="11"
          font-family="monospace" text-anchor="middle">BASE</text>

        <line x1="200" y1="635" x2="236" y2="530"
          stroke="rgba(0,255,100,0.5)" stroke-width="2.5" stroke-dasharray="8,4"
          marker-end="url(#arrow)"/>
        <text x="188" y="590" fill="rgba(0,255,100,0.8)" font-size="11"
          font-family="monospace" text-anchor="middle" transform="rotate(-77,188,590)">FINAL</text>

        <line x1="590" y1="200" x2="505" y2="310"
          stroke="rgba(255,179,0,0.45)" stroke-width="2" stroke-dasharray="10,5"
          marker-end="url(#arrow-warn)"/>
        <text x="570" y="240" fill="rgba(255,179,0,0.75)" font-size="10"
          font-family="monospace" text-anchor="middle" transform="rotate(-55,570,240)">45° ENTRY</text>

        <text x="350" y="42" fill="rgba(90,122,153,0.6)" font-size="11"
          font-family="monospace" text-anchor="middle" letter-spacing="3">SAN MARTIN AIRPORT · E16</text>

        <g id="aircraft-layer"></g>
      </svg>

      <div class="legend">
        <div><span class="legend-dot" style="background:rgba(0,200,255,0.7)"></span>Pattern leg</div>
        <div><span class="legend-dot" style="background:rgba(0,255,100,0.8)"></span>Final</div>
        <div><span class="legend-dot" style="background:rgba(255,179,0,0.7)"></span>45° Entry</div>
        <div><span class="legend-dot" style="background:var(--accent2)"></span>Aircraft</div>
      </div>
    </div>
  </div>
</div>

<script>
const STATE_POSITIONS = {
  "taxiing":          { x: 300, y: 380 },
  "holding_short":    { x: 268, y: 508 },
  "entering_runway":  { x: 248, y: 518 },
  "departing":        { x: 255, y: 460 },
  "landed_rollout":   { x: 258, y: 440 },
  "short_final":      { x: 222, y: 583 },
  "final":            { x: 206, y: 618 },
  "base":             { x: 420, y: 625 },
  "downwind":         { x: 500, y: 330 },
  "crosswind":        { x: 350, y: 88 },
  "upwind":           { x: 192, y: 330 },
  "forty_five_entry": { x: 560, y: 238 },
  "entered_taxiway":  { x: 302, y: 490 },
  "clear_of_runway":  { x: 302, y: 490 },
  "unknown":          { x: 260, y: 335 },
};

const STATE_POSITIONS_RWY32 = {
  "taxiing":          { x: 290, y: 380 },
  "holding_short":    { x: 274, y: 172 },
  "entering_runway":  { x: 278, y: 162 },
  "departing":        { x: 265, y: 220 },
  "landed_rollout":   { x: 264, y: 240 },
  "short_final":      { x: 330, y: 112 },
  "final":            { x: 370, y: 75 },
  "base":             { x: 150, y: 95 },
  "downwind":         { x: 140, y: 360 },
  "crosswind":        { x: 350, y: 610 },
  "upwind":           { x: 370, y: 320 },
  "forty_five_entry": { x: 105, y: 250 },
  "entered_taxiway":  { x: 290, y: 200 },
  "clear_of_runway":  { x: 290, y: 200 },
  "unknown":          { x: 260, y: 335 },
};

const CRITICAL_STATES = ["entering_runway", "departing", "short_final", "final", "landed_rollout"];

let acDots = {};
let speechQueue = Promise.resolve();

let simRunning = false;
let simStepIndex = 0;

let adsbReplayRunning = false;
let adsbStepIndex = 0;

const SIM_ANIMATION_MS = 7600;
const POST_STEP_BUFFER_MS = 1400;
const MIN_STEP_MS = SIM_ANIMATION_MS + POST_STEP_BUFFER_MS;

const recentAlertTimes = new Map();
const ALERT_DUPLICATE_WINDOW_MS = 9000;

let availableVoices = [];
let pilotVoice = null;
let advisoryVoice = null;
let criticalVoice = null;

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function getPosition(state, runway) {
  const posMap = runway === "32" ? STATE_POSITIONS_RWY32 : STATE_POSITIONS;
  return posMap[state] || STATE_POSITIONS["unknown"];
}

function getStateColor(state) {
  if (CRITICAL_STATES.includes(state)) return "#ff3b3b";
  if (["downwind", "base", "crosswind", "upwind", "forty_five_entry", "holding_short"].includes(state)) return "#00c8ff";
  return "#00ffa3";
}

function loadVoices() {
  if (!window.speechSynthesis) return;

  availableVoices = window.speechSynthesis.getVoices();
  if (!availableVoices || availableVoices.length === 0) return;

  function findVoice(preferredNames, excludedVoice = null) {
    for (const preferred of preferredNames) {
      const match = availableVoices.find(v =>
        v.name.toLowerCase().includes(preferred.toLowerCase()) &&
        (!excludedVoice || v.name !== excludedVoice.name)
      );

      if (match) return match;
    }

    const fallback = availableVoices.find(v =>
      (!excludedVoice || v.name !== excludedVoice.name) &&
      v.lang.toLowerCase().startsWith("en")
    );

    return fallback || availableVoices[0];
  }

  pilotVoice = findVoice([
    "Alex",
    "Samantha",
    "Google US English",
    "Microsoft Guy",
    "Daniel"
  ]);

  advisoryVoice = findVoice([
    "Victoria",
    "Karen",
    "Moira",
    "Microsoft Aria",
    "Google UK English Female",
    "Tessa"
  ], pilotVoice);

  criticalVoice = findVoice([
    "Fred",
    "Ralph",
    "Microsoft David",
    "Google UK English Male",
    "Daniel"
  ], advisoryVoice);

  if (!criticalVoice) criticalVoice = advisoryVoice;
}

if (window.speechSynthesis) {
  loadVoices();
  window.speechSynthesis.onvoiceschanged = loadVoices;
}

function shouldSuppressAlert(type, message) {
  if (!["critical", "advisory"].includes(type)) {
    return false;
  }

  const normalized = `${type}:${message}`.toLowerCase().replace(/\s+/g, " ").trim();
  const now = Date.now();
  const lastTime = recentAlertTimes.get(normalized);

  if (lastTime && now - lastTime < ALERT_DUPLICATE_WINDOW_MS) {
    return true;
  }

  recentAlertTimes.set(normalized, now);

  for (const [key, value] of recentAlertTimes.entries()) {
    if (now - value > ALERT_DUPLICATE_WINDOW_MS) {
      recentAlertTimes.delete(key);
    }
  }

  return false;
}

function setDotPosition(dot, x, y) {
  dot.g.setAttribute("transform", `translate(${x},${y})`);
}

function animateDotTo(dot, targetX, targetY, duration = SIM_ANIMATION_MS) {
  if (dot.animFrame) {
    cancelAnimationFrame(dot.animFrame);
  }

  const startX = dot.x ?? targetX;
  const startY = dot.y ?? targetY;
  const startTime = performance.now();

  function easeInOut(t) {
    return t < 0.5
      ? 2 * t * t
      : 1 - Math.pow(-2 * t + 2, 2) / 2;
  }

  function step(now) {
    const rawT = Math.min((now - startTime) / duration, 1);
    const t = easeInOut(rawT);

    const x = startX + (targetX - startX) * t;
    const y = startY + (targetY - startY) * t;

    setDotPosition(dot, x, y);

    if (rawT < 1) {
      dot.animFrame = requestAnimationFrame(step);
    } else {
      dot.x = targetX;
      dot.y = targetY;
      setDotPosition(dot, targetX, targetY);
    }
  }

  dot.animFrame = requestAnimationFrame(step);
}

function updateMapDots(aircraftList) {
  const layer = document.getElementById("aircraft-layer");
  const seen = new Set();

  for (const ac of aircraftList) {
    seen.add(ac.callsign);

    const fallback = getPosition(ac.state, ac.runway);
    const pos = {
      x: ac.x !== undefined && ac.x !== null ? Number(ac.x) : fallback.x,
      y: ac.y !== undefined && ac.y !== null ? Number(ac.y) : fallback.y
    };

    const color = getStateColor(ac.state);

    if (!acDots[ac.callsign]) {
      const g = document.createElementNS("http://www.w3.org/2000/svg", "g");

      const pulse = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      pulse.setAttribute("r", "7");
      pulse.setAttribute("stroke", color);
      pulse.setAttribute("stroke-width", "1");
      pulse.setAttribute("fill", "none");
      pulse.setAttribute("opacity", "0.5");
      pulse.innerHTML = `<animate attributeName="r" values="7;16;7" dur="2s" repeatCount="indefinite"/>
                         <animate attributeName="opacity" values="0.6;0;0.6" dur="2s" repeatCount="indefinite"/>`;

      const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      circle.setAttribute("r", "7");
      circle.setAttribute("stroke", "#fff");
      circle.setAttribute("stroke-width", "1.5");
      circle.setAttribute("fill", color);

      const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
      text.setAttribute("y", "20");
      text.setAttribute("fill", color);
      text.setAttribute("font-size", "9");
      text.setAttribute("font-family", "monospace");
      text.setAttribute("text-anchor", "middle");
      text.setAttribute("filter", "url(#glow)");
      text.textContent = ac.callsign;

      g.appendChild(pulse);
      g.appendChild(circle);
      g.appendChild(text);
      layer.appendChild(g);

      acDots[ac.callsign] = {
        g,
        circle,
        text,
        pulse,
        x: pos.x,
        y: pos.y,
        animFrame: null
      };

      setDotPosition(acDots[ac.callsign], pos.x, pos.y);
    }

    const dot = acDots[ac.callsign];

    dot.circle.setAttribute("fill", color);
    dot.text.setAttribute("fill", color);
    dot.text.textContent = ac.callsign;
    dot.pulse.setAttribute("stroke", color);

    animateDotTo(dot, pos.x, pos.y, SIM_ANIMATION_MS);
  }

  for (const callsign of Object.keys(acDots)) {
    if (!seen.has(callsign)) {
      if (acDots[callsign].animFrame) {
        cancelAnimationFrame(acDots[callsign].animFrame);
      }

      acDots[callsign].g.remove();
      delete acDots[callsign];
    }
  }
}

function queueSpeakText(text, type) {
  if (!window.speechSynthesis) return Promise.resolve();

  loadVoices();

  speechQueue = speechQueue.then(() => {
    return new Promise(resolve => {
      const utterance = new SpeechSynthesisUtterance(text);

      if (type === "ctaf") {
        utterance.voice = pilotVoice;
        utterance.rate = 0.92;
        utterance.pitch = 1.05;
      } else if (type === "critical") {
        utterance.voice = criticalVoice || advisoryVoice;
        utterance.rate = 0.78;
        utterance.pitch = 0.72;
      } else if (type === "advisory") {
        utterance.voice = advisoryVoice;
        utterance.rate = 0.86;
        utterance.pitch = 0.9;
      } else {
        utterance.voice = advisoryVoice;
        utterance.rate = 0.9;
        utterance.pitch = 1.0;
      }

      utterance.volume = 1.0;
      utterance.onend = resolve;
      utterance.onerror = resolve;

      window.speechSynthesis.speak(utterance);
    });
  });

  return speechQueue;
}

function addAlert(type, message, callsign = null) {
  if (shouldSuppressAlert(type, message)) {
    return Promise.resolve();
  }

  const feed = document.getElementById("alert-feed");
  const item = document.createElement("div");
  item.className = `alert-item ${type}`;

  const ts = document.createElement("div");
  ts.className = "ts";
  ts.textContent = new Date().toLocaleTimeString("en-US", {hour12:false}) + (callsign ? ` · ${callsign}` : "");

  const msg = document.createElement("div");
  msg.textContent = message;

  item.appendChild(ts);
  item.appendChild(msg);
  feed.insertBefore(item, feed.firstChild);

  if (["critical", "advisory", "ctaf"].includes(type)) {
    return queueSpeakText(
      message.replace("SIM CTAF: ", "").replace("ADS-B REPLAY CTAF: ", ""),
      type
    );
  }

  return Promise.resolve();
}

function updateAcTable(aircraftList) {
  const tbody = document.getElementById("ac-tbody");
  tbody.innerHTML = "";

  for (const ac of aircraftList) {
    const tr = document.createElement("tr");
    const isCrit = CRITICAL_STATES.includes(ac.state);

    tr.innerHTML = `
      <td style="color:var(--accent2)">${ac.callsign}</td>
      <td><span class="state-badge ${isCrit ? "critical-state" : ""}">${ac.state.replace(/_/g, " ")}</span></td>
      <td style="color:var(--muted)">${ac.runway || "–"}</td>
    `;

    tbody.appendChild(tr);
  }
}

async function submitCTAF() {
  const input = document.getElementById("ctaf-input");
  const text = input.value.trim();

  if (!text) return;

  try {
    const resp = await fetch("/api/ctaf", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({text})
    });

    const data = await resp.json();

    if (data.error) {
      addAlert("info", `Parse error: ${data.error}`);
      return;
    }

    addAlert("info", `${data.callsign} → ${data.state.replace(/_/g, " ")} · Runway ${data.runway}`, data.callsign);

    updateMapDots(data.aircraft || []);
    updateAcTable(data.aircraft || []);

    for (const conflict of data.conflicts || []) {
      addAlert(conflict.type, conflict.message);
    }

  } catch (error) {
    addAlert("info", "Connection error: " + error.message);
  }

  input.value = "";
}

async function resetAll() {
  await fetch("/api/reset", {method:"POST"});

  if (window.speechSynthesis) {
    window.speechSynthesis.cancel();
  }

  speechQueue = Promise.resolve();
  recentAlertTimes.clear();

  for (const callsign of Object.keys(acDots)) {
    if (acDots[callsign].animFrame) {
      cancelAnimationFrame(acDots[callsign].animFrame);
    }

    acDots[callsign].g.remove();
  }

  acDots = {};
  document.getElementById("ac-tbody").innerHTML = "";
  addAlert("info", "All aircraft cleared. Monitoring CTAF.");
}

async function handleReplayData(data, label) {
  if (data.error) {
    await addAlert("info", `${label} error: ${data.error}`);
    return false;
  }

  if (data.load_note) {
    await addAlert("info", data.load_note);
  }

  if (data.done) {
    await addAlert("info", data.message || `${label} complete.`);
    return false;
  }

  const speechPromises = [];

  if (data.ctaf_calls && data.ctaf_calls.length > 0) {
    addAlert("info", data.message);

    for (const call of data.ctaf_calls) {
      speechPromises.push(addAlert("ctaf", "SIM CTAF: " + call));
    }
  } else {
    speechPromises.push(addAlert("ctaf", data.message));
  }

  updateMapDots(data.aircraft || []);
  updateAcTable(data.aircraft || []);

  for (const conflict of data.conflicts || []) {
    speechPromises.push(addAlert(conflict.type, conflict.message));
  }

  await Promise.all([
    Promise.all(speechPromises),
    sleep(MIN_STEP_MS)
  ]);

  return true;
}

async function stepSimulation() {
  const scenario = document.getElementById("scenario-select").value;

  try {
    const resp = await fetch("/api/sim/step", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        scenario,
        step: simStepIndex
      })
    });

    const data = await resp.json();
    const keepGoing = await handleReplayData(data, "Simulation");

    if (keepGoing) {
      simStepIndex += 1;
    } else {
      stopSimulation();
    }

    return keepGoing;

  } catch (error) {
    await addAlert("info", "Simulation connection error: " + error.message);
    stopSimulation();
    return false;
  }
}

async function runSimulationLoop() {
  while (simRunning) {
    const keepGoing = await stepSimulation();

    if (!keepGoing || !simRunning) {
      break;
    }
  }
}

async function toggleSimulation() {
  if (simRunning) {
    stopSimulation();
    return;
  }

  stopAdsbReplay();
  await resetAll();

  simRunning = true;
  simStepIndex = 0;

  const btn = document.getElementById("sim-btn");
  btn.textContent = "Stop Sim";
  btn.classList.add("running");

  addAlert("info", "Starting built-in timeline aircraft simulation.");
  runSimulationLoop();
}

function stopSimulation() {
  simRunning = false;

  const btn = document.getElementById("sim-btn");

  if (btn) {
    btn.textContent = "Start Sim";
    btn.classList.remove("running");
  }
}

async function stepAdsbReplay() {
  try {
    const resp = await fetch("/api/adsb/step", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        step: adsbStepIndex
      })
    });

    const data = await resp.json();
    const keepGoing = await handleReplayData(data, "ADS-B replay");

    if (keepGoing) {
      adsbStepIndex += 1;
    } else {
      stopAdsbReplay();
    }

    return keepGoing;

  } catch (error) {
    await addAlert("info", "ADS-B replay connection error: " + error.message);
    stopAdsbReplay();
    return false;
  }
}

async function runAdsbReplayLoop() {
  while (adsbReplayRunning) {
    const keepGoing = await stepAdsbReplay();

    if (!keepGoing || !adsbReplayRunning) {
      break;
    }
  }
}

async function toggleAdsbReplay() {
  if (adsbReplayRunning) {
    stopAdsbReplay();
    return;
  }

  stopSimulation();
  await resetAll();

  adsbReplayRunning = true;
  adsbStepIndex = 0;

  const btn = document.getElementById("adsb-btn");
  btn.textContent = "Stop ADS-B Replay";
  btn.classList.add("running");

  addAlert("info", "Starting ADS-B historical replay.");
  runAdsbReplayLoop();
}

function stopAdsbReplay() {
  adsbReplayRunning = false;

  const btn = document.getElementById("adsb-btn");

  if (btn) {
    btn.textContent = "Start ADS-B Replay";
    btn.classList.remove("running");
  }
}

document.getElementById("scenario-select").addEventListener("change", () => {
  stopSimulation();
  simStepIndex = 0;
});

let recognition = null;
let isListening = false;

function toggleMic() {
  if (!window.SpeechRecognition && !window.webkitSpeechRecognition) {
    addAlert("info", "Speech recognition not supported in this browser.");
    return;
  }

  if (isListening) {
    recognition.stop();
    return;
  }

  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  recognition = new SR();
  recognition.lang = "en-US";
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;

  recognition.onstart = () => {
    isListening = true;
    document.getElementById("mic-btn").textContent = "⏹";
  };

  recognition.onresult = event => {
    const transcript = event.results[0][0].transcript;
    document.getElementById("ctaf-input").value = transcript;
    submitCTAF();
  };

  recognition.onerror = event => {
    addAlert("info", "Speech error: " + event.error);
  };

  recognition.onend = () => {
    isListening = false;
    document.getElementById("mic-btn").textContent = "🎙";
  };

  recognition.start();
}

document.getElementById("ctaf-input").addEventListener("keydown", event => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    submitCTAF();
  }
});

(async () => {
  loadVoices();

  const resp = await fetch("/api/aircraft");
  const data = await resp.json();

  updateMapDots(data.aircraft || []);
  updateAcTable(data.aircraft || []);
})();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(debug=True, port=5050)
