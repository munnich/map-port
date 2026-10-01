"""typecount.py <forge> [ACR]: count every object type (nested included) in a forge, decoded with ACB (or ACR) schema."""
import sys, os, collections, pickle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import forge_items
from convert import ACB_T, ACR
from anvilforge.fastload import Codec, walk, DecodeError
S = ACR if len(sys.argv) > 2 and sys.argv[2] == "ACR" else ACB_T
c = Codec(S); cnt = collections.Counter()
for e, subs, _ in forge_items(sys.argv[1]):
    for ext, name, uid, p in subs:
        try:
            for o in walk(c.decode(p).obj): cnt[S.name_of(o.type_hash)] += 1
        except Exception:
            cnt["opaque:" + str(S.name_of(ext))] += 1
pickle.dump(cnt, open(sys.argv[1].replace("/", "_")[-60:] + ".types.pkl", "wb"))
for k, v in sorted(cnt.items()): print(f"{v:7d} {k}")
