import sys, os, pickle, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import ACR, ACB, forge_items
acb = pickle.load(open("acb_idx.pkl", "rb")); acr = pickle.load(open("acr_idx.pkl", "rb"))
path, sch = sys.argv[1], sys.argv[2]
for e, subs, deps in forge_items(path):
    for ext, name, uid, p in subs:
        if ext != "ERR" and ACR.name_of(ext) == "WorldDataLayerManager":
            own = set()
            names = []
            for off in range(0, len(p) - 3):
                i = struct.unpack_from("<I", p, off)[0]
                v = acr.get(i) or acb.get(i)
                if v and v[0] == "DataLayer" and not v[1].startswith("Cell"):
                    names.append(v[1])
            layers = sorted(set(names))
            print(len(p), "bytes; non-cell layers:", layers)
