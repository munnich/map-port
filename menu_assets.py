"""menu_assets.py [map ...]: what the ACB menu needs to show ported maps as themselves (config: maps.json).

Per map -> out/maps/<key>/menu/: one image entry per variant preview/loading image + menu.json (ids, strings).
- Images: the CXB MpWorld's PreviewImg (map select, 512x256 DXT1) and TopViewImg (loading screen, 1024x512 DXT1).
  ACR's art is <Map>_MapDesc / <Map>_Alternative_MapDesc (512x512 DXT1, full mips) in ACR's DataPC_extra.forge, or
  in the map's own forge for its DLC maps (ACR's MpWorld_Dyers itself points at placeholders). Each is cropped to a
  2:1 band, re-encoded, and wrapped in a copy of San Marco's / Venice's ACB entry (TextureMapSpec + TextureMap, same
  formats; only id fields differ). Both games store UI textures upside down.
- Strings: the variant's ACR name line in every language ACR has (DataPC_localization.forge text packages, read with
  locdecode.py); an optional English description. New line ids: 9000000 + 100*index + 2*variant + 1 (name) / + 2
  (description), so Dyers keeps 9000001/9000002.
patch_skins.py puts both into the skins forges, cxb_maps.py writes the CXB entries."""
import io, json, os, pickle, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageOps
from analyze import forge_items
from convert import ACB_T, ACR, Game, HERE, _new_datafile, idb, u32, walk
from anvilforge.fastload import Codec, Handle, Ref
from locdecode import package_strings

CFG = json.load(open(os.path.join(HERE, "maps.json")))
TEMPLATES = {"preview": (0x723ac7f0, (512, 256), "_MapDesc", "_Map"),                    # ac2mp_img_SanMarco
             "loading": (0x18045bc, (1024, 512), "_DiffuseMapDesc", "_DiffuseMap")}       # LoadingScreen_Venise
SPAN = 0x20


def line_ids(index, v):
    base = 9000000 + 100 * index + 2 * v
    return base + 1, base + 2


def cxb_ids(index, v):
    base = 0xd7e50010 + 0x10 * index + 2 * v
    return base, base + 1  # UnlockableMap, MpWorld


def acr_images(path, names):
    """{TextureMapSpec entry name: upright PIL image of its top mip} for the wanted entries of one ACR forge."""
    c, out = Codec(ACR), {}
    for e, subs, _d in forge_items(path):
        if e.name in names:
            for ext, _n, _u, p in subs:
                if ext != "ERR" and ACR.name_of(ext) == "TextureMap":
                    o = c.decode(p).obj
                    w, h = u32(o.fields["Width"]), u32(o.fields["Height"])
                    d = b"".join(o.fields["CompiledTextureMap"].obj.fields["Data"])
                    out[e.name] = ImageOps.flip(Image.frombytes("RGBA", (w, h), d[: w * h // 2], "bcn", 1))
    missing = set(names) - set(out)
    if missing:
        raise SystemExit(f"{os.path.basename(path)}: no {sorted(missing)}")
    return out


def acr_lines(lines):
    """{line: {language: text}} from ACR's text localization packages."""
    c, out = Codec(ACR), {}
    for e, subs, _d in forge_items(os.path.join(CFG["acr_multi"], "DataPC_localization.forge")):
        for ext, _n, _u, p in subs:
            if ext != "ERR" and ACR.name_of(ext) == "LocalizationPackage":
                o = c.decode(p).obj
                if u32(o.fields["Type"]) != 0:
                    continue
                s, lang = package_strings(c, p), u32(o.fields["Language"])
                for i in lines:
                    if s.get(i):
                        out.setdefault(i, {})[lang] = s[i]
    return out


def dxt1(img):
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "DDS", pixel_format="DXT1")
    return buf.getvalue()[128:]


def free_family(taken, start):
    base = start
    while any(base + k in taken for k in range(-SPAN, SPAN + 1)):
        base += 2 * SPAN + 1
    taken.update(range(base - SPAN, base + SPAN + 1))
    return base


def remap_family(root, old_base, new_base):
    """Give a template's own object ids and its internal handles/refs (all within +-SPAN of its entry id) new ids."""
    def m(b):
        i = u32(b)
        return idb(new_base + i - old_base) if abs(i - old_base) <= SPAN else b
    for o in walk(root.obj):
        if o.id and o.id != bytes(4):
            o.id = m(o.id)
        stack = list(o.fields.values())
        while stack:
            v = stack.pop()
            if isinstance(v, list):
                stack.extend(v)
            elif isinstance(v, (Handle, Ref)):
                v.id = m(v.id)


def image_entry(acb, template, img, kind, name, base):
    tid, (w, h), spec_suffix, tm_suffix = TEMPLATES[kind]
    data = dxt1(ImageOps.flip(img.resize((w, h), Image.LANCZOS)))  # back to stored (upside-down) orientation
    subs = []
    for ext, n, p in template:
        root = acb.decode(p)
        remap_family(root, tid, base)
        if ACB_T.name_of(ext) == "TextureMap":
            ctm = root.obj.fields["CompiledTextureMap"].obj
            assert (u32(root.obj.fields["Width"]), u32(root.obj.fields["Height"])) == (w, h)
            assert len(ctm.fields["Data"]) == len(data)
            ctm.fields["Data"] = [bytes([b]) for b in data]
            n = name + tm_suffix
        else:
            n = name + spec_suffix
        subs.append([ext, n, acb.encode(root)])
    return subs


def main():
    keys = sys.argv[1:] or list(CFG["maps"])
    worlds = json.load(open(os.path.join(HERE, "bootstrap_worlds.json")))
    acb = Codec(ACB_T)
    taken = set(pickle.load(open(os.path.join(HERE, "acb_multi_idx.pkl"), "rb")))
    templates = {}
    for e, subs, _d in forge_items(os.path.join(CFG["acb_retail"], "DataPC_extra.forge")):
        if e.id in {t[0] for t in TEMPLATES.values()}:
            templates[e.id] = [[ext, n, p] for ext, n, _u, p in subs]
    # gather sources: ACR DataPC_extra once, map forges per map
    want = {}
    for k in keys:
        m = CFG["maps"][k]
        for v in m["variants"]:
            for kind in ("preview", "loading"):
                src, entry, _top = v[kind]
                want.setdefault("DataPC_extra.forge" if src == "extra" else m["acr_forge"], set()).add(entry)
    imgs = {}
    for forge, names in want.items():
        print("reading", forge, sorted(names))
        imgs.update(acr_images(os.path.join(CFG["acr_multi"], forge), names))
    lines = acr_lines({v["name_line"] for k in keys for v in CFG["maps"][k]["variants"]})
    for k in keys:
        m = CFG["maps"][k]
        out = os.path.join(HERE, "out", "maps", k, "menu")
        os.makedirs(out, exist_ok=True)
        for f in os.listdir(out):
            os.remove(os.path.join(out, f))
        slot_id = worlds[m["slot"]]
        meta = {"key": k, "world": slot_id, "slot": m["slot"], "strings": {}, "images": [], "variants": []}
        for vi, v in enumerate(m["variants"]):
            name_line, desc_line = line_ids(m["index"], vi)
            names = lines.get(v["name_line"])
            if not names or 1 not in names:
                raise SystemExit(f"{k}: ACR line {v['name_line']} not found")
            meta["strings"][name_line] = names
            if v.get("description"):
                meta["strings"][desc_line] = {1: v["description"]}
            ids = {}
            for kind in ("preview", "loading"):
                src, entry, top = v[kind]
                base = free_family(taken, slot_id + 0x10400 + 0x100 * vi + (0x80 if kind == "loading" else 0))
                img = imgs[entry].crop((0, top, 512, top + 256))
                name = f"{'ac2mp_img' if kind == 'preview' else 'AC2MP_LoadingScreen'}_{k}{'_v%d' % vi if vi else ''}"
                img.resize(TEMPLATES[kind][1], Image.LANCZOS).save(os.path.join(out, name + ".png"))
                subs = image_entry(acb, templates[TEMPLATES[kind][0]], img, kind, name, base)
                fn = f"{subs[0][1]}.data"
                open(os.path.join(out, fn), "wb").write(_new_datafile(fn, subs).build(Game.BROTHERHOOD))
                meta["images"].append({"entry": fn, "id": base})
                ids[kind] = base
            um, mw = cxb_ids(m["index"], vi)
            meta["variants"].append({"unlockable": um, "mpworld": mw, "name_line": name_line,
                                     "desc_line": desc_line if v.get("description") else -1, "tod": v["tod"],
                                     "hidden": bool(v.get("hidden")), "preview": ids["preview"], "loading": ids["loading"],
                                     "english": names[1]})
            print(f"{k} v{vi}: {names[1]!r} ({len(names)} languages) lines {name_line}/{desc_line if v.get('description') else -1}"
                  f" images {ids['preview']:#x}/{ids['loading']:#x} cxb {um}/{mw}")
        json.dump(meta, open(os.path.join(out, "menu.json"), "w"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
