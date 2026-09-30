import sys, os, pickle, collections, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import ACR, forge_items
from anvilforge.objectxml import decode_object

acb = pickle.load(open("acb_idx.pkl", "rb")); acr = pickle.load(open("acr_idx.pkl", "rb"))
path = sys.argv[1]
BULK = {"Mesh", "TextureMap", "MaterialTemplate", "Animation", "MeshShape", "Skeleton",
        "NavMeshManager", "RealTreeMesh", "GridCellDataBlock"}
own, objs = set(), []
for e, subs, deps in forge_items(path):
    own.add(e.id)
    for ext, name, uid, payload in subs:
        own.add(uid); objs.append((ACR.name_of(ext), name, uid, payload))

structured, scanned = collections.Counter(), collections.Counter()
referrers = collections.defaultdict(set)
for t, name, uid, payload in objs:
    root = decode_object(payload, ACR, True)
    for el in root.iter():
        if el is root: continue
        if el.get("Kind") in ("REFERENCE",) or el.get("State") == "link" or el.get("Kind") == "HANDLE":
            i = int.from_bytes(bytes.fromhex(el.get("ID")), "little")
            if i and i not in own: structured[i] += 1; referrers[i].add(t)
    if t not in BULK and len(payload) < 65536:
        for off in range(0, len(payload) - 3):
            i = struct.unpack_from("<I", payload, off)[0]
            if i > 0x10000 and i not in own and (i in acb or i in acr):
                scanned[i] += 1; referrers[i].add(t)


def report(label, ids):
    loc = collections.Counter(); bytype = collections.defaultdict(collections.Counter)
    for i in ids:
        k = "both" if (i in acb and i in acr) else "acb_only" if i in acb else "acr_only" if i in acr else "unknown"
        loc[k] += 1
        ty = (acr.get(i) or acb.get(i) or ("?",))[0]
        bytype[k][ty] += 1
    print(f"\n{label}: {len(ids)} distinct ids -> {dict(loc)}")
    for k, c in bytype.items(): print(f"  {k}: {c.most_common(15)}")
    return loc


report("structured refs (decoded Reference/link/Handle) leaving Dyers", structured)
report("raw-scan hits (small non-bulk objects) matching a known id", scanned)
acr_only = [i for i in set(structured) | set(scanned) if i in acr and i not in acb]
print("\nACR-only referenced assets (need porting too):")
for i in sorted(acr_only, key=lambda i: acr[i][0]):
    print(f"  {i:#010x} {acr[i][0]:24s} {acr[i][1][:50]:50s} {acr[i][2]}  <- {sorted(referrers[i])[:4]}")
