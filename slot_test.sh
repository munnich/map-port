#!/usr/bin/env bash
# Swap a converted Dyers build into ACB's Alhambra DLC slot for testing, or put
# the original back.
#
#   ./slot_test.sh install [VARIANT]   # VARIANT = default | remap_templates (a folder under out/)
#   ./slot_test.sh uninstall
#   ./slot_test.sh status
#
# Game folder: $ACB_MULTI, else the install the `cdacb` alias points at.
# In-game: pick "Alhambra" (day or night) -- it loads Dyers. Every player in the
# lobby needs the same file, or the session will desync.
set -euo pipefail

ACTION="${1:-status}"
VARIANT="${2:-default}"
DEFAULT_MULTI="/home/a/Games/assassins-creed-brotherhood/drive_c/Program Files (x86)/Ubisoft/Ubisoft Game Launcher/games/Assassin's Creed Brotherhood/multi"
MULTI="${ACB_MULTI:-$DEFAULT_MULTI}"
HERE="$(cd "$(dirname "$0")" && pwd)"
NAME="DataPC_AC2MP_Alhambra_dlc.forge"
TARGET="$MULTI/$NAME"
BACKUP="$TARGET.bak"
ORIG_MD5="b77f50eccfcac5fb785464350c8a7fba"  # retail Alhambra forge

md5() { md5sum "$1" | cut -d' ' -f1; }
variant_path() { if [ "$1" = default ]; then echo "$HERE/out/$NAME"; else echo "$HERE/out/$1/$NAME"; fi; }

case "$ACTION" in
  install)
    PORTED="$(variant_path "$VARIANT")"
    [ -f "$PORTED" ] || { echo "no build at $PORTED"; exit 1; }
    if [ -f "$BACKUP" ]; then
      [ "$(md5 "$BACKUP")" = "$ORIG_MD5" ] || { echo "refusing: $BACKUP is not the retail Alhambra forge"; exit 1; }
    else
      [ "$(md5 "$TARGET")" = "$ORIG_MD5" ] || { echo "refusing: $TARGET is not the retail Alhambra forge and no backup exists"; exit 1; }
      cp -p "$TARGET" "$BACKUP"
      echo "backed up original -> $BACKUP"
    fi
    cp "$PORTED" "$TARGET"
    echo "installed Dyers ($VARIANT) into the Alhambra slot: $(md5 "$TARGET")"
    ;;
  uninstall)
    [ -f "$BACKUP" ] && [ "$(md5 "$BACKUP")" = "$ORIG_MD5" ] || { echo "no retail backup at $BACKUP"; exit 1; }
    cp -p "$BACKUP" "$TARGET"
    echo "restored original Alhambra: $(md5 "$TARGET")"
    ;;
  status)
    cur="$(md5 "$TARGET")"; state="unknown file ($cur)"
    [ "$cur" = "$ORIG_MD5" ] && state="original"
    for v in default remap_templates; do
      p="$(variant_path "$v")"; [ -f "$p" ] && [ "$cur" = "$(md5 "$p")" ] && state="ported Dyers ($v)"
    done
    echo "game folder: $MULTI"
    echo "Alhambra slot: $state"
    [ -f "$BACKUP" ] && echo "backup: $BACKUP" || echo "backup: none yet"
    ;;
  *) echo "usage: $0 install [default|remap_templates] | uninstall | status"; exit 1 ;;
esac
