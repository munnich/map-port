"""chain.py <acb|acr> <TypeName|0xhash>... : serialized property chain (with class boundaries)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import ACB, ACR
from anvilforge.schema import Kind
S = ACB if sys.argv[1]=="acb" else ACR
for a in sys.argv[2:]:
    h = int(a,16) if a.startswith("0x") else next(k for k,v in S.names.items() if v==a)
    t = S.type_by_hash(h); cls=[]
    while t: cls.append(t); t=S.type_by_hash(t.base_type_hash)
    print(f"### {S.name_of(h)} ({h:#010x})")
    for t in reversed(cls):
        ps=[p for p in t.properties if p.flags & 0x2000000]
        if ps: print(f"  -- {S.name_of(t.type_hash)}")
        for p in ps:
            k=Kind(p.kind).name if p.kind<32 else str(p.kind)
            ek=Kind(p.elem_kind).name if p.elem_kind<32 else p.elem_kind
            tgt=S.name_of(p.object_hash) if p.kind in (17,18,19,20,21,22,23,24,25,28,29) else ""
            print(f"     {S.name_of(p.name_hash):30s} {k:15s} elem={ek:14s} {tgt:28s} flags={p.flags:#010x}")
