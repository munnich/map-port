import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import forge_items
path=sys.argv[1]; want=set(sys.argv[2:])
for e,subs,_ in forge_items(path):
    for ext,name,uid,p in subs:
        if name in want:
            want.discard(name); print(f"== {name} {len(p)}B")
            for i in range(0,min(len(p),400),32): print(f"  {i:5d} {p[i:i+32].hex(' ')}")
