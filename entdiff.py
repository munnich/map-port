import sys, os, pickle, collections
sys.path.insert(0, os.path.expanduser("~/Coding/Python/anvilforge-py-acrport/src"))
from analyze import ACB, ACR
from anvilforge.objectxml import decode_object
a, r, _ = pickle.load(open("cross.pkl", "rb"))
def flat(el, path=""):
    out = []
    for ch in el:
        if ch.tag == "RawTail": out.append((path + "/RawTail", ch.get("Bytes"))); continue
        nm = ch.get("Name") or ch.get("Type") or ch.tag
        p = f"{path}/{nm}"
        v = ch.text if ch.text and ch.text.strip() else (ch.get("ID") or ch.get("State") or ch.get("Count"))
        if v is not None and len(ch) == 0: out.append((p, v))
        out += flat(ch, p)
    return out
diffpaths = collections.Counter(); tails = collections.Counter(); n = 0
for uid in sorted(a.keys() & r.keys()):
    if ACR.name_of(r[uid][0]) != "Entity" or a[uid][2] == r[uid][2]: continue
    fa = dict(flat(decode_object(a[uid][2], ACB, True)))
    fr = dict(flat(decode_object(r[uid][2], ACR, True)))
    tails[("acb_tail" if "/RawTail" in fa else "acb_full", "acr_tail" if "/RawTail" in fr else "acr_full")] += 1
    for k in set(fa) | set(fr):
        if fa.get(k) != fr.get(k):
            import re; diffpaths[re.sub(r"\[\d+\]", "", k)[:110]] += 1
    n += 1
print("pairs", n, "decode completeness:", dict(tails))
for k, c in diffpaths.most_common(30): print(f"{c:5d} {k}")
