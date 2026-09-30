import sys, os
sys.path.insert(0, os.path.expanduser("~/Coding/Python/anvilforge-py-acrport/src"))
from analyze import ACB, ACR
from anvilforge.schema import Kind
def desc(s, p):
    k = p.kind
    kn = Kind(k).name if k < 32 else k
    extra = ""
    if k in (17,18,19,20,21,22,23,24,25,28,29):
        extra = " -> " + s.name_of(p.object_hash)
    return f"{s.name_of(p.name_hash)}:{kn}{extra} flags={p.flags:#x}"
def chain_names(s, h):
    out=[]; t=s.type_by_hash(h)
    while t: out.append(s.name_of(t.type_hash)); t=s.type_by_hash(t.base_type_hash)
    return out
for name in sys.argv[1:]:
    h = next(k for k,v in ACR.names.items() if v==name)
    a = [desc(ACB,p) for p in ACB.property_chain(h)]
    r = [desc(ACR,p) for p in ACR.property_chain(h)]
    print(f"### {name}  ACB chain={chain_names(ACB,h)} ACR chain={chain_names(ACR,h)}")
    import difflib
    for l in difflib.unified_diff(a, r, "ACB", "ACR", n=1, lineterm=""): print("  ", l)
