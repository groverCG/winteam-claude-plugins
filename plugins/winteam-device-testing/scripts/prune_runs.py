"""Delete capture runs: screenshots and page sources hold test-account data and must not go stale.

Only folders named like a run (yyyymmdd-hhmmss) directly inside a folder named "runs" are touched.
Prints a count, never paths or contents, and always exits 0 so a session-start hook can't break a session.
"""

import argparse
import json
import os
import re
import shutil
import sys
import time

RUN_NAME = re.compile(r"^\d{8}-\d{6}$")


def retention_days(data_dir, default=3):
    try:
        with open(os.path.join(data_dir, "app.json")) as handle:
            return float(json.load(handle).get("retentionDays", default))
    except (OSError, ValueError, TypeError):
        return float(default)


def prune(runs_dir, older_than_days=None):
    """Delete run folders older than the given age, or all of them when it is None. Returns the count."""
    runs_dir = os.path.realpath(runs_dir)
    if os.path.basename(runs_dir) != "runs":
        raise ValueError("refusing to prune a folder not named 'runs': {}".format(runs_dir))
    if not os.path.isdir(runs_dir):
        return 0
    cutoff = None if older_than_days is None else time.time() - older_than_days * 86400
    deleted = 0
    for name in os.listdir(runs_dir):
        path = os.path.join(runs_dir, name)
        if not RUN_NAME.match(name) or not os.path.isdir(path) or os.path.islink(path):
            continue
        if cutoff is not None and os.path.getmtime(path) >= cutoff:
            continue
        shutil.rmtree(path, ignore_errors=True)
        deleted += 1
    return deleted


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", required=True, help="the plugin's runs folder")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--all", action="store_true", help="delete every run")
    group.add_argument("--older-than", type=float, help="delete runs older than this many days")
    parser.add_argument("--data", help="folder with app.json, for retentionDays when no age is given")
    parser.add_argument("--quiet", action="store_true", help="print nothing when nothing was deleted")
    args = parser.parse_args()
    if args.all:
        age = None
    elif args.older_than is not None:
        age = args.older_than
    else:
        age = retention_days(args.data) if args.data else 3.0
    try:
        count = prune(args.runs, age)
    except (OSError, ValueError) as error:
        print("prune skipped: {}".format(error), file=sys.stderr)
        return
    if count or not args.quiet:
        print("winteam-device-testing: deleted {} capture run(s)".format(count))


if __name__ == "__main__":
    main()
