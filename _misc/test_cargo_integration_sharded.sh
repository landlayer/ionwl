#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later

# Run the integration test suite sharded across processes.
#
# Within a single process the suite is strictly serial: the embedded Python
# interpreter and the compositor state are process-global singletons, so a
# global mutex forces `--test-threads=1`. Parallelism therefore comes from
# running several test-binary processes at once, each over a disjoint subset
# of the tests. Each process gets its own interpreter and compositor, so the
# subsets are fully independent.
#
# Usage: test_cargo_integration_sharded.sh [shard-count]

set -eu

shards="${1:-1}"

# Build the test binary in one invocation (concurrent `cargo test` runs would
# contend on the build lock) and read its path from the JSON artifact stream,
# which reports the executable even on a fully warm build.
bin=$(
	cargo test --test integration --features test_support --no-run \
		--message-format=json |
	python3 -c 'import sys, json
for line in sys.stdin:
    try:
        msg = json.loads(line)
    except ValueError:
        continue
    if msg.get("target", {}).get("name") == "integration" and msg.get("executable"):
        print(msg["executable"])'
)

if [ -z "$bin" ]; then
	echo "error: could not locate integration test binary" >&2
	exit 1
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# Partition the test list round-robin so each shard carries a balanced mix of
# fast and slow tests rather than a contiguous (and lopsided) module range.
"$bin" --list --format terse |
	sed 's/: test$//' |
	awk -v n="$shards" '{ print > (dir "/shard_" (NR % n)) }' dir="$work"

# Launch one single-threaded process per shard, tracking each PID with its log
# so a failing shard can be replayed in full after the run.
pids=""
i=0
for shard in "$work"/shard_*; do
	[ -e "$shard" ] || continue
	"$bin" --exact $(cat "$shard") --test-threads=1 >"$work/out_$i" 2>&1 &
	pids="$pids $!:$work/out_$i"
	i=$((i + 1))
done

status=0
passed=0
for entry in $pids; do
	pid=${entry%%:*}
	log=${entry#*:}
	if ! wait "$pid"; then
		status=1
		cat "$log"
	fi
	n=$(sed -n 's/^test result: ok\. \([0-9]*\) passed.*/\1/p' "$log")
	passed=$((passed + ${n:-0}))
done

echo "integration: ${passed} tests passed across ${i} shards"
exit "$status"
