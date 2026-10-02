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
- MeshShape: verts/indices/materials identical; MoppCode recompiled by ACR (159/173 shared MtStMichel shapes differ).
  ACR's MOPPs are NOT safe in ACB -- see "Collision: let ACB rebuild every MOPP" below.
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

## Loader rule: dependencies must be in-forge

Every entry's dependency table (u32 count + (id u32, flag u32) pairs at the start of the .data, i.e. entry offset +
0x1b8 in the forge) may only list entries of the *same* forge — retail Alhambra: 1749/1749 in-forge. ACB's streaming
code (ACBMP.exe 0x01b06b30, reached from 0x01b098a0) crashed walking a table that pointed at templates living in other
forges. convert.py now vendors such entries (copies them, or wraps a sub-object copy as its own entry); `depcheck.py`
verifies. In-game test 1 (default build) crashed in memcpy during load; test 2 (template remap, before vendoring)
crashed in that loader.

## Loader rule: entry headers must not straddle a streaming chunk

`scimitar::BigFileAsynchStream::ExecutePrefetch` (Mac 0x1ce0c0) streams a forge in chunks aligned to 0x8000;
`HandleChunkPrefetches` (Mac 0x1cf2b0, ACBMP.exe 0x01b06b30) then reads each started entry's dependency table *in
place* at `chunk_buf + (entry_off - chunk_off) + 0x1b8`. A header + table running past the chunk end is read from
unrelated memory -> huge "count" -> the entry's dep array (14-bit size) overflows -> memcpy crash at acbmp+0x1acdb03
via 0x17877ec/0x1706f23 (tests 1 and 3), or a bad read at +0x1706f98 (test 2). Retail forges: every entry 16-aligned,
0 headers straddle 0x10000 (one Alhambra entry straddles 0x8000). anvilforge's repack packed entries back to back
(10-22 straddles); `repack(..., align_entries=True)` (anvilforge acr-port-decoder) now lays entries out retail-style.
`aligncheck.py` verifies.

## Slot takeover keeps the slot's World id

Test 4 (aligned build) loaded without crashing but hung before spawning, like a map that isn't installed. The rest of ACB
knows Alhambra's World by id 0x42b7dce4 (DataPC.forge Game Bootstrap Settings / AssassinSoundSettings; the skins DLC
package descriptors). convert.py now renumbers Dyers' World (0x3ba8d804) to the slot's id: own id, refs, raw id
fields, dep tables, and a raw replace in the 21 NavMeshManagers (retail navmeshes embed the world id too). `idgrep.py`
finds any id in decompressed forges.

AdditionalWorldData: `AdditionalWorldDataDLCElement::OnPackageLoaded` (Mac 0xe6ad04) keeps only the FIRST loaded element's
table (the skins DLC packages carry every world's chest/escort data); later ones are freed. So the converter no longer
adds its own element, and Chest/Escort on the ported map currently use retail Alhambra's data (0x4fd98273 /
0x4fd987d9, entity refs that don't exist in Dyers) -- expect those two modes to be broken until that is solved.

## Test 5: still hangs before spawning (Wanted + Assassinate) -> retail conformance pass

- Entry order: convert.py sorted output files as strings ("1000_-_" < "2_-_"), so the World sat at index 719. Retail
  (and ACR) map forges: GlobalMetaFile, World, Cell00084_DataBlock, ..., ContentPackage, MpWorlds + images last.
  `retail_order()` now keeps the source order, then added entries, then the slot's registration entries.
- Entries we add got create_entry()'s derived `extension` (0xbcfb3c7a); retail map forges have 0 everywhere.
- World SoundBankWorldComponent: ACR's AutoLoad bank has WwiseID 0; now the slot world's (Alhambra 0x6b041403).
- Control build: `roundtrip.py` pushes retail Alhambra through the same writer (`out/control/`,
  `slot_test.sh install control`). If the control hangs too, the writer (recompression is 53.8 MB vs retail 97.5 MB,
  layout, metadata) is at fault, not Dyers' content.
- Live inspection: /proc/<pid>/mem and /proc/<pid>/task/*/syscall are readable without stopping the game (Wine sets
  PR_SET_PTRACER_ANY); a stack sampler scanning thread stacks for return addresses into ACBMP.exe works.

## Test 6: Dyers still hangs, control (retail Alhambra through our writer) loads -> content, not writer

Retail-vs-ours comparison (typecount.py, extrefs.py with the multi-forge index acb_multi_idx.pkl from multiidx.py):
- Retail maps reference only DataPC.forge outside their own forge (plus dangling handles). Ours referenced
  AC2MP_VEN_WaterSea_01a, which lives only in SanMarco's forge (a --remap-acfe-templates target) -> never loadable.
- Retail maps ship AC2MP_Characters_Body/Skin as their own entries (flag-1 deps of the users); ours referenced them
  with no entry/deps. `add_reference_deps()` now adds flag-1 deps for both cases; vendor_dependencies copies them.
- Every ACB map has one `Death_Message_Total_<map>_02` Entity (Scene with 61 MPMessage / 50 MPAbilityMessageMap /
  21 MPDeathContextConditionClip, identical across maps); Dyers has none. `add_mp_message_scene()` copies the
  slot's into Cell00084. (Retail also has a CU_Herald body + Cloth/LiteRagdoll -- not copied yet.)
- Dependency tables are NOT simply "entries holding referenced objects" (deprule.py): retail lists only part.

## Test 7 -> runtime trace -> ROOT CAUSE of the pre-spawn hang: spawn points never activated

Runtime tracing (`trace_lookups.gdb`: gdb dprintf on BigFileFat::GetIndexFromKey at ACBMP.exe 0x01b32e4f, logs every
forge-index lookup + found flag + caller; attach to the running game, pass Wine's signals): in both the Dyers run
and the control, every id was found; World, Cell00084, persona templates, AbilitySelectionPage, ReadyPage all load.
So nothing is missing -- the hang is after loading, at spawn.

GridCellDataBlock activates only the first `NumberOfObjectsToActivate` entries of `Objects`; most blocks end with a
not-activated tail (Dyers Cell00084: 377 objects, 98 activated). `_append` added the standard-mode objects (incl.
all 59 player spawn entities moved out of ACFE_* layers) at the END and bumped the count -> they stayed inactive
and 62 tail objects got activated instead. No MultiSpawnPlayerComponent registered -> no spawn candidate -> the
client waits forever (retail: all 95 Alhambra spawns active). `activate_objects()` now inserts into the active
prefix; `spawncheck.py` verifies. Same fix applies to the copied MP message scene.

Also learned: LoadOnDemandManager::LoadObject silently never completes when no source forge has the id as an
*entry* (FileExistsInAlternateSource -> BigFile::GetFileIndex) -- the real "map not installed" hang.

## Test 8 -> spawn probes -> second half of the root cause: moved objects were never loaded

Spawn probes (trace_lookups.gdb: MultiSpawnManager_Update 0x005c6d80, Server_GetBestSpawnPoint 0x005c72d0 + its
result at 0x005c73cc): Dyers asks for a spawn (rule 1 FarFromEnemies, SpawnType 0) 30x, the picker returns 0 every
time; the control gets a point on the first call. Candidates = MultiSpawnManager+0x38 list, filled by
MultiSpawnPlayerComponent::OnAddToWorld -> AddSpawnPoint, i.e. only when the entity is actually added to the world.

The objects remap_layers moved into Cell00084 / gamemode_teamwanted were only *referenced* there; they still lived in
the ACR layer entries (DataBlock_ACFE_Wanted/Corruption/...), which nothing loads -> never added -> no spawn point.
Retail: every activated object of a block lives in the block's own entry (Alhambra: 3017/3017). `materialize_moves()`
copies moved objects (+ the same-entry objects they reference) into the target block's entry and merges the source
entries' deps; `blockcheck.py` verifies (ours now 2958/2958 own entry).

## Test 9: Dyers loads and plays (Wanted). Escort (TeamVIP) navigation

ACB: Escort paths come from AdditionalWorldData_TeamVIP, looked up per (world id, mode 7) in the skins DLCs' table
(Alhambra -> 0x4fd987d9; mode 2 chest 0x4fd98273; mode 6 Assassinate 0x239e1b54 = just a VIPHighReactionPack ref,
map-independent). The object is loaded by id via LoadOnDemandManager, which probes sources in this order (from the
lookup trace): DataPC_extra -> the map forge -> skins_0002 -> Pienza -> skins_0001 -> MtStMichel -> skins_0000 ->
DataPC. So an entry with the same id in OUR forge overrides the skins copy -- no skins forge needs touching.
`override_slot_world_data()` ships Dyers' World.TeamVIPPaths (same types in both games: TeamVIPNavflowPath ->
TeamVIPNavflowPathNode{NavFlow handle, IsSpawnPoint, IsCheckpoint}; 4 paths / 54 nodes, all NavFlow targets are
Dyers CrowdFlow/NavFlow entities active in loaded cells) as entry 0x4fd987d9, shaped like retail (1 object, no deps).
Retail gamemode_teamvip layers are empty -- nothing else needed.
Escort confirmed working in-game.

Chest Capture (mode 2, Alhambra id 0x4fd98273): retail's AdditionalWorldData_ChestCapture.chestSpawnPoints refs the
map's SpawnType-3 MultiSpawnPlayerComponent entities (Multi_Chest_01..18, gamemode_teamwanted layer) and its entry
carries copies of them with the SAME ids (18/18 also in the map forge), no deps. Dyers' equivalents: the 16 type-3
Chest_Spawn* entities remap_layers moved into gamemode_teamwanted. `override_slot_world_data()` ships entry
0x4fd98273 = AWD + those 16 entities, same layout.
Test: chests loaded from OUR entry (trace: 0x4fd98273 found in the map forge) but no capture zones. Consumer:
GBrick_PickupObjectManager::NotifyWorldLoaded (Mac 0xf4ab46) World::AddEntity()s every chestSpawnPoints entity; the
zone itself is the global FX AC2MP_Zone_Chest (-> entity AC2MP_CaptureZone, skins CoreFX table). Retail's AWD copies
are NOT plain copies of the map twins: they differ in exactly IsPhantom=1 and component Ptr status 0 + flag 1 (map:
status 4 + flag 0) -- that transform reproduces all 18 Alhambra AWD copies byte for byte. Ours were plain copies;
now transformed the same way.

## If the in-game test fails

1. Crash while loading: rerun convert.py with `--remap-acfe-templates` (ACR shaders are the top suspect), then
   try dropping the 4 kept ACR FX / TOD controller.
2. Falling through geometry / no collision: MOPP code -- fixed, see "Collision: let ACB rebuild every MOPP".
3. Black/garbled textures: MctCompressionEnabled=0 path.
4. NPCs/crowd missing or stuck: NavMeshManager (kept ACR bytes).
5. No spawns / instant OOB: layer remap (report lists what went where).

## Separate (non-DLC) map entry -- investigation (2026-10-01)

How the game finds maps (Mac symbols):
- Map list = `MapManagerMulti` UnlockableMaps (+0x40, comes from the CXB `mapmanagermulti.xml`, which defines each
  `MpWorld` inline: World handle, TimeOfDay, name/description OasisLineIDs, TopViewImg/PreviewImg) plus DLC maps
  (+0x48) added at runtime by `MpWorldDLCElement::OnPackagesLoaded` -> `MapManagerMulti::AddDLCMap` (skipped if an
  existing UnlockableMap already points at that MpWorld). That's why Alhambra/Pienza/MSM aren't in the CXB XML.
- DLC forges: `ContentLoadingThread::ScanDefaultDevice` globs `game:multi/DataPC*_dlc.forge` ->
  `LoadPackagesFromForgeFile`; `MpWorldDLCElement::OnPackageLoaded` adds the forge as a LoadOnDemand source.
- Non-DLC worlds: `World::GetWorldAlternateSourcePrefixName(worldId)` -> `"_" + GameBootstrap::GetObjectName(worldId)`
  (truncated to 19 chars) -> file `multi/DataPC_<name>.forge`. GetObjectName searches `GameBootstrap.LoadInfo`
  (DataPC.forge "Game Bootstrap Settings", 1271 {FileName, ObjectID, FileClassID}); unknown id -> "Unknown".
- `OnlineMenuController::CreateUnlockedMapList` hides maps whose forge file doesn't exist (CheckWorldExists ->
  AlternateSourceExistsForWorld), so players without the file just don't see the map.
- Base-map menu images (TopViewImg = AC2MP_LoadingScreen_*_DiffuseMap, PreviewImg = ac2mp_img_*) live in
  DataPC_extra.forge; the map forge isn't mounted at menu time, so a base map can't carry its own images.
- Base map forge = DLC map forge minus DLCPackageDescriptor, MpWorld_* (+images), MpMapsDLCAddon.

World-id keyed data a new world lacks:
- Chest/Escort: `OnlineMenuController::GetAdditionalWorldData(world, mode)` only searches the table at
  OnlineMenuController+0x5950 ({worldId, [{mode, handle}]}, 12-byte rows), filled once from the first loaded
  AdditionalWorldDataDLCElement (skins DLC descriptors -- they cover base maps too, e.g. SanMarco 0x48069cd7).
  No World-level fallback in ACB. -> need a row for Dyers: edit the 3 skins descriptors, or an acb2 hook.
- AssassinSoundSettings (DataPC) has per-world entries (Alhambra, SanMarco, ...); a new world gets defaults.
- Name string: UnlockableMap/MpWorld use OasisLineIDs; ACB has no "Dyers" line -> reuse one or hook.

Ways to get a forge name for Dyers' World without DLC:
1. Reuse an unused LoadInfo World (only referenced there, nowhere else in DataPC/extra/skins), e.g.
   AC2MP_ludotest 0xdff24c44 -> renumber Dyers' World to it, ship `DataPC_AC2MP_ludotest.forge`. No DataPC edit.
2. Add {AC2MP_Dyers, 0x3ba8d804, World} to LoadInfo (DataPC.forge repack; anvilforge multi-FileSet repack untested).
3. acb2 hook on GetWorldAlternateSourcePrefixName / GetObjectName.

Draft CXB entry for option 1 (ids 0xd7e50010/11 unused in ACB + the XML; names/images borrowed until we have our
own): add `<UnlockableUnlockCondition>` (UnlockableRef 3622109200, UnlockConditionLevel 1) and a ReferenceList
`<UnlockableMap>` objID 3622109200 with MpWorld objID 3622109201, World 3757198404, TimeOfDay 12.0; bump both
Array_Size attributes.

## Base (non-DLC) map build -- `convert.py --base AC2MP_ludotest`

Chosen route (players all get the edited forge files): Dyers' World takes the id of an unused LoadInfo world,
AC2MP_ludotest (0xdff24c44; referenced nowhere but LoadInfo), so the game loads it from
`multi/DataPC_AC2MP_ludotest.forge`. `bootstrap_worlds.json` (from `bootstrap_worlds.py DataPC.forge`) maps names -> ids.

    python3 convert.py <Dyers forge> <retail ACB multi> out/base/DataPC_AC2MP_ludotest.forge --base AC2MP_ludotest --remap-acfe-templates
    python3 menu_assets.py <Dyers forge> <retail ACB multi> out/base/menu
    python3 patch_skins.py <INSTALLED multi> out/base/skins --awd out/base/DataPC_AC2MP_ludotest.forge.awd --menu out/base/menu
    python3 verify_base.py out/base/DataPC_AC2MP_ludotest.forge out/base/skins out/base/menu <server cfg>/mapmanagermulti.xml
    ./base_test.sh install          # + cxb_dyers_entry.xml in the CXB's mapmanagermulti.xml (done, uncommitted there)

- register_base: no ContentPackage/MpWorld/DLC addons, DLCWorldComponent removed (base Worlds have none), World
  renamed + renumbered; donor base map (default San Marco) gives the sound bank id, the MP message scene and the MetaFile.
- World data: retail keeps every map's AdditionalWorldData as dependency-free entries in skins_0001 (modes 2/7) and
  skins_0002 (2/7/6), each with an 11-world holder table. convert.py writes Dyers' Chest/Escort entries under fresh
  ids to `<out>.awd/` + awd.json; patch_skins.py --awd adds them to both forges plus a holder copied from the donor's
  (mode 6 Assassinate stays on the donor's data). Use the installed skins as input: the game folder's skins_0002 is a
  community edit (differs from vbox retail). Untouched round trip of both skins forges is content-identical.
- Menu entry: `cxb_dyers_entry.xml`; its strings/images live in skins_0001 (below).
- Login failures 13:10-13:26 were server-side (identical files failed then worked; A/B CXBs + skins variants).
- Test 1 (base build, San Marco strings/images): map loads; Chest Capture: chests visible, zones still missing,
  can't capture (same as the slot build) -- parked, lower priority.

## Showing Dyers as Dyers (menu_assets.py + patch_skins.py --menu)

- Strings: `LocalizationManager::GetLocalizedString` walks the loaded LocalizationCollections in priority order
  (AddLocalizationCollection sorts by +0x2c; skins DLC packages register theirs in
  CharacterSkinsDLCElement::OnPackageLoaded) and per collection the text/subtitle/e-manual package;
  `LocalizationPackage::GetLocalizedStringRaw` binary-searches the plain `LocalizedData` array (LocalizedString
  {TextID u32, Text LSTRING}) before the compressed blob. Retail leaves LocalizedData empty everywhere, so new
  lines go there: 9000001 "DYERS" (ACR's own name, line 338599 / TempString in ACR's UnlockableMap "Map Dyers"),
  9000002 a description (ACR has none), English text in all 16 text (Type 0) packages of skins_0001 AND skins_0002:
  `LocalizationManager::CleanUpCollections` keeps only the highest-priority collection (skins_0002 = 14 > skins_0001 =
  12 > skins_0000 = 11; each a full copy of the text), so lines only in skins_0001 were never shown (in-game test).
  Encoding checked against LocalizationPackage::FastLoad: count, then per element id(4) + class hash(4) + TextID +
  u32 len + UTF-16 incl. NUL.
- Images: ACR's MpWorld_Dyers uses placeholders (TopViewImg = Rome loading screen, PreviewImg = Knight Hospital);
  the real art is Dyers_MapDesc / Dyers_alternative_MapDesc in the ACR DLC forge (512x512 DXT1, full mips).
  ACB wants PreviewImg 512x256 DXT1 (ac2mp_img_*) and TopViewImg 1024x512 DXT1 (AC2MP_LoadingScreen_*), both 1 mip,
  UI textures stored upside down in both games. menu_assets.py crops 2:1, re-encodes with Pillow, and wraps them in
  copies of San Marco's / Venice's entries (fresh ids 0xdff35000 / 0xdff35041; only id fields differ from the
  templates). They go into skins_0001 (a LoadOnDemand source via CharacterSkinsDLCElement::OnPackageLoaded) --
  the map forge isn't mounted in the menu.

## All ACR-only maps: build_maps.py (supersedes the Dyers-only base_test.sh / verify_base.py / cxb_dyers_entry.xml)

    python3 build_maps.py [map ...] [--rebuild]   # convert + checks, menu assets, skins, CXB XML, verify
    ./install_maps.sh install | uninstall | status
    # then rebuild the CXB from the server cfg: CXBTool convert <xml dir> gamesettings_c1380_d873_s6285.cxb

- `maps.json`: per ACR map its forge, LoadInfo slot (all verified unreferenced outside LoadInfo in DataPC/extra/
  extraparams/skins), menu variants (ACR name line, optional English description, TimeOfDay, preview/loading image
  source + crop). `index` fixes every id: lines 9000000+100*i+2*v+1/+2, CXB objIDs 0xd7e50010+0x10*i+2*v(+1), images
  slot+0x10400+0x100*v(+0x80 loading), world data slot+0x10000.. -- never reorder.
- ACR-only maps (ACR line / English name): Antioch 334842 ANTIOCH, Constantinople 334844 GALATA, Jerusalem(dlc)
  334843 JERUSALEM, Juderia 334845 IPPOKRATOUS, Rhodes 334731 KNIGHTS HOSPITAL, Souk 334846 SOUK, Dyers(dlc) 338599
  DYERS, Imperial(dlc) 338597 IMPERIAL; night/dusk variants 334848-334854 (same World, TimeOfDay 0/18, hidden like
  ACB's night maps). ACR has no descriptions for them; maps.json carries our own English ones. Names come in 15 languages from ACR's DataPC_localization.forge.
- `locdecode.py`: CompressedLocalizationData reader (port of DecodeHeader/GetLocalizedStringRaw; pair-table codes,
  big-endian block index + per-block id tables). Matches the AnvilToolkit export of ACB English 10695/10703 (the
  rest differ only in \r\n vs \r).
- Art: <Map>_MapDesc / <Map>_Alternative_MapDesc (512x512 DXT1) in ACR DataPC_extra (base maps) or the map forge
  (DLC maps); ACR's own MpWorlds for Dyers/Imperial point at placeholders.
- `cxb_maps.py` edits mapmanagermulti.xml idempotently (only entries in the reserved objID range are replaced).

## Collision: let ACB rebuild every MOPP (2026-10-01)

In-game: Souk -- fell through the map at spawn; Knights Hospital -- many buildings walk/jump-through (and looked
low-detail); Ippokratous -- both. Not streaming: Souk's ground (ACFE_RHO_Souk_Ground_*) is in the always-loaded top
cell next to the spawn points that did work, and the data was complete (every spawn has collision under it, every
RigidBody.Shape resolves to an in-forge MeshShape, sizes within ACB's own). Ruled out on the way: the 6-level grid
of Souk/Rhodes/Juderia (one shared 1 km ACR world, GridDimensionLevel0 32; ACB's GridLayout/GridPartition/
GridLoadingAdvisor/FakeEntities code is fully generic, LoadingRangeTable/FakeCellIndex (Morton) match), data layers
(these 3 maps keep everything in grid cells), Havok broadphase (fixed +-5000 x +-500 m), id collisions, cell sizes.

Cause: `scimitar::MeshShape::UpdateSDKObject` (Mac 0x55cb60; ACBMP.exe FUN_016b3c40, VA 0x016b3c40) uses the stored
MOPP only if `MoppCode` is non-empty AND `MoppCodeVersionNumber == 5`; otherwise it rebuilds it from the triangles
with hkpMoppUtility::buildCode (tolerance 0.01) and sets the version to 5. convert.py used to stamp 5 on every ACR
shape (the field is ACB-only), so ACB ran ACR-compiled MOPPs. convert.patch_fields now writes 0 -> ACB compiles
its own at load for every ported MeshShape (only MeshShape stores a MOPP; Box/Sphere shapes have none).
verify_maps.py flags any ported MeshShape left at 5.

## Layer filters ACB can't resolve load in EVERY mode (2026-10-01)

Retest after the MOPP fix: Souk still "spawned in the middle with a dying animation" on every spawn. Runtime check
(gdb dprintf on MeshShape::UpdateSDKObject, ACBMP.exe 0x016b3c40, + /proc/<pid>/fd forge list) showed Souk's forge
loading and all its top-cell ground shapes built -> not collision. Cause: `DataLayerFilter::ShouldAssociatedObject
BeLoaded` (Mac 0x1df270) skips LayerActions whose layer handle doesn't resolve; a filter with no resolvable layer
returns "load" (Action 0 = load while layer active, else unload while active). Souk/Rhodes/Juderia are one shared ACR
world: entities are filtered on `Rhodes_<Map>_<Mode>` layers (+ unknown ids for other maps), none of which exist in
ACB, and convert.py only remapped `ACFE_<Mode>` layers listed in the WDLM. So Knights Hospital's OOB volume (in
Souk's top cell, filtered on two unknown layers) was live in Souk -> instant out-of-bounds death. The other maps had
the same leak for Deathmatch/CTF/Hijack objects sitting in loaded cells (DM OOBs, DM spawns).

Fix (remap_layers, entity filters): every LayerAction whose layer is not a DataLayer in ACB's DataPC.forge is
classified by name suffix (layer_mode): standard modes -> filter cleared; Chest_Capture -> gamemode_teamwanted;
anything else -> Action 0 on `Test_AI_Detection` (DataLayer 0xc1bd0eeb, never active in MP) = never loaded.
Souk after the fix: Hospital + DM OOB never, Souk OOB always, 21 FFA + 16 team spawns always, CTF/Hijack/DM spawns
never, 11 chest spawns on gamemode_teamwanted. verify_maps.py flags objects filtered only on unresolvable layers.
