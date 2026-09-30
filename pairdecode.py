import sys, os, pickle, base64
sys.path.insert(0, os.path.expanduser("~/Coding/Python/anvilforge-py-acrport/src"))
from analyze import ACB, ACR
from anvilforge.objectxml import decode_object
import xml.etree.ElementTree as ET
a, r, _ = pickle.load(open("cross.pkl", "rb"))
want, n = sys.argv[1], int(sys.argv[2])
k = 0
for uid in sorted(a.keys() & r.keys()):
    if ACR.name_of(r[uid][0]) != want or a[uid][2] == r[uid][2]: continue
    for lab, S, blob in (("ACB", ACB, a[uid][2]), ("ACR", ACR, r[uid][2])):
        root = decode_object(blob, S, True)
        props = [(p.get("Name"), (p.text or p.get("ID") or p.get("Count") or p.get("State") or "")[:40]) for p in root.findall("Property")]
        tails = [(int(t.get("Bytes")), base64.b64decode(t.text)[:48].hex()) for t in root.findall("RawTail")]
        print(f"{lab} {a[uid][1]} len={len(blob)} props={props}\n     tail={tails}")
    k += 1
    if k >= n: break
