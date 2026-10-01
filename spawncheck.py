"""spawncheck.py <forge> [ACR]: where are the MultiSpawnPlayerComponent entities listed, and are they activated?
(A GridCellDataBlock activates only the first NumberOfObjectsToActivate entries of Objects.)"""
import sys, collections, pickle, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import forge_items
from convert import ACB_T
from anvilforge.fastload import Codec, walk
c = Codec(ACB_T)
multi = pickle.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "acb_multi_idx.pkl"), "rb"))
def lname(i):
    v = multi.get(i); return next(iter(v.values()))[1] if v else hex(i)
spawn, blocks, layers, cells, scene = {}, {}, {}, set(), set()
for e, subs, _ in forge_items(sys.argv[1]):
    for ext, name, uid, pl in subs:
        t = ACB_T.name_of(ext)
        if name.startswith("Death_Message_Total"): scene.add(uid)
        try: r = c.decode(pl)
        except Exception: continue
        if t == "GridCellDataBlock":
            blocks[uid] = (name, [int.from_bytes(x.id, "little") for x in r.obj.fields["Objects"]], int.from_bytes(r.obj.fields["NumberOfObjectsToActivate"], "little"))
        if t == "WorldDataLayerManager":
            for a in r.obj.fields["LayersConfig"]:
                layers[int.from_bytes(a.fields["DataBlock"].id, "little")] = lname(int.from_bytes(a.fields["Layer"].id, "little"))
        if t == "GridPartition":
            cells = {int.from_bytes(x.fields["DataBlock"].id, "little") for x in r.obj.fields["Cells"]}
        if t == "Entity":
            for o in walk(r.obj):
                if ACB_T.name_of(o.type_hash) == "MultiSpawnPlayerComponent":
                    spawn[uid] = int.from_bytes(o.fields["SpawnType"], "little")
where = collections.Counter()
for b, (bn, objs, nact) in blocks.items():
    kind = ("layer:" + layers[b]) if b in layers else ("grid-top" if b in cells and bn.endswith("84_DataBlock") else "grid" if b in cells else "unused-block")
    for i, o in enumerate(objs):
        tag = "spawn type %d" % spawn[o] if o in spawn else ("MP message scene" if o in scene else None)
        if tag: where[(kind, tag, "active" if i < nact else "INACTIVE")] += 1
print(len(spawn), "spawn entities")
for k, v in sorted(where.items(), key=str): print("   ", k, v)
