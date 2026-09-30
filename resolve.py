import sys, os, pickle, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import ACR, forge_items
acb = pickle.load(open("acb_idx.pkl", "rb")); acr = pickle.load(open("acr_idx.pkl", "rb"))
d = json.load(open("dyers.json"))
ids_own=set()
own = collections.defaultdict(collections.Counter)
for e in d["entries"]:
    for t, name, uid in e["subs"]:
        own[t]["in_acb" if uid in acb else "new"] += 1
        ids_own.add(uid)
print("Dyers own objects already present in ACB (by id):")
for t, c in sorted(own.items(), key=lambda x: -sum(x[1].values())):
    print(f"  {t:30s} {dict(c)}")
ext = d["ext_deps"]
ext=[x for x in ext if (int(x)&0xFFFFFFFF) not in ids_own]
print('deps not satisfied inside Dyers after masking:', len(ext))
where = collections.Counter(); types_acr_only = collections.Counter(); types_acb = collections.Counter(); missing = []
for x in ext:
    x = int(x) & 0xFFFFFFFF
    if x in acb: where["in_acb"] += 1; types_acb[acb[x][0]] += 1
    elif x in acr: where["acr_shared_only"] += 1; types_acr_only[acr[x][0]] += 1
    else: where["nowhere"] += 1; missing.append(x)
print("\nexternal deps:", dict(where))
print("  resolvable in ACB, types:", types_acb.most_common())
print("  ACR-shared-only, types:", types_acr_only.most_common())
print("  unresolved sample:", [hex(m) for m in missing[:10]])
ext=[int(x)&0xFFFFFFFF for x in ext]
acr_only = [x for x in ext if x not in acb and x in acr]
json.dump([(hex(x),) + tuple(acr[x]) for x in acr_only], open("acr_only_deps.json", "w"), indent=0)
