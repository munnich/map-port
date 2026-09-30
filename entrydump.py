import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import ACR, ACB, forge_items
path = sys.argv[1]; want = sys.argv[2]
for e, subs, deps in forge_items(path):
    names = [ACR.name_of(x[0]) for x in subs if x[0] != "ERR"]
    if want in names:
        print(f"entry {e.name} id={e.id:#x} n_subs={len(subs)} deps={len(deps)}")
        for ext, name, uid, p in subs:
            print(f"   {ACR.name_of(ext):28s} {name[:40]:40s} {uid:#010x} {len(p)}B")
