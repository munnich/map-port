import sys, os, pickle, struct, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import ACR, forge_items
acb = pickle.load(open("acb_idx.pkl", "rb")); acr = pickle.load(open("acr_idx.pkl", "rb"))
c = collections.Counter(); ex = collections.defaultdict(list)
for e, subs, deps in forge_items(sys.argv[1]):
    for ext, name, uid, p in subs:
        if ext == "ERR" or ACR.name_of(ext) not in ("Entity", "EntityGroup"): continue
        seen = set()
        for off in range(0, len(p) - 3):
            i = struct.unpack_from("<I", p, off)[0]
            v = acr.get(i) or acb.get(i)
            if v and v[0] == "DataLayer" and (v[1].startswith(("gamemode", "ACFE", "MP_", "Spawn")) ):
                seen.add(v[1])
        for s in seen:
            c[s] += 1
            if len(ex[s]) < 4: ex[s].append(name)
for k, v in sorted(c.items()): print(f"{k:22s} {v:5d}  e.g. {ex[k]}")
