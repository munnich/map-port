"""Greedy byte alignment of ACB->ACR pairs: find where ACR inserts/deletes bytes."""
import sys, os, pickle, collections
sys.path.insert(0, os.path.expanduser("~/Coding/Python/anvilforge-py-acrport/src"))
from analyze import ACR
a, r, _ = pickle.load(open("cross.pkl", "rb"))
want = sys.argv[1]
K = 12  # bytes that must match after a candidate skip


def align(x, y):
    i = j = 0; events = []
    while i < len(x) and j < len(y):
        if x[i] == y[j]: i += 1; j += 1; continue
        found = None
        for d in range(1, 9):
            if y[j + d:j + d + K] == x[i:i + K] and len(x) - i >= K: found = ("ins", d); break
            if x[i + d:i + d + K] == y[j:j + K] and len(y) - j >= K: found = ("del", d); break
        if found is None:
            events.append(("sub", i, x[max(0, i - 8):i].hex(), x[i:i + 1].hex(), y[j:j + 1].hex())); i += 1; j += 1; continue
        kind, d = found
        if kind == "ins": events.append(("ins", i, x[max(0, i - 8):i].hex(), "", y[j:j + d].hex())); j += d
        else: events.append(("del", i, x[max(0, i - 8):i].hex(), x[i:i + d].hex(), "")); i += d
    return events


ctx = collections.Counter(); per_obj = collections.Counter(); n = 0
for uid in sorted(a.keys() & r.keys()):
    if ACR.name_of(r[uid][0]) != want or len(a[uid][2]) == len(r[uid][2]): continue
    ev = [e for e in align(a[uid][2], r[uid][2]) if e[0] != "sub"]
    per_obj[len(ev)] += 1; n += 1
    for kind, off, before, old, new in ev:
        ctx[(kind, before[-8:], old, new)] += 1
print(f"{want}: {n} length-changed pairs; indel events per object: {sorted(per_obj.items())}")
for (kind, before, old, new), c in ctx.most_common(25):
    print(f"  {c:4d} {kind} after ..{before} old={old or '-'} new={new or '-'}")
