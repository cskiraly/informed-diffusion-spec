#!/bin/bash
# The record's run of the twin: check.sh with --record. Every cell of the toy under both documents, the three
# hand traces and the 22 directed sets, each traced and replayed under the quick check's contract; the tools' own
# controls; the seeds' retrace; and the manifest of the record's 55 traces by their two hashes. Hours on a
# server, where the quick check takes minutes.
#
#   bash formal/twin/record.sh [--toy DIR] [--out DIR] [-j N] [--steps a,b,...]
#
# The options, the steps and what each must show are in check.sh's head. It prints "check.sh: PASS (the record's
# run)" and exits 0 only if every step ran and showed what it must.
exec bash "$(cd "$(dirname "$0")" && pwd)/check.sh" --record "$@"
