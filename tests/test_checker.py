"""Contract checks for malformed inputs, boundaries and the actual CLI."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from language_estimate_integrity_checker import validate


def example():
    return {"areas": [{"area_id": "demo", "total": 10, "english_only": 4,
                       "home_language_total": 6, "limited_english_total": 2,
                       "groups": [{"id": "a", "speakers": 6, "limited_english": 2}]}]}


class IntegrityTests(unittest.TestCase):
    def codes(self, data, format="normalized", selected=None):
        return {e["code"] for e in validate(data, format, selected)["errors"]}

    def test_rejects_bad_count_values(self):
        for value, code in [(-1, "negative"), (None, "integer"), (True, "integer"),
                            ("6", "integer"), (1.5, "integer"),
                            (float("nan"), "nonfinite"), (float("inf"), "nonfinite")]:
            with self.subTest(value=value):
                data = example()
                data["areas"][0]["groups"][0]["speakers"] = value
                self.assertIn(code, self.codes(data))

    def test_zero_population_and_unknown_or_large_margin_are_valid(self):
        for moe in (None, 50):
            data = {"areas": [{"area_id": "empty", "total": 0, "english_only": 0,
                               "home_language_total": 0, "limited_english_total": 0,
                               "groups": [{"id": "a", "speakers": 0, "limited_english": 0, "moe": moe}]}]}
            self.assertTrue(validate(data, "normalized")["valid"])

    def test_duplicate_groups_cannot_hide_behind_correct_sums(self):
        data = example()
        data["areas"][0]["groups"] = [{"id": "Spanish", "speakers": 3, "limited_english": 1},
                                     {"id": "spanish", "speakers": 3, "limited_english": 1}]
        self.assertEqual(self.codes(data), {"duplicate_group"})

    def test_duplicate_areas_rejected(self):
        data = example()
        data["areas"].append(copy.deepcopy(data["areas"][0]))
        self.assertIn("duplicate_area", self.codes(data))

    def test_partitions_and_subsets(self):
        cases = [("english_only", 11, "subset"), ("home_language_total", 7, "partition"),
                 ("limited_english_total", 3, "limited_sum"),
                 ("limited_english_total", 7, "subset")]
        for field, value, code in cases:
            with self.subTest(field=field, value=value):
                data = example()
                data["areas"][0][field] = value
                self.assertIn(code, self.codes(data))
        data = example()
        data["areas"][0]["groups"][0]["speakers"] = 5
        self.assertIn("speaker_sum", self.codes(data))
        data = example()
        data["areas"][0]["groups"][0]["limited_english"] = 7
        self.assertIn("subset", self.codes(data))

    def test_structural_failures(self):
        for data in (None, [], {}, {"areas": []}, {"areas": [None]}):
            with self.subTest(data=data):
                self.assertFalse(validate(data, "normalized")["valid"])
        for groups in (None, [], [None], [{"id": [], "speakers": 6, "limited_english": 2}]):
            data = example()
            data["areas"][0]["groups"] = groups
            self.assertFalse(validate(data, "normalized")["valid"])
        self.assertIn("shape", self.codes({"10001": [0] * 37}, "compact"))
        self.assertIn("missing_area", self.codes(example(), selected="absent"))

    def test_compact_missing_margin_is_allowed_but_negative_count_is_not(self):
        row = [0, 0] + [0, -1, 0] * 12
        self.assertTrue(validate({"zero": row})["valid"])
        row[2] = -1
        self.assertIn("negative", self.codes({"zero": row}, "compact"))

    def test_only_integer_minus_one_is_a_compact_missing_margin(self):
        for value, code in [(-2, "negative"), (-1.0, "integer")]:
            row = [0, 0] + [0, -1, 0] * 12
            row[3] = value
            self.assertIn(code, self.codes({"zero": row}, "compact"))


class CommandLineTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(BASE / "language_estimate_integrity_checker.py"), *map(str, args)],
                              text=True, capture_output=True, cwd=BASE, timeout=10)

    def test_real_production_fixture(self):
        result = self.run_cli("fixtures/zip-10001.json", "--area", "10001", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["valid"])
        self.assertEqual(report["areas_checked"], 1)

    def test_deliberately_invalid_fixture(self):
        result = self.run_cli("fixtures/invalid-normalized.json", "--format", "normalized", "--json")
        self.assertEqual(result.returncode, 1, result.stderr)
        codes = {error["code"] for error in json.loads(result.stdout)["errors"]}
        self.assertTrue({"duplicate_group", "speaker_sum", "limited_sum", "subset"}.issubset(codes))

    def test_input_failures_are_structured_and_never_tracebacks(self):
        scratch = BASE / ".verification"
        scratch.mkdir(exist_ok=True)
        payloads = ['{"same": [], "same": []}', '{"10001": [NaN]}', '{broken',
                    '{"10001": [Infinity]}']
        with tempfile.TemporaryDirectory(dir=scratch) as temporary:
            for index, payload in enumerate(payloads):
                path = Path(temporary) / f"bad-{index}.json"
                path.write_text(payload, encoding="utf-8")
                result = self.run_cli(path, "--json")
                self.assertEqual(result.returncode, 2)
                self.assertEqual(json.loads(result.stdout)["errors"][0]["code"], "input")
                self.assertNotIn("Traceback", result.stderr)
            missing = self.run_cli(Path(temporary) / "absent.json", "--json")
            self.assertEqual(missing.returncode, 2)
            self.assertEqual(json.loads(missing.stdout)["errors"][0]["code"], "input")

    def test_overflowing_json_exponent_cannot_pass_as_finite(self):
        scratch = BASE / ".verification"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temporary:
            path = Path(temporary) / "overflow.json"
            payload = json.dumps(example()).replace('"speakers": 6', '"speakers": 1e999')
            path.write_text(payload, encoding="utf-8")
            result = self.run_cli(path, "--format", "normalized", "--json")
            self.assertEqual(result.returncode, 1)
            self.assertIn("nonfinite", {e["code"] for e in json.loads(result.stdout)["errors"]})

    def test_help_is_available_without_input(self):
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--format", result.stdout)
        self.assertIn("--area", result.stdout)


if __name__ == "__main__":
    unittest.main()
