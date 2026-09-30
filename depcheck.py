"""depcheck.py <forge>: validate every entry's dependency table (count, ids resolve, flags)."""
import sys, os, io, pickle, collections
sys.path.insert(0, os.path.expanduser("~/Coding/Python/anvilforge-py-acrport/src"))
from anvilforge.forge import read_header
from anvilforge.fileset import iter_fileset_entries, read_entry_payload
acb = pickle.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "acb_idx.pkl"), "rb"))
path = sys.argv[1]
ents = []
with open(path, "rb") as f:
    for s in range(read_header(f, 25)):
        for e in list(iter_fileset_entries(f, s, True)):
            ents.append((e, read_entry_payload(f, e, True)))
ids = {e.id for e, _ in ents}
flags = collections.Counter(); bad = collections.Counter(); ex = collections.defaultdict(list); counts = []
for e, p in ents:
    if e.id == 16: continue
    n = int.from_bytes(p[:4], "little"); counts.append(n)
    if n > 100000: bad["huge count"] += 1; ex["huge count"].append(e.name); continue
    for i in range(n):
        dep = int.from_bytes(p[4 + 8*i: 8 + 8*i], "little"); fl = int.from_bytes(p[8 + 8*i: 12 + 8*i], "little")
        flags[fl] += 1
        k = "in forge" if dep in ids else ("in ACB (other forge)" if dep in acb else "MISSING")
        bad[k] += 1
        if k != "in forge" and len(ex[k]) < 15: ex[k].append(f"{e.name} -> {acb.get(dep, ("?", hex(dep)))[1]} [{acb.get(dep, ("", "", "?"))[2]}]")
print(f"entries {len(ents)}; dep count max {max(counts)}; flags {dict(flags)}")
for k, v in bad.items(): print(f"  {v:6d} {k}", ex.get(k, [])[:15])
