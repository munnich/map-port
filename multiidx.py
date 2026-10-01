"""multiidx.py <forge> <out.pkl>: id -> (type, name) of every entry and sub-object in one forge (merge with
multiidx_merge to get id -> {forges})."""
import sys, os, pickle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import forge_items
from convert import ACB_T
d = {}
for e, subs, _ in forge_items(sys.argv[1]):
    d[e.id] = ("<entry>", e.name, e.id)
    for ext, name, uid, p in subs:
        if ext != "ERR": d.setdefault(uid, (ACB_T.name_of(ext), name, e.id))
pickle.dump(d, open(sys.argv[2], "wb"))
