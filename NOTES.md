# Porting ACR (Revelations) MP maps to ACB — Dyers

Source: `<ACR>/multi/DataPC_ACFE_Dyers_dlc.forge` (1609 entries, 8562 objects).
Target: `/home/a/vbox/Assassin's Creed Brotherhood/multi/`.

Everything runs with the anvilforge **worktree** venv (branch `acr-port-decoder`):
`~/Coding/Python/anvilforge-py-acrport/.venv/bin/python <script>`; scripts import anvilforge from
`~/Coding/Python/anvilforge-py-acrport/src`. `acb_idx.pkl`/`acr_idx.pkl` = id -> (type, name, forge) for the whole
ACB install and ACR's shared forges (rebuild with `index.py`). Entry ids shadow root-subpart ids in the index, so a
root object may show type `<entry>`.

Naming: `ACR_Rome_Multi` = *Brotherhood's* Rome map (ACB codename "ACR"). Revelations maps are `ACFE_*`.

## Status (2026-09-30)

- `anvilforge.fastload` (branch `acr-port-decoder`): engine-rule object codec. Decodes + byte-exactly re-encodes
  every object of ACB MtStMichel/Alhambra and ACR Dyers except custom-serialized types (Animation, FX,
  MaterialTemplate, NavMeshManager, PropertyControllerData, a few Whiteroom cinematic components).
- `convert.py`: Dyers -> ACB, installed into the Alhambra DLC slot. Output `out/DataPC_AC2MP_Alhambra_dlc.forge`
  (+ `.report.txt`). `validate.py` on it: every decodable object decodes with ACB's schema, no ACR-only type left,
  0 unresolved refs/links (handle "unresolved" count matches a retail ACB map).
- `slot_test.sh install|uninstall|status`: swap it into the ACB install (backs up the retail file first).
- **Not yet run in-game.**

## Engine serialization rules (FastLoadSerializer, from the Mac build in Ghidra)

- Property on disk iff `flags & 0x2000000`; BOOL always 1 byte. (objectxml.py's "elem_kind==1 bool is absent"
  rule and "pointer tag 0 = null" rule are wrong.)
- Root: `[import-table pre-header] status(1) flag(1) id(4) hash(4) props`.
- Pointer: status byte — 3 null; 1/2/5 link + id(4); 0/4 inline: `[flag(1) iff declared class derives from
  ManagedObject] id hash props` (SerializeObjectPropertyInternal Object** vs ManagedObject** overloads).
- Embedded OBJECT: `[flag iff ManagedObject] id hash props`; BASE_OBJECT: `id hash props`.
- REFERENCE: `tag extra id`; tag 0 -> object inlined (`hash props`) — EntityGroup.Entities.
- STRING: `len` then `len+1` bytes (NUL included) when len>0.
- DynamicProperties block after FXCommand/Material/BuildRow/BuildColumn/FX tables/GenericObject/
  PropertyControllerEntry own props: `count, (name, objhash, typebits, value)*`, value via generic rules
  (OBJECT_PTR = bare id).
- ACB_MP.schema has nameless placeholder props where the binary serializes a field (e.g.
  CrowdFraction.CrowdFractionName); `Schema.with_placeholders_filled(ACR)` gives the real ACB layout.
- Useful Ghidra addresses (acbmp_sf.exe): SerializePropertyGeneric 0x150510, SerializeObjectPropertyInternal
  0x14fdb0/0x14fea0, SerializeProperty(Reference) 0x150030, SerializeDynamicProperties 0x150f20,
  Entity::FastLoad 0x3decf0, EntityGroup::FastLoad 0x3e3ff0, CrowdDutyRegion::FastLoad 0x14643fa.
  `/home/a/.claude/jobs/.../allfl_named.txt` was a name->address map of ~3000 FastLoad routines (regenerable).

## ACB vs ACR data differences (MtStMichel exists in both: 5066 shared ids)

- Serialized-field differences are all "ACR added a field" (drop it) except MeshShape.MoppCodeVersionNumber (ACB
  only, always 5). ACR-only object types (253) must be stripped; in Dyers: SpawnNetworkParams, ChaseBreaker*,
  GcLMPCivilianSocialize, GcLMPRestObject/OLMPRestObject, CTF*/Flag/Hijack components, GameModeInfo,
  Trioviz3DSettings.
- Mesh/TextureMap `UserCategory` 0 in ACB (0x19 in ACR); TextureMap `CompiledTextureMap.MctCompressionEnabled` is 1 in
  ACB (pixels "MCT"-compressed), 0 in ACR — converted textures keep ACR's plain pixels with the flag at 0 (RISK).
- MeshShape: verts/indices/materials identical; MoppCode recompiled (RISK: kept ACR's). ACBMP.exe contains
  Havok's MOPP compiler (hkpMoppCodeGenerator...) if a rebuild is needed.
- Opaque shared objects (889 animations, 34 FX, 12 templates, 3 skeletons whose bone modifiers changed) are
  replaced by ACB's own bytes (same ids). Kept as ACR bytes (RISK): 4 FX, 12 MaterialTemplates
  (`--remap-acfe-templates` swaps them for same-named AC2_* templates), 21 NavMeshManagers, the TOD
  PropertyControllerData. ACFE_Characters_Skin/Body (not in the forge) -> AC2MP_Characters_Skin/Body.

## Data layers / game modes

- WorldDataLayerManager: layer -> GridCellDataBlock (list of object refs loaded when the layer is on).
  Grid = 4-level quadtree (85 cells); last cell (Cell00084) covers the whole map.
- ACB activates only `gamemode_<GamemodeParameters.GameModeEngineName>` (format string in ACBMP.exe): wanted_2,
  teamwanted (Alliance/Chest), vip, advwanted, catsmice (Manhunt), assassinate, teamvip (Escort), pacman,
  advteamwanted. Only teamwanted/vip/teamvip/wanted_2 layers exist; ACB maps keep spawns/OOB unlayered.
- Dyers puts spawns/OOB/chests in ACFE_* layers. Converter: objects of ACFE Wanted/Manhunt/Assassinate/Escort/
  Corruption -> appended to Cell00084 + filters cleared (61); chest-only -> gamemode_teamwanted (16); Deathmatch/
  CTF/Hijack/Training/story-only objects are never loaded (95); 26 ACR-only associations removed.
- Escort paths / chest spawn points: ACB gets them from `AdditionalWorldDataDLCElement` in a DLC ContentPackage
  (see DataPC_skins_0002_00000004_dlc), per world id and game-mode id (2 ChestCapture, 6 Assassinate, 7 TeamVIP).
  ACR stores them on World.chestSpawnPoints/TeamVIPPaths. Converter adds such an element to the slot package with
  Dyers' 4 TeamVIP paths and 16 Chest_Spawn entities.

## Map registration

- ACB DLC forge: ContentPackage (WorldDLCElement -> World, MpWorldDLCElement -> MpWorld), MpWorld_<map> entries
  (+ their TopView/Preview image entries), MpMapsDLCAddons in the World entry, and a GlobalMetaFile whose changelist
  matches the package's MinimumChangelistNumber.
- Base DataPC.forge "Game Bootstrap Settings" -> MapManagerMulti -> UnlockableMaps (DLC ones pre-registered,
  e.g. Map Alhambra 0x179a58ab -> MpWorld_Alhambra 0x7622f1ff).
- Slot takeover (current test path): output forge replaces DataPC_AC2MP_Alhambra_dlc.forge, keeps Alhambra's
  package/MpWorlds/images/MetaFile/addons, retargets them at Dyers' World (renamed AC2MP_Alhambra). Map name shown
  in-game stays "Alhambra"; acb2's diagnostics map-name table sees `AC2MP_Alhambra`.
- A standalone new map would need a new UnlockableMap in MapManagerMulti (DataPC.forge) + own MpWorld/package.

## If the in-game test fails

1. Crash while loading: rerun convert.py with `--remap-acfe-templates` (ACR shaders are the top suspect), then
   try dropping the 4 kept ACR FX / TOD controller.
2. Falling through geometry / no collision: MOPP code; rebuild via ACBMP's Havok compiler.
3. Black/garbled textures: MctCompressionEnabled=0 path.
4. NPCs/crowd missing or stuck: NavMeshManager (kept ACR bytes).
5. No spawns / instant OOB: layer remap (report lists what went where).
