#!/usr/bin/env python3
"""Two controls of the kit, one for each of two causes of a mutant left untold by the directed sets. Each fails on
the kit without the fix it checks.

    python3 fixcontrols.py pick REPLAY CONTENT TRACE.jsonl.gz NAME      (CONTENT: the file with the tree's content line)
    python3 fixcontrols.py draw DIRECTED3V.jsonl.gz

pick: the replay's `--only fn=NAME` takes every record of TRACE that reached NAME, and every record that asks NAME on
its tape (a name a node has replaced is asked there, and is not in `reached`: the twin's line that asks the node
runs at exactly those records). The records are counted here by parsing each line; the replay must say that it
skipped the others, no more and no fewer, and end with 0. The trace must have records of the second kind, or the
control shows nothing. Without the fix the replay skips them all (`validate-own-level1-not-asked`).

draw: in directed3v's set, at a node of design A (`DESCRIPTOR_IN_CHUNK`), the scenario's blocks are the toy's: some
have the committed id and no descriptor member, as every block of the toy's own has under design A (toy/sim.py's
Block). Without the fix every block has the member, set to the chunk's own descriptor where the id matches, and the
bid's descriptor returned for the chunk's is the same value (`committed-bid-descriptor-under-a`).
The answers of installed_block on the tapes are counted by their form (slot, id, descriptor), a node.

Each prints one line and exits 0, or says what does not hold and exits 1.
"""
import json
import re
import subprocess
import sys


def records(path):
    """The lines of a trace that are records (they have a tape), parsed; and the nodes line's nodes."""
    z = subprocess.Popen(["zcat", "--", path], stdout=subprocess.PIPE)
    nodes, recs = None, []
    for line in z.stdout:
        d = json.loads(line)
        if isinstance(d, dict) and "nodes" in d and nodes is None:
            nodes = d["nodes"]
        if isinstance(d, dict) and "tape" in d:
            recs.append(d)
    if z.wait() != 0:
        raise SystemExit(f"fixcontrols: zcat failed on {path}")
    return nodes, recs


def pick(replay, spec, path, name):
    _, recs = records(path)
    reached = sum(1 for d in recs if name in d.get("reached", ()))
    asked = sum(1 for d in recs if name not in d.get("reached", ())
                and any(isinstance(e, list) and e and e[0] == name for e in d["tape"]))
    if not asked:
        print(f"fixcontrols pick: {path}: no record asks {name} on its tape outside its reached: the control shows nothing")
        return 1
    z = subprocess.Popen(["zcat", "--", path], stdout=subprocess.PIPE)
    r = subprocess.run([replay, "--only", f"fn={name}", "--content", spec], stdin=z.stdout, capture_output=True, text=True)
    z.stdout.close()
    if z.wait() != 0:
        raise SystemExit(f"fixcontrols: zcat failed on {path}")
    m = re.search(rf"^subset: --only fn={re.escape(name)}: (\d+) records skipped unread$", r.stdout, re.M)
    if not m:
        print(f"fixcontrols pick: {path}: the replay did not say how many records it skipped (rc {r.returncode})")
        return 1
    taken = len(recs) - int(m[1])
    ok = r.returncode == 0 and taken == reached + asked
    print(f"fixcontrols pick: {path.rsplit('/', 1)[-1]} --only fn={name}: {len(recs)} records; {reached} reached {name}, "
          f"{asked} more ask it on the tape; the replay took {taken} and ended with {r.returncode}"
          + ("" if ok else f"  <-- NOT the {reached + asked} it must take, or not 0"))
    return 0 if ok else 1


def draw(path):
    nodes, recs = records(path)
    if not nodes:
        print(f"fixcontrols draw: {path}: no nodes line")
        return 1
    design_a = {n for nd in nodes for n in nd["n"] if nd.get("consts", {}).get("DESCRIPTOR_IN_CHUNK") is True}
    design_b = {n for nd in nodes for n in nd["n"] if nd.get("consts", {}).get("DESCRIPTOR_IN_CHUNK") is False}
    forms = {}
    for d in recs:
        for e in d["tape"]:
            if isinstance(e, list) and e and e[0] == "installed_block" and isinstance(e[2], list) and len(e[2]) == 3:
                key = ("A" if d["n"] in design_a else "B" if d["n"] in design_b else "?",
                       "an id" if e[2][1] is not None else "no id",
                       "a descriptor" if e[2][2] is not None else "no descriptor")
                forms[key] = forms.get(key, 0) + 1
    toy = forms.get(("A", "an id", "no descriptor"), 0)
    ok = bool(design_a) and bool(design_b) and toy > 0 and not any(k[0] == "?" for k in forms)
    said = "; ".join(f"design {k[0]}, {k[1]}, {k[2]}: {v}" for k, v in sorted(forms.items()))
    print(f"fixcontrols draw: {path.rsplit('/', 1)[-1]}: the blocks answered, by form: {said}"
          + ("" if ok else "  <-- NOT with a design A block of an id and no descriptor (the toy's), or a node of no design"))
    return 0 if ok else 1


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 5 and a[0] == "pick":
        sys.exit(pick(*a[1:]))
    if len(a) == 2 and a[0] == "draw":
        sys.exit(draw(a[1]))
    sys.exit("usage: fixcontrols.py pick REPLAY SPEC TRACE NAME | fixcontrols.py draw DIRECTED3V")
