# Control: a GRAFT for a held relation unanswered

`protocol-v2.md` §4.1's functions as they stood before 2026-11-09, kept for `graft_check.py --doc
... --diverged`: a GRAFT for a relation its receiver already holds goes unanswered, so ends that
disagree stay apart. The check must fail on it.

```python
def on_join(p, j: Join):
    T = type_of(j.object_type)
    if j.colours != T.params.M: return                 # no v2 for T on this link; the stock path remains
    join_recv[p][T] = j
    if T not in join_sent[p]: send_join(p, our_join(T))

def send_join(p, j: Join):                             # every JOIN of ours, once per link and type: when the node opens
    join_sent[p][type_of(j.object_type)] = j           #   the link, a sampling link's included, or in answer to p's;
    send_relation(p, j)

def maintain_relations(T):                             # at the heartbeat, per family we have duty in
    for fam in families_with_duty(T):
        for c in range(T.params.M):
            ins = in_pushers(T, fam, c)
            if len(ins) < T.params.F_LO:               # the floor per colour                [D10]
                for q in candidates(T, fam, c, IN)[: T.params.F_LO - len(ins)]:
                    graft(q, T, fam, c, IN)            # "push me": counted once q says yes
            if len(ins) > T.params.F_HI:
                for q in ins[T.params.F_HI:]:
                    prune(q, T, fam, c, IN)            # "stop pushing me"
            outs = out_pushees(T, fam, c)
            target = T.params.D_OUT_FAST if uplink_class() == FAST else T.params.D_OUT    # [c17]
            for q in candidates(T, fam, c, OUT)[: max(0, target - len(outs))]:
                graft(q, T, fam, c, OUT)

def graft(q, T, fam, c, d):                            # our GRAFT: nothing is counted until q answers it
    (grafted_in if d == IN else grafted_out)[q][T][fam].add(c)
    send_relation(q, Graft(object_type=T.id, family=fam, colour=c, direction=d))

def prune(q, T, fam, c, d):                            # our PRUNE: the relation ends at our end at once
    (push_in if d == IN else push_out)[q][T][fam].discard(c)
    (grafted_in if d == IN else grafted_out)[q][T][fam].discard(c)
    send_relation(q, Prune(object_type=T.id, family=fam, colour=c, direction=d))

def on_graft(p, gr: Graft):                            # each direction answered: a GRAFT is yes, a PRUNE no
    T = type_of(gr.object_type); fam, c = gr.family, gr.colour
    if gr.direction in (OUT, BOTH) and c not in push_in[p][T][fam]:     # p will push us colour c
        asked = c in grafted_in[p][T][fam]             # the yes to our "push me", or a GRAFT that crossed it
        grafted_in[p][T][fam].discard(c)
        if len(in_pushers(T, fam, c)) < T.params.F_HI and wants_family(T, fam):
            push_in[p][T][fam].add(c)
            if not asked: send_relation(p, Graft(object_type=T.id, family=fam, colour=c, direction=IN))   # yes: "push me"
        else:
            send_relation(p, Prune(object_type=T.id, family=fam, colour=c, direction=IN))   # no: "stop pushing me"
    if gr.direction in (IN, BOTH) and c not in push_out[p][T][fam]:     # p asks us to push it colour c
        asked = c in grafted_out[p][T][fam]            # the yes to our "I will push you", or one that crossed it
        grafted_out[p][T][fam].discard(c)
        if join_sent[p][T].duty == FORWARD and len(out_pushees(T, fam, c)) < T.params.D_OUT_MAX:
            if not asked: send_relation(p, Graft(object_type=T.id, family=fam, colour=c, direction=OUT))  # yes: "I will push you"
            join_push(p, T, fam, c)                    # in the relation at our end: what we hold is announced
        else:
            send_relation(p, Prune(object_type=T.id, family=fam, colour=c, direction=OUT))

def join_push(p, T, fam, c):                           # p joins our push relation for colour c: what we hold of
    if c in push_out[p][T][fam]: return                #   it is announced (protocol.md §5.4's on_mesh_join);
    push_out[p][T][fam].add(c)                         #   a GRAFT that adds nothing runs nothing
    for g in list(chunks):
        if expired(g) or state[g] == INVALID or type_of_group(g) != T or T.family(g) != fam: continue
        announce(p, g, bitmap({i for i in chunks[g] if colour_of(g, i) == c}))

def on_prune(p, pr: Prune):                            # p's no, or p's end of the relation: ours ends too
    T = type_of(pr.object_type); fam, c = pr.family, pr.colour
    if pr.direction in (OUT, BOTH):                    # "I stop pushing you", "I will not push you"
        push_in[p][T][fam].discard(c); grafted_in[p][T][fam].discard(c)
    if pr.direction in (IN, BOTH):                     # "stop pushing me"
        push_out[p][T][fam].discard(c); grafted_out[p][T][fam].discard(c)

def send_relation(p, m):                               # a JOIN, GRAFT or PRUNE is never lost to a full queue: one
    if owed_relations[p] or not send(p, m, urgent=isinstance(m, Join)):   #   refused, and every later one, is
        owed_relations[p].append(m)                    #   owed in order; a JOIN keeps the urgent lane
        wake(p)

def queue_owed_relations(p):                           # the writer, before anything else (§4.11)
    while owed_relations[p] and has_room(p):
        m = owed_relations[p].pop(0)
        send(p, m, urgent=isinstance(m, Join))
```
