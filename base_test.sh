#!/usr/bin/env bash
# Install Dyers as its own non-DLC map (World AC2MP_ludotest) next to the retail maps, or remove it again.
#
#   ./base_test.sh install     # copies out/base/DataPC_AC2MP_ludotest.forge + the patched skins forges (out/base/skins)
#   ./base_test.sh uninstall   # removes the map forge, restores the skins forges saved by install
#   ./base_test.sh status
#
# The menu entry comes from the CXB: mapmanagermulti.xml needs the UnlockableMap from cxb_dyers_entry.xml.
# Game folder: $ACB_MULTI, else the install the `cdacb` alias points at. Every player needs the same files.
set -euo pipefail

ACTION="${1:-status}"
DEFAULT_MULTI="/home/a/Games/assassins-creed-brotherhood/drive_c/Program Files (x86)/Ubisoft/Ubisoft Game Launcher/games/Assassin's Creed Brotherhood/multi"
MULTI="${ACB_MULTI:-$DEFAULT_MULTI}"
HERE="$(cd "$(dirname "$0")" && pwd)"
MAP="DataPC_AC2MP_ludotest.forge"
SKINS=(DataPC_skins_0001_00000002_dlc.forge DataPC_skins_0002_00000004_dlc.forge)
SAVE=".pre_dyers"

md5() { md5sum "$1" | cut -d' ' -f1; }

case "$ACTION" in
  install)
    [ -f "$HERE/out/base/$MAP" ] || { echo "no build at out/base/$MAP"; exit 1; }
    for s in "${SKINS[@]}"; do [ -f "$HERE/out/base/skins/$s" ] || { echo "no patched $s in out/base/skins"; exit 1; }; done
    for s in "${SKINS[@]}"; do
      if [ ! -f "$MULTI/$s$SAVE" ]; then cp -p "$MULTI/$s" "$MULTI/$s$SAVE"; echo "saved $s -> $s$SAVE"; fi
      cp "$HERE/out/base/skins/$s" "$MULTI/$s"
    done
    cp "$HERE/out/base/$MAP" "$MULTI/$MAP"
    echo "installed Dyers as $MAP: $(md5 "$MULTI/$MAP")"
    ;;
  uninstall)
    for s in "${SKINS[@]}"; do
      [ -f "$MULTI/$s$SAVE" ] || { echo "no saved $s$SAVE"; exit 1; }
      cp -p "$MULTI/$s$SAVE" "$MULTI/$s" && rm "$MULTI/$s$SAVE"
      echo "restored $s"
    done
    rm -f "$MULTI/$MAP"
    echo "removed $MAP"
    ;;
  status)
    echo "game folder: $MULTI"
    if [ -f "$MULTI/$MAP" ]; then
      st="unknown build"; [ -f "$HERE/out/base/$MAP" ] && [ "$(md5 "$MULTI/$MAP")" = "$(md5 "$HERE/out/base/$MAP")" ] && st="current build"
      echo "$MAP: installed ($st)"
    else echo "$MAP: not installed"; fi
    for s in "${SKINS[@]}"; do
      st="original"; [ -f "$MULTI/$s$SAVE" ] && st="patched (original saved as $s$SAVE)"
      echo "$s: $st"
    done
    ;;
  *) echo "usage: $0 install | uninstall | status"; exit 1 ;;
esac
