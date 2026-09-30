"""getobj.py <forge> <Type> [n] [--min|--name X] : dump raw payloads of objects."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import ACR, forge_items
def objects(path, typ):
    for e, subs, deps in forge_items(path):
        for ext, name, uid, p in subs:
            if ext != "ERR" and ACR.name_of(ext) == typ: yield name, uid, p
if __name__ == "__main__":
    path, typ = sys.argv[1], sys.argv[2]
    objs = sorted(objects(path, typ), key=lambda o: len(o[2]))
    for name, uid, p in objs[: int(sys.argv[3]) if len(sys.argv) > 3 else 1]:
        print(f"== {name} {uid:#x} {len(p)}B")
        for i in range(0, len(p), 32): print(f"  {i:5d} {p[i:i+32].hex(' ')}")
