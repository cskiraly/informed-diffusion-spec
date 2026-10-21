#!/usr/bin/env python3
"""Read a Quint ITF trace of the diffusion model and say what happened.

    python3 -I tools/itf.py TRACE.itf.json [--steps] [--state N]

Decodes ITF values (bigint, set, map, tuple), names the property the last state violates, and with
--steps prints one line per step: the action taken (with `quint run --mbt`) and what changed.
"""
import json
import sys


def dec(v):
    if isinstance(v, dict):
        if "#bigint" in v:
            return int(v["#bigint"])
        if "#set" in v:
            return frozenset(dec(x) for x in v["#set"])
        if "#map" in v:
            return {dec(k): dec(x) for k, x in v["#map"]}
        if "#tup" in v:
            return tuple(dec(x) for x in v["#tup"])
        return {k: dec(x) for k, x in v.items()}
    if isinstance(v, list):
        return [dec(x) for x in v]
    return v


def load(path):
    t = json.load(open(path))
    # the model's one variable, whatever the instance prefixes it with (t3::diffusion::s)
    return [{k.split("::")[-1]: dec(v) for k, v in st.items() if not k.startswith("#") and not k.startswith("mbt::")}
            for st in t["states"]]


def entry(e):
    parts = []
    if e["isHave"]:
        parts.append("HAVE{%s}" % ",".join(map(str, sorted(e["have"]))))
    if e["chunk"] != -1:
        parts.append(("ANS" if e["sol"] else "CHUNK") + str(e["chunk"]))
    if e["ihave"]:
        parts.append("IHAVE{%s}" % ",".join(map(str, sorted(e["ihave"]))))
    if e["iwant"]:
        parts.append("IWANT{%s}" % ",".join(map(str, sorted(e["iwant"]))))
    return "+".join(parts) or "-"


def violations(s, W=None):
    out = []
    if s["penalties"]:
        out.append(f"noPenalty: {sorted(s['penalties'])}")
    if s["badAsk"]:
        out.append(f"noStaleAsk: {sorted(s['badAsk'])}")
    if s["badHave"]:
        out.append(f"p4: {sorted(s['badHave'])}")
    for n, nd in s["nodes"].items():
        if nd["inFlight"] != len(nd["slotHeld"]) + len(nd["sent"]):
            out.append(f"windowConserved: node {n} inFlight {nd['inFlight']} held {sorted(nd['slotHeld'])} sent {sorted(nd['sent'])}")
        if W is not None and nd["inFlight"] > W:
            out.append(f"window > W at node {n}")
        if nd["waiters"] and (W is None or nd["inFlight"] < W) and nd["waiters"][0] not in nd["runnable"]:
            out.append(f"noLostWakeup?: node {n} waiters {nd['waiters']} inFlight {nd['inFlight']} runnable {sorted(nd['runnable'])}")
    return out


def summary(s):
    lines = []
    for n, nd in sorted(s["nodes"].items()):
        q = {p: [entry(e) for e in nd["qUrg"][p]] + ["|"] + [entry(e) for e in nd["qNorm"][p]]
             for p in nd["qNorm"] if nd["qUrg"][p] or nd["qNorm"][p]}
        lines.append(f"  node {n}: stage {nd['stage']} recv {sorted(nd['recv'])} mine {sorted(nd['mine'])} "
                     f"stored {sorted(nd['stored'])} stopPull {nd['stopPull']} inFlight {nd['inFlight']} "
                     f"waiters {nd['waiters']} held {sorted(nd['slotHeld'])} sent {sorted(nd['sent'])} "
                     f"runnable {sorted(nd['runnable'])} asking {sorted(nd['asking'])} "
                     f"promises {sorted(nd['promises'])} parked {sorted(nd['parked'])} queues {q}")
    for (a, b), l in sorted(s["links"].items()):
        if l:
            lines.append(f"  link {a}->{b}: {[entry(e) for e in l]}")
    return "\n".join(lines)


def main(argv):
    path = argv[0]
    states = load(path)
    raw = json.load(open(path))["states"]
    W = None
    if "--W" in argv:
        W = int(argv[argv.index("--W") + 1])
    if "--steps" in argv:
        for k, st in enumerate(states):
            meta = {kk: dec(vv) for kk, vv in raw[k].items() if kk.startswith("mbt::")}
            act = meta.get("mbt::actionTaken", "")
            picks = {p: v["value"] for p, v in (meta.get("mbt::nondetPicks") or {}).items()
                     if isinstance(v, dict) and v.get("tag") == "Some"}
            what = ""
            if k > 0:
                a, b = states[k - 1]["s"], st["s"]
                if act == "deliverAct":
                    src, dst = picks["lk"]
                    what = f"{src}->{dst} delivers {entry(a['links'][(src, dst)][0])}"
                elif act == "writerAct":
                    n, p = picks["w"]
                    if len(b["links"][(n, p)]) > len(a["links"][(n, p)]):
                        what = f"{n} writes {entry(b['links'][(n, p)][-1])} to {p}"
                    else:
                        nb, na = b["nodes"][n], a["nodes"][n]
                        what = (f"{n}'s writer for {p}: no write (inFlight {na['inFlight']}->{nb['inFlight']}, "
                                f"waiters {na['waiters']}->{nb['waiters']}, held {sorted(nb['slotHeld'])})")
                picks = {p: v for p, v in picks.items() if p not in ("lk", "w")}
            print(f"[{k}] {act} {what} {picks if picks else ''}")
            if "--full" in argv:
                print(summary(st["s"]))
    k = int(argv[argv.index("--state") + 1]) if "--state" in argv else len(states) - 1
    s = states[k]["s"]
    print(f"state {k} of {len(states) - 1}")
    print(summary(s))
    print("violations:", violations(s, W) or "none")


if __name__ == "__main__":
    main(sys.argv[1:])
