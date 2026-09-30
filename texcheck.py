import sys, os, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import forge_items
from anvilforge.fastload import Codec, DecodeError
from schemas import ACB_TRUE as T
c = Codec(T); u = lambda b: int.from_bytes(b, "little")
BPB = {1: 8, 2: 16, 3: 16, 4: 16, 5: 16}  # DXT1=8 bytes/4x4 block, DXT3/5=16 (by PixelFormat enum guess)
def expect(w, h, mips, bpb):
    tot = 0
    for m in range(mips):
        bw, bh = max(1, (max(1, w >> m) + 3) // 4), max(1, (max(1, h >> m) + 3) // 4)
        tot += bw * bh * bpb
    return tot
cnt = collections.Counter(); ex = collections.defaultdict(list)
for path in sys.argv[1:]:
    for e, subs, _ in forge_items(path):
        for ext, name, uid, p in subs:
            if T.name_of(ext) != "TextureMap": continue
            try: t = c.decode(p).obj
            except DecodeError: cnt["undecodable"] += 1; continue
            ct = t.fields["CompiledTextureMap"].obj
            if ct is None: cnt["no compiled"] += 1; continue
            f = ct.fields; w, h, d, mips, pf = u(f["Width"]), u(f["Height"]), u(f["Depth"]), u(f["NbMipMaps"]), u(f["PixelFormat"])
            hdr = (u(t.fields["Width"]), u(t.fields["Height"]), u(t.fields["NbMipMaps"]), u(t.fields["PixelFormat"]))
            n = len(f["Data"])
            key = [f"pf{pf}", f"mct{f['MctCompressionEnabled'][0]}", f"tf{u(f['TextureFormat'])}"]
            if hdr != (w, h, mips, pf): key.append("HEADER!=COMPILED")
            if pf in BPB and d <= 1:
                ex_ = expect(w, h, mips, BPB[pf]); key.append("size==calc" if n == ex_ else ("size>calc" if n > ex_ else "size<calc"))
            k = tuple(key); cnt[k] += 1
            if len(ex[k]) < 2: ex[k].append((name, w, h, mips, n, hdr))
for k, v in sorted(cnt.items(), key=str): print(v, k, ex.get(k))
