"""exptest.py <acb|acr> <Type[,Type]> <forge>... : run expdec over objects, cluster outcomes."""
import sys, os, collections, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import ACB, ACR, forge_items
from expdec import Dec, Fail

from schemas import ACB_TRUE
S = {"acb": ACB, "acr": ACR, "acbtrue": ACB_TRUE}[sys.argv[1]]
types = set(sys.argv[2].split(",")) if sys.argv[2] != "*" else None
d = Dec(S)
res = collections.Counter(); fails = collections.Counter(); ex = {}
for path in sys.argv[3:]:
    for e, subs, _ in forge_items(path):
        for ext, name, uid, p in subs:
            if ext == "ERR": continue
            t = S.name_of(ext)
            if types and t not in types: continue
            try:
                _, end, n = d.root(p)
                k = "exact" if end == n else ("short" if end < n else "over")
                res[(t, k)] += 1
                if k == "short": ex.setdefault((t, "short"), (name, end, n, p[end:end + 24].hex()))
            except Fail as x:
                key = (t, re.sub(r"\[\d+\]", "[]", x.path), str(x).split(" ")[0] + (" " + str(x).split(" ")[-1] if "tag" in str(x) or "type" in str(x) else ""))
                fails[key] += 1; ex.setdefault(key, (name, x.pos, len(p), p[max(0, x.pos - 8):x.pos + 16].hex()))
for k, v in sorted(res.items()): print(f"{v:6d} {k}")
print("-- failures")
for k, v in fails.most_common(25): print(f"{v:6d} {k}\n        e.g. {ex[k]}")
for k, v in ex.items():
    if k[1] == "short": print("short e.g.", k, v)
