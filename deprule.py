"""deprule.py <forge>: does an entry's dependency table == the in-forge entries holding objects it references?"""
import sys, os, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import forge_items
from convert import ACB_T
from anvilforge.fastload import Codec, Handle, Ptr, Ref, walk
c = Codec(ACB_T)
owner, deps, refs, opaque = {}, {}, collections.defaultdict(lambda: collections.defaultdict(set)), set()
for e, subs, d in forge_items(sys.argv[1]):
    deps[e.id] = {x & 0xFFFFFFFF for x in d}; owner[e.id] = e.id
    for ext, name, uid, p in subs:
        owner.setdefault(uid, e.id)
        try: root = c.decode(p)
        except Exception: opaque.add(e.id); continue
        for o in walk(root.obj):
            owner.setdefault(int.from_bytes(o.id, "little"), e.id)
            stack = list(o.fields.values()) + [x[3] for x in o.dyn or []]
            while stack:
                x = stack.pop()
                if isinstance(x, list): stack.extend(x)
                elif isinstance(x, Ref) and x.obj is None: refs[e.id][f"ref{x.tag}"].add(int.from_bytes(x.id, "little"))
                elif isinstance(x, Handle): refs[e.id]["handle"].add(int.from_bytes(x.id, "little"))
                elif isinstance(x, Ptr) and x.link: refs[e.id][f"link{x.status}"].add(int.from_bytes(x.link, "little"))
                elif isinstance(x, Ptr) and x.obj is not None: stack.append(x.obj) if False else None
st = collections.Counter(); miss_ex = []
for eid, d in deps.items():
    if eid == 16: continue
    pred = {}
    for kind, ids in refs[eid].items():
        for i in ids:
            o = owner.get(i)
            if o is not None and o != eid: pred.setdefault(o, set()).add(kind)
    for o, kinds in pred.items():
        st[("predicted&listed" if o in d else "predicted-NOT-listed") + ":" + "+".join(sorted(kinds))] += 1
        if o not in d and len(miss_ex) < 6: miss_ex.append((hex(eid), hex(o), kinds))
    for o in d - set(pred): st["listed-not-predicted" + (" (opaque src)" if eid in opaque else "")] += 1
for k, v in sorted(st.items()): print(f"{v:6d} {k}")
print("examples not listed:", miss_ex)
