"""fielddiff.py <Type> [n]: field-level diff of MtStMichel ACB/ACR pairs via fastload."""
import sys, os, pickle, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import ACR
from schemas import ACB_TRUE
from anvilforge.fastload import Codec, DecodeError, Obj, Ptr, Ref, Handle
a, r, _ = pickle.load(open("cross.pkl", "rb"))
ca, cr = Codec(ACB_TRUE), Codec(ACR)
def flat(v, path, out):
    if isinstance(v, Obj):
        out[path + "#type"] = v.type_hash
        if v.flag is not None: out[path + "#flag"] = v.flag
        for k, x in v.fields.items(): flat(x, f"{path}.{k}", out)
        if v.dyn: out[path + "#dyn"] = repr(v.dyn)[:80]
    elif isinstance(v, Ptr):
        out[path + "#st"] = v.status
        if v.link: out[path + "#link"] = v.link.hex()
        if v.obj: flat(v.obj, path, out)
    elif isinstance(v, Ref):
        out[path + "#ref"] = (v.tag, v.extra, v.id.hex())
        if v.obj: flat(v.obj, path, out)
    elif isinstance(v, list):
        out[path + "#n"] = len(v)
        for i, x in enumerate(v): flat(x, f"{path}[{i}]", out)
    elif isinstance(v, Handle): out[path] = (v.tag, v.id.hex())
    else: out[path] = v if len(v) <= 16 else f"<{len(v)}B crc {hash(v) & 0xffff:x}>"
want = sys.argv[1]; diffs = collections.Counter(); n = 0
for uid in a.keys() & r.keys():
    if ACR.name_of(r[uid][0]) != want or a[uid][2] == r[uid][2]: continue
    try: ta, tr = ca.decode(a[uid][2]).obj, cr.decode(r[uid][2]).obj
    except DecodeError: continue
    fa, fr = {}, {}; flat(ta, "", fa); flat(tr, "", fr)
    import re
    for k in set(fa) | set(fr):
        if fa.get(k) != fr.get(k):
            diffs[(re.sub(r"\[\d+\]", "[]", k), str(fa.get(k))[:30], str(fr.get(k))[:30])] += 1
    n += 1
print(want, "pairs differing:", n)
diffs = collections.Counter({k: v for k, v in diffs.items() if "Data[]" not in k[0]})
for k, c in diffs.most_common(int(sys.argv[2]) if len(sys.argv) > 2 else 12): print(f"{c:5d} {k}")
