# Language estimate integrity checker

An offline Python CLI that catches broken counts and duplicate groups in saved home-language estimates. Use it before displaying an export, loading a refreshed data file, or passing a normalized table to another script. It uses only the Python standard library and writes nothing during ordinary checks.

No license grant is included for the source code.

## Try the real example

Python 3.10 or newer is sufficient. From this directory:

```sh
python language_estimate_integrity_checker.py --help
python language_estimate_integrity_checker.py fixtures/zip-10001.json --area 10001
```

Expected output:

```text
VALID: 1 area(s), 0 issue(s).
```

The fixture is the exact numeric record for ZCTA 10001 retrieved from the public export behind the [PewTranslate Census language lookup](https://pewtranslate.com/en/guides/languages-spoken-by-zip-code) on October 31, 2026. It contains 29,450 people aged five and older, 19,947 English-only speakers, and 12 other home-language groups. The group speaker estimates sum to 9,503; their limited-English counts sum to 2,414. These are arithmetic relationships in the downloaded record, not an independent Census verification. The survey period is 2020–2024. See [fixture provenance](fixtures/provenance.json) for the retrieval time, source URL, source hash, selection and fixture hash.

## See a useful failure

```sh
python language_estimate_integrity_checker.py fixtures/invalid-normalized.json --format normalized --json
```

This deliberately synthetic file has a duplicate group, a subset larger than its group, a speaker sum that differs from the stated home-language total, and a limited-English sum that differs from its total. The command returns exit code 1 and structured errors identifying each field. It contains no actual geography or observed population values.

Exit codes: **0** means the requested integrity checks found no issues; **1** means a shape, count or consistency check failed; **2** means the file could not be read or parsed, or CLI usage was invalid. Invalid CLI arguments use argparse's stderr message; `--json` makes file-reading and validation results machine readable.

## Check your saved export

The CLI never fetches a URL. Save a public export locally, then run:

```sh
python language_estimate_integrity_checker.py saved-export.json --json
python language_estimate_integrity_checker.py saved-export.json --area 10001 --json
```

The default `compact` format accepts a nonempty object mapping area IDs to 38-value rows:

```text
{ "AREA_ID": [total_5_plus, english_only,
              spanish_speakers, spanish_moe, spanish_limited_english,
              ... eleven more group triples ...] }
```

The fixed group order is Spanish, French/Haitian/Cajun, German/other West Germanic, Russian/Polish/other Slavic, other Indo-European, Korean, Chinese, Vietnamese, Tagalog, other Asian/Pacific Island, Arabic, other/unspecified. It follows the site's C16001 export adapter. Compact ZIP and state objects use this layout. County arrays have a different wrapper and are not accepted directly; convert one deliberately to normalized JSON instead. Arbitrary compact layouts are not guessed.

`--area` checks counts for one exact ID. Duplicate JSON keys, area identifiers and compact row lengths are still checked throughout the input, so it is not a way to ignore a malformed file. Default operation validates every area. Duplicate keys are rejected before JSON parsing can silently overwrite a record.

## Normalize another table

Use `--format normalized` for this explicit JSON schema:

```json
{
  "areas": [{
    "area_id": "example-only",
    "total": 10,
    "english_only": 4,
    "home_language_total": 6,
    "limited_english_total": 2,
    "groups": [{"id": "group-a", "speakers": 6, "limited_english": 2, "moe": null}]
  }]
}
```

The example is synthetic. Supply a complete, mutually exclusive breakdown of non-English home-language groups for one geography, survey period and universe. `total`, `english_only`, `home_language_total` and `limited_english_total` are required. `groups` must be nonempty; each group requires `id`, `speakers` and `limited_english`. Group and area IDs are nonempty strings without surrounding whitespace; duplicates are checked without case sensitivity. `moe` is optional and may be null.

Counts must be nonnegative JSON integers: no numeric strings, booleans, fractional values, NaN or infinity. Published negative annotation codes in count fields must be resolved as missing upstream; they are not turned into zero. In the compact adapter only, a margin of error of `-1` is the export's unavailable-margin sentinel. Other negative margins are rejected. A margin may legitimately exceed its estimate, so that is not rejected.

Checks cover:

- English-only plus non-English home-language total equals the age-five-and-over total.
- Group speaker estimates sum to the home-language total.
- Each limited-English count is at most its group's speaker count.
- Group limited-English counts sum to the provided limited-English total, which is at most the home-language total.
- Input shape, finite integer values and duplicate identifiers/JSON keys.

The compact adapter derives home-language total as total minus English-only, and derives the limited-English total by summing group subsets. Its limited-English sum therefore has no separate independent total to cross-check. Normalized JSON can supply both totals explicitly. Sums use exact integer arithmetic, without a rounding tolerance.

## What a valid result does not mean

This checker does not retrieve or recompute the Census source, authenticate a file, test sampling accuracy, combine margins of error, calculate confidence intervals, infer significance, compare rankings, match geographic boundaries, or infer translation demand. It cannot detect a consistently wrong or stale export, mislabeled language groups, overlapping groups that happen to balance, or mixed geographies/periods with matching totals. Preserve provenance and review those meanings separately.

Home language differs from preferred language and translation need. ZCTAs differ from postal delivery areas, and the universe is people aged five and older. The data are ACS five-year period estimates. The [US Census Bureau's C16001 metadata](https://api.census.gov/data/2024/acs/acs5/groups/C16001.html) is the primary reference for the upstream table; the [Census summary-file guide](https://www.census.gov/programs-surveys/acs/data/summary-file.html) describes its source layout. This checker does not assert Census endorsement or translation-product availability.

## Development verification

```sh
python -m unittest discover -s tests -v
```

Tests exercise invalid values, duplicates, broken partitions/subsets, zero populations, unavailable or larger margins, malformed files, missing files, and the real CLI with both fixtures. Temporary test files stay under `.verification/` and are removed after the test. `.verification/` is ignored by Git and is not included in the repository.

Unlike the existing two-record Census notebook, this tool validates arbitrary saved exports without executing notebook cells or comparing saved notebook output. It complements source provenance work; it does not replace it.
