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

## If the in-game test fails

1. Crash while loading: rerun convert.py with `--remap-acfe-templates` (ACR shaders are the top suspect), then
   try dropping the 4 kept ACR FX / TOD controller.
2. Falling through geometry / no collision: MOPP code; rebuild via ACBMP's Havok compiler.
3. Black/garbled textures: MctCompressionEnabled=0 path.
4. NPCs/crowd missing or stuck: NavMeshManager (kept ACR bytes).
5. No spawns / instant OOB: layer remap (report lists what went where).
