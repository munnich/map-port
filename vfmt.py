import sys, os, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import forge_items
from anvilforge.fastload import Codec, DecodeError, walk
from schemas import ACB_TRUE as T, ACR
S = ACR if sys.argv[1] == "acr" else T
c = Codec(S); cnt = collections.Counter(); ex = {}
for path in sys.argv[2:]:
    for e, subs, _ in forge_items(path):
        for ext, name, uid, p in subs:
            if S.name_of(ext) != "Mesh": continue
            try: r = c.decode(p)
            except DecodeError: cnt["undecodable"] += 1; continue
            for o in walk(r.obj):
                if S.name_of(o.type_hash) == "MeshData":
                    vb = len(o.fields["VertexBufferData"]); fmt = o.fields["VertexFormat"][0]; st = o.fields["VertexStride"][0]
                    nv = max((int.from_bytes(pr.fields["MinIndex"],"little") + int.from_bytes(pr.fields["NumVertices"],"little") for pr in o.fields["StandardPrimitives"]), default=0)
                    k = (fmt, st, "vb==nv*stride" if vb == nv * st else ("vb>nv*stride" if vb > nv*st else "vb<nv*stride"))
                    cnt[k] += 1; ex.setdefault(k, (name, vb, nv, st))
for k, v in sorted(cnt.items(), key=str): print(v, k, ex.get(k))
