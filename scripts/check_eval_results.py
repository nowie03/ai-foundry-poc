"""Gate CI on a promptfoo eval result: fail if the pass rate is below a threshold.

Usage:
    python scripts/check_eval_results.py results/smoke.json --min-pass-rate 1.0
    python scripts/check_eval_results.py results/skills.json --min-pass-rate 0.8
"""
import argparse
import json
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_path", help="Path to a promptfoo -o/--output JSON file")
    parser.add_argument("--min-pass-rate", type=float, required=True, help="Minimum pass rate, e.g. 0.8")
    args = parser.parse_args()

    with open(args.results_path) as f:
        data = json.load(f)

    metrics = data["results"]["prompts"][0]["metrics"]
    passed = metrics["testPassCount"]
    failed = metrics["testFailCount"]
    errored = metrics["testErrorCount"]
    total = passed + failed + errored

    if total == 0:
        print(f"{args.results_path}: no tests ran", file=sys.stderr)
        sys.exit(1)

    pass_rate = passed / total
    print(
        f"{args.results_path}: {passed}/{total} passed "
        f"({pass_rate:.1%}, {failed} failed, {errored} errored) "
        f"— threshold {args.min_pass_rate:.1%}"
    )

    if pass_rate < args.min_pass_rate:
        print(f"FAIL: pass rate {pass_rate:.1%} is below the required {args.min_pass_rate:.1%}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
