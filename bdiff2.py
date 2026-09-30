import sys, os, pickle, collections
sys.path.insert(0, os.path.expanduser("~/Coding/Python/anvilforge-py-acrport/src"))
from analyze import ACR
a, r, _ = pickle.load(open("cross.pkl", "rb"))


def pre(x, y):
    n = min(len(x), len(y)); i = 0
    while i < n and x[i] == y[i]: i += 1
    return i


def suf(x, y):
    n = min(len(x), len(y)); i = 0
    while i < n and x[-1 - i] == y[-1 - i]: i += 1
    return i


want = sys.argv[1]; n = int(sys.argv[2])
shown = 0; ndiffbytes = collections.Counter()
for uid in sorted(a.keys() & r.keys()):
    if ACR.name_of(r[uid][0]) != want: continue
    pa, pr = a[uid][2], r[uid][2]
    if pa == pr: continue
    p = pre(pa, pr); s = suf(pa[p:], pr[p:])
    if len(pa) == len(pr):
        nd = sum(1 for i in range(len(pa)) if pa[i] != pr[i]); ndiffbytes[min(nd, 99)] += 1
    if shown < n:
        print(f"-- {a[uid][1][:40]} acb={len(pa)} acr={len(pr)} prefix={p} suffix={s} "
              f"acb_mid={pa[p:len(pa)-s][:32].hex()} acr_mid={pr[p:len(pr)-s][:32].hex()}")
        shown += 1
if ndiffbytes: print("same-len: #differing bytes histogram", sorted(ndiffbytes.items())[:15])
