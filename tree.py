"""tree.py <acr|acbtrue> <forge> <Type|name> [maxlines]: pretty-print fastload trees."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import ACR, forge_items
from schemas import ACB_TRUE
from anvilforge.fastload import Codec, Obj, Ptr, Ref, Handle
import pickle
S = ACR if sys.argv[1] == "acr" else ACB_TRUE
IDX = {}
for fn in ("acb_idx.pkl", "acr_idx.pkl"):
    try: IDX.update(pickle.load(open(fn, "rb")))
    except Exception: pass
def idname(b):
    i = int.from_bytes(b, "little"); v = IDX.get(i)
    return f"{b.hex()}" + (f"({v[0]}:{v[1][:30]})" if v else "")
def show(v, ind, name, out):
    p = "  " * ind + (f"{name}: " if name else "")
    if isinstance(v, Obj):
        out.append(p + f"<{S.name_of(v.type_hash)} id={idname(v.id)}" + (f" flag={v.flag}" if v.flag is not None else "") + ">")
        for k, x in v.fields.items(): show(x, ind + 1, k, out)
        if v.dyn: out.append("  " * (ind + 1) + f"_dyn: {len(v.dyn)} entries")
    elif isinstance(v, Ptr):
        if v.obj: out.append(p + f"ptr[{v.status}]"); show(v.obj, ind + 1, "", out)
        else: out.append(p + f"ptr[{v.status}] " + (idname(v.link) if v.link else "null"))
    elif isinstance(v, Ref):
        out.append(p + f"ref[{v.tag},{v.extra}] {idname(v.id)}")
        if v.obj: show(v.obj, ind + 1, "", out)
    elif isinstance(v, Handle): out.append(p + f"handle[{v.tag}] {idname(v.id)}")
    elif isinstance(v, list):
        out.append(p + f"[{len(v)}]")
        for i, x in enumerate(v[:40]): show(x, ind + 1, f"[{i}]", out)
        if len(v) > 40: out.append("  " * (ind + 1) + "...")
    else:
        out.append(p + (v.hex() if len(v) <= 16 else f"<{len(v)} bytes>") + (f" '{v.decode('latin-1')}'" if 0 < len(v) < 80 and all(32 <= c < 127 for c in v) else ""))
c = Codec(S); want = sys.argv[3]; lim = int(sys.argv[4]) if len(sys.argv) > 4 else 200
for e, subs, _ in forge_items(sys.argv[2]):
    for ext, name, uid, p in subs:
        if S.name_of(ext) == want or name == want:
            out = []; show(c.decode(p).obj, 0, f"{name}", out)
            print("\n".join(out[:lim])); print("-----")
            if "--all" not in sys.argv: sys.exit()
