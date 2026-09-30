import sys, os, collections
sys.path.insert(0, os.path.expanduser("~/Coding/Python/anvilforge-py-acrport/src"))
from analyze import ACB, ACR, forge_items
def load(p):
    d = {}
    for e, subs, deps in forge_items(p):
        for ext, name, uid, payload in subs:
            d[uid] = (ext, name, payload)
    return d
a = load(sys.argv[1]); r = load(sys.argv[2])
common = set(a) & set(r)
print("acb objs", len(a), "acr objs", len(r), "common ids", len(common))
st = collections.defaultdict(collections.Counter)
examples = {}
for uid in common:
    ea, na, pa = a[uid]; er, nr, pr = r[uid]
    t = ACR.name_of(er)
    if pa == pr: st[t]["identical"] += 1
    elif len(pa) == len(pr): st[t]["same_len_diff_bytes"] += 1
    else:
        st[t]["len_diff"] += 1; st[t]["delta_sum"] += len(pr) - len(pa)
        examples.setdefault(t, []).append((uid, na, len(pa), len(pr)))
for t, c in sorted(st.items(), key=lambda x: -sum(v for k, v in x[1].items() if k != "delta_sum")):
    print(f"{t:32s} {dict(c)}")
import pickle; pickle.dump((a, r, examples), open("cross.pkl", "wb"))
