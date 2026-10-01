"""blockcheck.py <forge>: for every GridCellDataBlock that gets loaded (grid cells + WorldDataLayerManager layers),
are its activated objects in the block's own entry (retail: always) or a dependency of it -- or stranded in some
entry that is never loaded?"""
import sys, collections, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import forge_items
from convert import ACB_T
from anvilforge.fastload import Codec
c = Codec(ACB_T)
owner = collections.defaultdict(list); blocks = {}; ents = {}; used = set()
for e, subs, deps in forge_items(sys.argv[1]):
    ents[e.id] = (e.name, {d & 0xffffffff for d in deps})
    for ext, name, uid, pl in subs:
        owner[uid].append(e.id)
        t = ACB_T.name_of(ext)
        if t == "GridCellDataBlock":
            r = c.decode(pl)
            blocks[uid] = (name, e.id, [int.from_bytes(x.id, "little") for x in r.obj.fields["Objects"]][:int.from_bytes(r.obj.fields["NumberOfObjectsToActivate"], "little")])
        if t == "GridPartition":
            used |= {int.from_bytes(x.fields["DataBlock"].id, "little") for x in c.decode(pl).obj.fields["Cells"]}
        if t == "WorldDataLayerManager":
            used |= {int.from_bytes(a.fields["DataBlock"].id, "little") for a in c.decode(pl).obj.fields["LayersConfig"]}
tot = collections.Counter()
for bid in used & set(blocks):
    bn, eid, act = blocks[bid]
    for o in act:
        es = owner.get(o, [])
        k = "own entry" if eid in es else "dependency" if any(x in ents[eid][1] for x in es) else "STRANDED" if es else "not in forge"
        tot[k] += 1
        if k == "STRANDED" and tot[k] <= 8: print("  stranded:", bn, hex(o), "in", [ents[x][0] for x in es])
print(dict(tot))
