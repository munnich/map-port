"""cxb_maps.py [--xml PATH] [--dry-run]: write the ported maps' menu entries into the CXB's mapmanagermulti.xml.

One UnlockableUnlockCondition (level 1) + one ReferenceList UnlockableMap (with its MpWorld inline) per map variant
(maps.json + out/maps/<key>/menu/menu.json from menu_assets.py). Idempotent: entries whose objID lies in the range
reserved for ported maps (0xd7e50010 + 0x10*index + 2*variant, see menu_assets.cxb_ids) are removed first, every other
entry is left byte for byte; both Array_Size attributes are recomputed. The MpWorld's World is the map's LoadInfo slot
id, so the game loads multi/DataPC_<slot>.forge (and hides the entry for players without that file)."""
import argparse, json, os, re, sys
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "maps.json")))
RESERVED = range(0xd7e50010, 0xd7e50010 + 0x10 * 256)
ICON = 386389562

COND = """            <UnlockableUnlockCondition memberName="UnlockConditionList">
                <Handle propertyName="UnlockableRef" objID="{um}"/>
                <Pointer propertyName="UnlockConditionRef" classID="1688405200">
                    <UnlockConditionLevel memberName="UnlockConditionRef">
                        <Level value="1"/>
                    </UnlockConditionLevel>
                </Pointer>
            </UnlockableUnlockCondition>
"""
REF = """            <Reference propertyName="ReferenceList" classID="614032972" objID="{um}">
                <UnlockableMap memberName="ReferenceList">
                    <Icon value="{icon}"/>
                    <UIString memberName="NameString">
                        <OasisLineID value="{name}"/>
                    </UIString>
                    <UIString memberName="DescriptionString">
                        <OasisLineID value="{desc}"/>
                    </UIString>
                    <UIString memberName="UnlockDescriptionString">
                        <OasisLineID value="-1"/>
                    </UIString>
                    <UIString memberName="EvolutionInfoString">
                        <OasisLineID value="-1"/>
                    </UIString>
                    <UIString memberName="ControlDescString">
                        <OasisLineID value="-1"/>
                    </UIString>
                    <UIString memberName="ParamDescString">
                        <OasisLineID value="-1"/>
                    </UIString>
                    <Index value="0"/>
                    <InitiallyHidden value="{hidden}"/>
                    <Reference propertyName="MapReference" classID="2382761820" objID="{mw}">
                        <MpWorld memberName="MapReference">
                            <Handle propertyName="World" objID="{world}"/>
                            <TimeOfDay value="{tod}"/>
                            <UIString memberName="DisplayName">
                                <OasisLineID value="{name}"/>
                            </UIString>
                            <UIString memberName="Description">
                                <OasisLineID value="{desc}"/>
                            </UIString>
                            <Handle propertyName="TopViewImg" objID="{loading}"/>
                            <Handle propertyName="PreviewImg" objID="{preview}"/>
                        </MpWorld>
                    </Reference>
                </UnlockableMap>
            </Reference>
"""
COND_RE = re.compile(r' {12}<UnlockableUnlockCondition memberName="UnlockConditionList">\n {16}<Handle propertyName='
                     r'"UnlockableRef" objID="(\d+)"/>\n.*?\n {12}</UnlockableUnlockCondition>\n', re.S)
REF_RE = re.compile(r' {12}<Reference propertyName="ReferenceList" classID="\d+" objID="(\d+)">\n.*?\n {12}</Reference>\n',
                    re.S)


def entries(keys):
    conds, refs, rows = [], [], []
    for k in sorted(keys, key=lambda k: CFG["maps"][k]["index"]):
        menu = json.load(open(os.path.join(HERE, "out", "maps", k, "menu", "menu.json")))
        for v in menu["variants"]:
            assert v["unlockable"] in RESERVED
            conds.append(COND.format(um=v["unlockable"]))
            refs.append(REF.format(um=v["unlockable"], mw=v["mpworld"], icon=ICON, name=v["name_line"], desc=v["desc_line"],
                                   hidden="true" if v["hidden"] else "false", world=menu["world"], tod=f"{float(v['tod'])}",
                                   loading=v["loading"], preview=v["preview"]))
            rows.append(f"  {k:18} {v['english']:26} unlockable {v['unlockable']} world {menu['world']:#x}"
                        f"{' (hidden)' if v['hidden'] else ''}")
    return conds, refs, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("maps", nargs="*")
    ap.add_argument("--xml", default=CFG["server_xml"])
    ap.add_argument("--dry-run", action="store_true", help="write <xml>.new instead")
    args = ap.parse_args()
    keys = args.maps or list(CFG["maps"])
    s = open(args.xml, encoding="iso-8859-1").read()
    removed = [0, 0]
    def drop(rx, i):
        def f(m):
            if int(m.group(1)) in RESERVED:
                removed[i] += 1
                return ""
            return m.group(0)
        return f
    s = COND_RE.sub(drop(COND_RE, 0), s)
    s = REF_RE.sub(drop(REF_RE, 1), s)
    conds, refs, rows = entries(keys)
    s = s.replace("        </m_UnlockConditionList>\n", "".join(conds) + "        </m_UnlockConditionList>\n", 1)
    s = s.replace("        </m_ReferenceList>\n", "".join(refs) + "        </m_ReferenceList>\n", 1)
    n_cond = len(COND_RE.findall(s))
    n_ref = len(REF_RE.findall(s))
    s = re.sub(r'<m_UnlockConditionList Array_Size="\d+">', f'<m_UnlockConditionList Array_Size="{n_cond}">', s, count=1)
    s = re.sub(r'<m_ReferenceList Array_Size="\d+">', f'<m_ReferenceList Array_Size="{n_ref}">', s, count=1)
    root = ET.fromstring(s.encode("iso-8859-1"))  # well-formed, and the counts match what the game will read
    assert len(root.find(".//m_UnlockConditionList")) == n_cond and len(root.find(".//m_ReferenceList")) == n_ref
    out = args.xml + ".new" if args.dry_run else args.xml
    open(out, "w", encoding="iso-8859-1").write(s)
    print(f"{out}: removed {removed[0]} conditions / {removed[1]} maps of ours, added {len(conds)}; "
          f"Array_Size {n_cond} / {n_ref}")
    print("\n".join(rows))


if __name__ == "__main__":
    main()
