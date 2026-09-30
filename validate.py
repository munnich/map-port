"""validate.py <converted.forge> : checks a converted forge reads back as ACB content.

1. unpacks as an ACB (v25) forge; every .data parses
2. every object decodes exactly with ACB's (placeholder-filled) schema, or is
   one of the known custom-serialized types; nothing ACR-only remains
3. every id referenced by a Ref / Handle / link Ptr resolves to an object in
   this forge or anywhere in the ACB install (acb_idx.pkl)
"""
import os, pickle, sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.expanduser("~/Coding/Python/anvilforge-py-acrport/src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import forge_items
from anvilforge.fastload import Codec, DecodeError, Handle, Obj, Ptr, Ref, walk
from anvilforge.games import Game
from anvilforge.schema import Schema

ACB = Schema.load_default(Game.BROTHERHOOD)
ACR = Schema.load_default(Game.REVELATIONS)
ACB_T = ACB.with_placeholders_filled(ACR)
ACR_ONLY = set(ACR.types_by_hash) - set(ACB.types_by_hash)
KNOWN_OPAQUE = {"Animation", "FX", "MaterialTemplate", "NavMeshManager", "PropertyControllerData"}

here = os.path.dirname(os.path.abspath(__file__))
acb_idx = pickle.load(open(os.path.join(here, "acb_idx.pkl"), "rb"))
codec = Codec(ACB_T)

path = sys.argv[1]
ids, res, problems = set(), Counter(), []
refs = defaultdict(set)  # kind -> ids
n_entries = 0
for e, subs, deps in forge_items(path):
    n_entries += 1
    ids.add(e.id)
    for ext, name, uid, p in subs:
        if ext == "ERR":
            problems.append(f"unparseable .data {e.name}: {name}"); continue
        ids.add(uid)
        t = ACB_T.name_of(ext)
        try:
            root = codec.decode(p)
        except DecodeError as x:
            res["opaque:" + t] += 1
            if t not in KNOWN_OPAQUE:
                problems.append(f"undecodable {t} {name}: {x}")
            continue
        res["decoded"] += 1
        for o in walk(root.obj):
            ids.add(int.from_bytes(o.id, "little"))
            if o.type_hash in ACR_ONLY:
                problems.append(f"ACR-only {ACR.name_of(o.type_hash)} in {t} {name}")
            for v in list(o.fields.values()) + [d[3] for d in o.dyn or []]:
                stack = [v]
                while stack:
                    x = stack.pop()
                    if isinstance(x, list): stack.extend(x)
                    elif isinstance(x, Ref) and x.obj is None and x.tag in (1, 3): refs["ref"].add(int.from_bytes(x.id, "little"))
                    elif isinstance(x, Handle): refs["handle"].add(int.from_bytes(x.id, "little"))
                    elif isinstance(x, Ptr) and x.link: refs["ptr-link"].add(int.from_bytes(x.link, "little"))

print(f"entries: {n_entries}, objects: {sum(res.values())}")
for k, v in sorted(res.items()): print(f"  {v:6d} {k}")
for kind, s in refs.items():
    s.discard(0)
    here_ = s & ids
    acb = {i for i in s - ids if i in acb_idx}
    missing = s - ids - acb
    print(f"{kind:9s}: {len(s):5d} ids -> in forge {len(here_)}, elsewhere in ACB {len(acb)}, UNRESOLVED {len(missing)}")
    if missing: print("     e.g.", [hex(i) for i in sorted(missing)[:10]])
print("problems:", len(problems))
for pr in problems[:30]: print("  ", pr)
