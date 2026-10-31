"""Check count integrity in compact or normalized home-language JSON exports.

Offline and standard-library only. This checks data shape and arithmetic, not
source authenticity, statistical accuracy, uncertainty, or translation demand.
"""

import argparse
import json
import math
from pathlib import Path
import sys


GROUPS = (
    "spanish", "french", "german", "slavic", "otherIndoEuropean", "korean",
    "chinese", "vietnamese", "tagalog", "otherAsian", "arabic", "other",
)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError(f"Non-finite JSON number: {value}")


def validate(data, input_format="compact", selected_area=None):
    """Return a report without modifying the input or accessing the network."""
    errors = []
    checked = 0

    def problem(area, field, code, message):
        errors.append({"area": area, "field": field, "code": code, "message": message})

    def count(value, area, field, optional=False):
        if optional and value is None:
            return None
        if isinstance(value, float) and not math.isfinite(value):
            problem(area, field, "nonfinite", "Expected a finite count.")
        elif isinstance(value, bool) or not isinstance(value, int):
            problem(area, field, "integer", "Expected an integer; strings, booleans and fractions are invalid.")
        elif value < 0:
            problem(area, field, "negative", "Expected a nonnegative count.")
        else:
            return value
        return None

    def identifier(value, area, field):
        if not isinstance(value, str) or not value.strip():
            problem(area, field, "identifier", "Expected a nonempty string identifier.")
            return None
        if value != value.strip():
            problem(area, field, "identifier", "Identifier must not contain surrounding whitespace.")
        return value.strip().casefold()

    if input_format == "compact":
        if not isinstance(data, dict) or not data:
            problem(None, "$", "shape", "Compact input must be a nonempty object mapping area IDs to 38-number rows.")
            records = []
        else:
            records = []
            for area, row in data.items():
                if not isinstance(row, list) or len(row) != 38:
                    problem(str(area), "$", "shape", "Compact row must contain exactly 38 values.")
                    records.append({"area_id": area, "_malformed": True})
                    continue
                groups = [
                    {"id": name, "speakers": row[2 + 3 * i],
                     "moe": None if isinstance(row[3 + 3 * i], int) and row[3 + 3 * i] == -1 else row[3 + 3 * i],
                     "limited_english": row[4 + 3 * i]}
                    for i, name in enumerate(GROUPS)
                ]
                records.append({"area_id": area, "total": row[0], "english_only": row[1],
                                "groups": groups})
    elif input_format == "normalized":
        if not isinstance(data, dict) or not isinstance(data.get("areas"), list) or not data["areas"]:
            problem(None, "$", "shape", "Normalized input must contain a nonempty areas list.")
            records = []
        else:
            records = data["areas"]
    else:
        problem(None, "$", "format", "Unknown input format.")
        records = []

    seen_areas = set()
    found = False
    for position, record in enumerate(records):
        if not isinstance(record, dict):
            problem(None, f"areas[{position}]", "shape", "Area record must be an object.")
            continue
        raw_area = record.get("area_id")
        area = raw_area if isinstance(raw_area, str) else None
        area_key = identifier(raw_area, area, "area_id")
        if area_key in seen_areas and area_key is not None:
            problem(area, "area_id", "duplicate_area", "Area identifier occurs more than once.")
        seen_areas.add(area_key)
        if selected_area is not None and raw_area != selected_area:
            continue
        found = True
        checked += 1
        if record.get("_malformed") and input_format == "compact":
            continue
        total = count(record.get("total"), area, "total")
        english = count(record.get("english_only"), area, "english_only")
        compact = input_format == "compact"
        home = (total - english if total is not None and english is not None else None) if compact else count(record.get("home_language_total"), area, "home_language_total")
        limited = None if compact else count(record.get("limited_english_total"), area, "limited_english_total")
        groups = record.get("groups")
        if not isinstance(groups, list) or not groups:
            problem(area, "groups", "shape", "Expected a nonempty list of mutually exclusive home-language groups.")
            continue
        speaker_counts, limited_counts, seen_groups = [], [], set()
        for index, group in enumerate(groups):
            field = f"groups[{index}]"
            if not isinstance(group, dict):
                problem(area, field, "shape", "Group must be an object.")
                continue
            key = identifier(group.get("id"), area, field + ".id")
            if key in seen_groups and key is not None:
                problem(area, field + ".id", "duplicate_group", "Group identifier occurs more than once (case insensitive).")
            seen_groups.add(key)
            speakers = count(group.get("speakers"), area, field + ".speakers")
            subset = count(group.get("limited_english"), area, field + ".limited_english")
            count(group.get("moe"), area, field + ".moe", optional=True)
            if speakers is not None:
                speaker_counts.append(speakers)
            if subset is not None:
                limited_counts.append(subset)
            if speakers is not None and subset is not None and subset > speakers:
                problem(area, field + ".limited_english", "subset", "Limited-English count exceeds this group's speaker count.")
        if total is not None and english is not None and english > total:
            problem(area, "english_only", "subset", "English-only count exceeds the age-five-and-over total.")
        if not compact and total is not None and english is not None and home is not None and english + home != total:
            problem(area, "home_language_total", "partition", "English-only plus home-language total does not equal total.")
        if home is not None and len(speaker_counts) == len(groups) and sum(speaker_counts) != home:
            problem(area, "groups", "speaker_sum", f"Group speakers sum to {sum(speaker_counts)}; home-language total is {home}.")
        if compact and len(limited_counts) == len(groups):
            limited = sum(limited_counts)
        elif limited is not None and len(limited_counts) == len(groups) and sum(limited_counts) != limited:
            problem(area, "limited_english_total", "limited_sum", f"Group limited-English counts sum to {sum(limited_counts)}; total is {limited}.")
        if home is not None and limited is not None and limited > home:
            problem(area, "limited_english_total", "subset", "Limited-English total exceeds the home-language total.")
    if selected_area is not None and not found:
        problem(selected_area, "area_id", "missing_area", "Requested area is absent.")
    return {"valid": not errors, "format": input_format, "areas_checked": checked,
            "error_count": len(errors), "errors": errors}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Local UTF-8 JSON file; no URLs or network requests.")
    parser.add_argument("--format", choices=("compact", "normalized"), default="compact",
                        help="compact: 38-value export rows (default); normalized: explicit areas/groups.")
    parser.add_argument("--area", help="Check counts for one exact area ID. IDs, duplicate keys and row shapes remain checked throughout the file.")
    parser.add_argument("--json", action="store_true", help="Print a machine-readable report.")
    args = parser.parse_args(argv)
    try:
        data = json.loads(args.input.read_text(encoding="utf-8-sig"),
                          object_pairs_hook=unique_object, parse_constant=reject_constant)
        report = validate(data, args.format, args.area)
        exit_code = 0 if report["valid"] else 1
    except (OSError, UnicodeError, ValueError, RecursionError) as error:
        report = {"valid": False, "format": args.format, "areas_checked": 0,
                  "error_count": 1, "errors": [{"area": None, "field": "$", "code": "input",
                                                "message": str(error)}]}
        exit_code = 2
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False))
    else:
        label = "VALID" if report["valid"] else "INVALID"
        print(f"{label}: {report['areas_checked']} area(s), {report['error_count']} issue(s).")
        for error in report["errors"]:
            print(f"  {error['area'] or '$'} / {error['field']}: {error['message']}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
