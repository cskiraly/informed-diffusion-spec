# Control: an answered GRAFT not yet in the text

`protocol-v2.md` §4.1's functions as they stood before 2026-11-04, kept for `graft_check.py --doc`:
a GRAFT's sender recorded nothing, so the two ends of a relation can disagree at rest. The check must
fail on it.

```python
def on_join(p, j: Join):
    T = type_of(j.object_type)
    if j.colours != T.params.M: return                 # no v2 for T on this link; the stock path remains
    join_recv[p][T] = j
    if T not in join_sent[p]: send(p, our_join(T), urgent=True)

def maintain_relations(T):                             # at the heartbeat, per family we have duty in
    for fam in families_with_duty(T):
        for c in range(T.params.M):
            ins = in_pushers(T, fam, c)
            if len(ins) < T.params.F_LO:               # the floor per colour                [D10]
                for q in candidates(T, fam)[: T.params.F_LO - len(ins)]:
                    send(q, Graft(object_type=T.id, family=fam, colour=c, direction=IN), urgent=False)
            if len(ins) > T.params.F_HI:
                for q in ins[T.params.F_HI:]:
                    send(q, Prune(object_type=T.id, family=fam, colour=c, direction=IN), urgent=False)
                    push_in[q][T][fam].discard(c)
            outs = out_pushees(T, fam, c)
            target = T.params.D_OUT_FAST if uplink_class() == FAST else T.params.D_OUT    # [c17]
            for q in candidates(T, fam)[: max(0, target - len(outs))]:
                send(q, Graft(object_type=T.id, family=fam, colour=c, direction=OUT), urgent=False)

def on_graft(p, gr: Graft):                            # returns the PRUNEs to send back
    T = type_of(gr.object_type); fam, c = gr.family, gr.colour
    back = []
    if gr.direction in (OUT, BOTH):                    # p offers to push us colour c
        if len(in_pushers(T, fam, c)) < T.params.F_HI and wants_family(T, fam):
            push_in[p][T][fam].add(c)
        else:
            back.append(Prune(object_type=T.id, family=fam, colour=c, direction=IN))   # our view: "stop pushing me"
    if gr.direction in (IN, BOTH):                     # p asks us to push it colour c
        if join_sent[p][T].duty == FORWARD and len(out_pushees(T, fam, c)) < T.params.D_OUT_MAX:
            join_push(p, T, fam, c)
        else:
            back.append(Prune(object_type=T.id, family=fam, colour=c, direction=OUT))  # our view: "I will not push you"
    return back

def join_push(p, T, fam, c):                           # p joins our push relation for colour c: what we hold of
    if c in push_out[p][T][fam]: return                #   it is announced (protocol.md §5.4's on_mesh_join);
    push_out[p][T][fam].add(c)                         #   a GRAFT that adds nothing runs nothing
    for g in list(chunks):
        if expired(g) or state[g] == INVALID or type_of_group(g) != T or T.family(g) != fam: continue
        announce(p, g, bitmap({i for i in chunks[g] if colour_of(g, i) == c}))

def on_prune(p, pr: Prune):
    T = type_of(pr.object_type)
    if pr.direction in (OUT, BOTH): push_in[p][T][pr.family].discard(pr.colour)
    if pr.direction in (IN, BOTH): push_out[p][T][pr.family].discard(pr.colour)
```
