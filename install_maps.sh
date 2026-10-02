#!/usr/bin/env bash
# Install the ported ACR maps (maps.json, built by build_maps.py) into the game, or remove them again.
#
#   ./install_maps.sh install     # every built out/maps/<key>/DataPC_<name>.forge, the patched skins forges (out/maps/skins)
#                                 # and DataPC.forge with the maps' LoadInfo names (out/maps/DataPC.forge, patch_bootstrap.py)
#   ./install_maps.sh uninstall   # removes those map forges, restores the skins forges + DataPC.forge saved by install
#   ./install_maps.sh status
#
# The menu entries come from the CXB (cxb_maps.py writes them into the server's mapmanagermulti.xml).
# Game folder: $ACB_MULTI, else maps.json's acb_installed. Every player needs the same files.
set -euo pipefail
ACTION="${1:-status}"
HERE="$(cd "$(dirname "$0")" && pwd)"
MULTI="${ACB_MULTI:-$(python3 -c "import json;print(json.load(open('$HERE/maps.json'))['acb_installed'])")}"
SKINS=(DataPC_skins_0001_00000002_dlc.forge DataPC_skins_0002_00000004_dlc.forge)
SAVE=".pre_dyers"   # name kept from the first (Dyers-only) installs
BOOT=DataPC.forge; BOOT_SAVE=".pre_acfe"
mapfiles() { python3 -c "
import json, sys
sys.path.insert(0, '$HERE')
from patch_bootstrap import CFG, map_name
for k, m in sorted(CFG['maps'].items(), key=lambda kv: kv[1]['index']):
    print(k, 'DataPC_%s.forge' % map_name(m), 'DataPC_%s.forge' % m['slot'][:19])"; }
md5() { md5sum "$1" | cut -d' ' -f1; }

case "$ACTION" in
  install)
    for s in "${SKINS[@]}"; do [ -f "$HERE/out/maps/skins/$s" ] || { echo "no patched $s in out/maps/skins"; exit 1; }; done
    [ -f "$HERE/out/maps/$BOOT" ] || { echo "no patched $BOOT in out/maps (patch_bootstrap.py)"; exit 1; }
    if [ ! -f "$MULTI/$BOOT$BOOT_SAVE" ]; then cp -p "$MULTI/$BOOT" "$MULTI/$BOOT$BOOT_SAVE"; echo "saved $BOOT -> $BOOT$BOOT_SAVE"; fi
    cp "$HERE/out/maps/$BOOT" "$MULTI/$BOOT.tmp" && mv "$MULTI/$BOOT.tmp" "$MULTI/$BOOT" && echo "installed $BOOT"
    for s in "${SKINS[@]}"; do
      if [ ! -f "$MULTI/$s$SAVE" ]; then cp -p "$MULTI/$s" "$MULTI/$s$SAVE"; echo "saved $s -> $s$SAVE"; fi
      cp "$HERE/out/maps/skins/$s" "$MULTI/$s"
    done
    mapfiles | while read key f old; do
      if [ -f "$HERE/out/maps/$key/$f" ]; then cp "$HERE/out/maps/$key/$f" "$MULTI/$f"; echo "installed $key as $f"
      else echo "skipped $key (not built)"; fi
      if [ "$old" != "$f" ] && [ -f "$MULTI/$old" ]; then rm "$MULTI/$old"; echo "  removed old $old"; fi
    done
    ;;
  uninstall)
    for s in "${SKINS[@]}"; do
      [ -f "$MULTI/$s$SAVE" ] || { echo "no saved $s$SAVE"; exit 1; }
      cp -p "$MULTI/$s$SAVE" "$MULTI/$s" && rm "$MULTI/$s$SAVE" && echo "restored $s"
    done
    if [ -f "$MULTI/$BOOT$BOOT_SAVE" ]; then cp -p "$MULTI/$BOOT$BOOT_SAVE" "$MULTI/$BOOT" && rm "$MULTI/$BOOT$BOOT_SAVE" && echo "restored $BOOT"; fi
    mapfiles | while read key f old; do
      for x in "$f" "$old"; do [ -f "$MULTI/$x" ] && rm "$MULTI/$x" && echo "removed $x"; done; true
    done
    ;;
  status)
    echo "game folder: $MULTI"
    mapfiles | while read key f old; do
      if [ -f "$MULTI/$f" ]; then st="installed"; [ -f "$HERE/out/maps/$key/$f" ] && { [ "$(md5 "$MULTI/$f")" = "$(md5 "$HERE/out/maps/$key/$f")" ] && st="installed (current build)" || st="installed (OLDER build)"; }
      else st="not installed"; fi
      printf '  %-18s %-36s %s\n' "$key" "$f" "$st"
    done
    for s in "${SKINS[@]}"; do
      st="original"; [ -f "$MULTI/$s$SAVE" ] && st="patched (original saved as $s$SAVE)"
      [ -f "$HERE/out/maps/skins/$s" ] && [ "$(md5 "$MULTI/$s")" = "$(md5 "$HERE/out/maps/skins/$s")" ] && st="$st, current build"
      echo "  $s: $st"
    done
    st="original"; [ -f "$MULTI/$BOOT$BOOT_SAVE" ] && st="patched (original saved as $BOOT$BOOT_SAVE)"
    [ -f "$HERE/out/maps/$BOOT" ] && [ "$(md5 "$MULTI/$BOOT")" = "$(md5 "$HERE/out/maps/$BOOT")" ] && st="$st, current build"
    echo "  $BOOT: $st"
    ;;
  *) echo "usage: $0 install | uninstall | status"; exit 1 ;;
esac
