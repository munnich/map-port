import sys, os, collections, json
sys.path.insert(0, os.path.expanduser("~/Coding/Python/anvilforge-py-acrport/src"))
from analyze import ACB, ACR, forge_items, sig
from anvilforge.objectxml import decode_object
path, schema_name = sys.argv[1], sys.argv[2]
S = ACR if schema_name == "acr" else ACB
nested = collections.Counter()
tails = collections.Counter(); tailbytes = collections.Counter(); roots = collections.Counter()
for e, subs, deps in forge_items(path):
    for ext, name, uid, payload in subs:
        root = decode_object(payload, S, True)
        rt = root.get("Type"); roots[rt] += 1
        for el in root.iter():
            t = el.get("Type")
            if t and el is not root: nested[t] += 1
        for t in root.findall("RawTail"):
            tails[rt] += 1; tailbytes[rt] += int(t.get("Bytes"))
print("roots with RawTail:", {k: f"{tails[k]}/{roots[k]} ({tailbytes[k]//1024}KB)" for k in tails})
res = collections.defaultdict(list)
for t, c in nested.items():
    h = next((k for k, v in S.names.items() if v == t), None)
    if h is None: res["unresolved"].append(f"{t}:{c}"); continue
    a, r = sig(ACB, h), sig(ACR, h)
    st = "missing_in_acb" if a is None else ("same" if a == r else "differs")
    res[st].append(f"{t}:{c}")
for k, v in res.items(): print(f"\n== nested {k} ({len(v)})\n" + ", ".join(v))
