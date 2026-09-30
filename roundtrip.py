"""roundtrip.py <acb|acbtrue|acr> <forge>...: decode+encode every object, count byte-exact round trips."""
import sys, os, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import ACB, ACR, forge_items
from schemas import ACB_TRUE
from anvilforge.fastload import Codec, DecodeError
S = {"acb": ACB, "acr": ACR, "acbtrue": ACB_TRUE}[sys.argv[1]]
c = Codec(S); res = collections.Counter(); bad = []
for path in sys.argv[2:]:
    for e, subs, _ in forge_items(path):
        for ext, name, uid, p in subs:
            if ext == "ERR": continue
            t = S.name_of(ext)
            try: r = c.decode(p)
            except DecodeError: res[(t, "opaque")] += 1; continue
            q = c.encode(r)
            if q == p: res[(t, "roundtrip")] += 1
            else: res[(t, "MISMATCH")] += 1; bad.append((t, name, len(p), len(q)))
tot = collections.Counter()
for (t, k), v in res.items(): tot[k] += v
print(dict(tot))
print("opaque by type:", sorted(((t, v) for (t, k), v in res.items() if k == "opaque"), key=lambda x: -x[1])[:12])
print("mismatches:", bad[:10])
