"""extrefs.py <forge>...: for every Ref/Handle/link id a forge uses but doesn't contain, which forges have it.
Needs the per-forge indexes from multiidx.py in $MIDX."""
import os, pickle, sys, glob, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import forge_items
from convert import ACB_T
from anvilforge.fastload import Codec, DecodeError, Handle, Ptr, Ref, walk
MIDX = os.environ["MIDX"]
where = collections.defaultdict(set); info = {}
for p in glob.glob(MIDX + "/*.pkl"):
    fg = os.path.basename(p)[:-4]
    for i, v in pickle.load(open(p, "rb")).items(): where[i].add(fg); info.setdefault(i, v)
codec = Codec(ACB_T)
def refs_of(path):
    own, out = set(), collections.defaultdict(set)   # id -> {(kind, referrer)}
    for e, subs, deps in forge_items(path):
        own.add(e.id)
        for ext, name, uid, p in subs:
            own.add(uid)
            try: root = codec.decode(p)
            except Exception: continue
            for o in walk(root.obj):
                own.add(int.from_bytes(o.id, "little"))
                stack = list(o.fields.values()) + [d[3] for d in o.dyn or []]
                while stack:
                    x = stack.pop()
                    if isinstance(x, list): stack.extend(x)
                    elif isinstance(x, Ref) and x.obj is None and x.tag in (1, 3): out[int.from_bytes(x.id, "little")].add(("ref", e.name))
                    elif isinstance(x, Handle): out[int.from_bytes(x.id, "little")].add(("handle", e.name))
                    elif isinstance(x, Ptr) and x.link: out[int.from_bytes(x.link, "little")].add(("link", e.name))
    return {i: r for i, r in out.items() if i and i not in own}
for path in sys.argv[1:]:
    ext = refs_of(path)
    by = collections.Counter()
    for i, r in ext.items():
        fgs = where.get(i, set())
        key = "NOWHERE" if not fgs else ("DataPC" if "DataPC" in fgs else ",".join(sorted(fgs))[:70])
        for kind in {k for k, _ in r}: by[(kind, key)] += 1
    print("##", path.split("/")[-1], len(ext), "external ids")
    for (kind, key), n in sorted(by.items(), key=lambda kv: -kv[1]): print(f"  {n:5d} {kind:6s} {key}")
    pickle.dump(ext, open(os.environ.get("OUT", "/dev/null"), "wb")) if os.environ.get("OUT") else None
