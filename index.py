"""Index every object id (entry + subpart) -> (type, name, forge) across forges."""
import sys, os, pickle, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import ACR, forge_items

out = sys.argv[1]
idx = {}
for path in sys.argv[2:]:
    fn = os.path.basename(path)
    n = 0
    try:
        for e, subs, deps in forge_items(path):
            idx.setdefault(e.id, ("<entry>", e.name, fn))
            for ext, name, uid, _ in subs:
                if ext != "ERR":
                    idx.setdefault(uid, (ACR.name_of(ext), name, fn)); n += 1
    except Exception as ex:
        print("FAIL", fn, ex, flush=True)
    print(fn, n, flush=True)
pickle.dump(idx, open(out, "wb"))
print("total ids", len(idx))
