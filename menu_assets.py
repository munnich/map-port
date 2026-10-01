"""menu_assets.py <acr_map.forge> <acb_multi_dir> <out_dir>: what the ACB menu needs to show a ported map as itself.

- Images: the CXB MpWorld's PreviewImg (map select, 512x256 DXT1) and TopViewImg (loading screen, 1024x512 DXT1).
  ACR ships Dyers' own art in the DLC forge (Dyers_MapDesc, Dyers_alternative_MapDesc; 512x512 DXT1 -- ACR's own
  MpWorld_Dyers points at Knight Hospital / Rome placeholders). Cropped to 2:1, re-encoded, and wrapped in copies of
  San Marco's / Venice's ACB entries (TextureMapSpec + TextureMap, same formats) under fresh ids. Both games store UI
  textures upside down, so no flip is needed beyond what the crop works in.
- Strings: name + description lines. LocalizationPackage::GetLocalizedStringRaw binary-searches the plain
  LocalizedData array before the compressed blob, and LocalizationManager tries every loaded collection (DLC
  packages included), so new line ids only need to be in one package per language.
Writes <out_dir>/*.data (one entry per image) + menu.json; patch_skins.py puts both into skins_0001 (a LoadOnDemand
source and localization collection via CharacterSkinsDLCElement::OnPackageLoaded)."""
import io, json, os, pickle, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageOps
from analyze import forge_items
from convert import ACB_T, ACR, DataFile, Game, HERE, _new_datafile, idb, u32, walk
from anvilforge.fastload import Codec, Handle, Ref

NAME = "DYERS"
DESCRIPTION = "A maze of rooftop workshops where cloth is dyed in great stone vats and hung out to dry."
LINE_IDS = (9000001, 9000002)  # name, description; ACB's own lines stop at ~321k
# (ACR image, upright crop top, ACB template entry id, new entry name, size)
IMAGES = {
    "preview": ("Dyers_MapDesc", 96, 0x723ac7f0, "ac2mp_img_Dyers", (512, 256)),           # SanMarco preview
    "topview": ("Dyers_alternative_MapDesc", 112, 0x18045bc, "AC2MP_LoadingScreen_Dyers", (1024, 512)),  # Venice loading
}
ID_BASE = 0xdff35000


def acr_image(acr_forge, entry_name):
    c = Codec(ACR)
    for e, subs, _d in forge_items(acr_forge):
        if e.name == entry_name:
            for ext, _n, _u, p in subs:
                if ACR.name_of(ext) == "TextureMap":
                    o = c.decode(p).obj
                    w, h = u32(o.fields["Width"]), u32(o.fields["Height"])
                    d = b"".join(o.fields["CompiledTextureMap"].obj.fields["Data"])
                    return Image.frombytes("RGBA", (w, h), d[: w * h // 2], "bcn", 1)
    raise SystemExit(f"{entry_name} not in {acr_forge}")


def dxt1(img):
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "DDS", pixel_format="DXT1")
    return buf.getvalue()[128:]


def free_family(taken, start, span=0x20):
    base = start
    while any(base + k in taken for k in range(-span, span + 1)):
        base += 2 * span + 1
    taken.update(range(base - span, base + span + 1))
    return base


def remap_family(root, old_base, new_base, span=0x20):
    """Give a template's own object ids and its internal handles/refs (all within +-span of its entry id) new ids."""
    def m(b):
        i = u32(b)
        return idb(new_base + i - old_base) if abs(i - old_base) <= span else b
    for o in walk(root.obj):
        o.id = m(o.id) if o.id and o.id != bytes(4) else o.id
        stack = list(o.fields.values())
        while stack:
            v = stack.pop()
            if isinstance(v, list):
                stack.extend(v)
            elif isinstance(v, (Handle, Ref)):
                v.id = m(v.id)


def main():
    acr_forge, acb_dir, out = sys.argv[1:4]
    os.makedirs(out, exist_ok=True)
    acb = Codec(ACB_T)
    taken = set(pickle.load(open(os.path.join(HERE, "acb_multi_idx.pkl"), "rb")))
    templates = {}
    for e, subs, _d in forge_items(os.path.join(acb_dir, "DataPC_extra.forge")):
        if e.id in {t[2] for t in IMAGES.values()}:
            templates[e.id] = [[ext, n, p] for ext, n, _u, p in subs]
    meta = {"name": NAME, "description": DESCRIPTION, "line_ids": LINE_IDS, "images": {}}
    for key, (src, top, tid, new_name, (w, h)) in IMAGES.items():
        img = ImageOps.flip(acr_image(acr_forge, src))  # upright
        img = img.crop((0, top, 512, top + 256)).resize((w, h), Image.LANCZOS)
        img.save(os.path.join(out, new_name + ".png"))
        data = dxt1(ImageOps.flip(img))  # back to stored orientation
        assert len(data) == w * h // 2
        base = free_family(taken, ID_BASE)
        subs = []
        for ext, n, p in templates[tid]:
            root = acb.decode(p)
            remap_family(root, tid, base)
            if ACB_T.name_of(ext) == "TextureMap":
                assert (u32(root.obj.fields["Width"]), u32(root.obj.fields["Height"])) == (w, h)
                ctm = root.obj.fields["CompiledTextureMap"].obj
                assert len(ctm.fields["Data"]) == len(data)
                ctm.fields["Data"] = [bytes([b]) for b in data]
                n = new_name + ("_DiffuseMap" if key == "topview" else "_Map")
            else:
                n = new_name + ("_DiffuseMapDesc" if key == "topview" else "_MapDesc")
            subs.append([ext, n, acb.encode(root)])
        fn = f"{subs[0][1]}.data"
        open(os.path.join(out, fn), "wb").write(_new_datafile(fn, subs).build(Game.BROTHERHOOD))
        meta["images"][key] = {"entry": fn, "id": base}
        print(f"{key}: {fn} id {base:#x} ({base}) from {src}")
    json.dump(meta, open(os.path.join(out, "menu.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
