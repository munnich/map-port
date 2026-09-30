"""Census nested object types in a forge's non-bulk objects via type-hash scan."""
import sys, os, struct, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import ACB, ACR, forge_items, sig

BULK = {"Mesh", "TextureMap", "MaterialTemplate", "Animation", "MeshShape", "Skeleton",
        "NavMeshManager", "RealTreeMesh", "GridCellDataBlock", "FakeEntities"}
types = set(ACR.types_by_hash)
hits = collections.Counter(); tagged = collections.Counter(); where = collections.defaultdict(collections.Counter)
for e, subs, deps in forge_items(sys.argv[1]):
    for ext, name, uid, p in subs:
        if ext == "ERR": continue
        root_t = ACR.name_of(ext)
        if root_t in BULK: continue
        for off in range(4, len(p) - 3):
            h = struct.unpack_from("<I", p, off)[0]
            if h in types and h != ext:
                hits[h] += 1; where[h][root_t] += 1
                if off >= 6 and p[off - 6] == 4: tagged[h] += 1

by = collections.defaultdict(list)
for h, c in hits.items():
    a, r = sig(ACB, h), sig(ACR, h)
    st = "missing_in_acb" if a is None else ("same" if a == r else "differs")
    conf = "ptr-tagged" if tagged[h] else ""
    by[st].append((c, ACR.name_of(h), conf, dict(where[h].most_common(3))))
for st in ("missing_in_acb", "differs", "same"):
    rows = sorted(by[st], reverse=True)
    print(f"\n== {st}: {len(rows)} types")
    for c, n, conf, w in rows[: (60 if st != "same" else 40)]:
        print(f"  {c:6d} {n:40s} {conf:10s} {w}")
