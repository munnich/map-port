#!/usr/bin/env bash
# Swap the converted Dyers map into ACB's Alhambra DLC slot for testing, or
# put the original back.
#
#   ./slot_test.sh install   [ACB_MULTI_DIR]
#   ./slot_test.sh uninstall [ACB_MULTI_DIR]
#   ./slot_test.sh status    [ACB_MULTI_DIR]
#
# In-game: pick "Alhambra" (day or night) in a match -- it loads Dyers.
# Every player in the lobby needs the same file, or the session will desync.
set -euo pipefail

ACTION="${1:-status}"
DEFAULT_MULTI="/home/a/vbox/Assassin's Creed Brotherhood/multi"
MULTI="${2:-$DEFAULT_MULTI}"
HERE="$(cd "$(dirname "$0")" && pwd)"
NAME="DataPC_AC2MP_Alhambra_dlc.forge"
TARGET="$MULTI/$NAME"
BACKUP="$MULTI/Backups/$NAME.orig"
PORTED="$HERE/out/$NAME"
ORIG_MD5="b77f50eccfcac5fb785464350c8a7fba"  # retail Alhambra forge in this install

md5() { md5sum "$1" | cut -d' ' -f1; }

case "$ACTION" in
  install)
    [ -f "$PORTED" ] || { echo "no converted forge at $PORTED (run convert.py first)"; exit 1; }
    mkdir -p "$MULTI/Backups"
    if [ ! -f "$BACKUP" ]; then
      [ "$(md5 "$TARGET")" = "$ORIG_MD5" ] || { echo "refusing: $TARGET is not the known original Alhambra forge and no backup exists"; exit 1; }
      cp -p "$TARGET" "$BACKUP"
      echo "backed up original -> $BACKUP"
    fi
    cp "$PORTED" "$TARGET"
    echo "installed Dyers into the Alhambra slot ($(md5 "$TARGET"))"
    ;;
  uninstall)
    [ -f "$BACKUP" ] || { echo "no backup at $BACKUP"; exit 1; }
    cp -p "$BACKUP" "$TARGET"
    echo "restored original Alhambra ($(md5 "$TARGET"))"
    ;;
  status)
    cur="$(md5 "$TARGET")"
    if [ "$cur" = "$ORIG_MD5" ]; then echo "Alhambra slot: original"
    elif [ -f "$PORTED" ] && [ "$cur" = "$(md5 "$PORTED")" ]; then echo "Alhambra slot: ported Dyers"
    else echo "Alhambra slot: unknown file ($cur)"; fi
    [ -f "$BACKUP" ] && echo "backup: $BACKUP" || echo "backup: none yet"
    ;;
  *) echo "usage: $0 install|uninstall|status [ACB_MULTI_DIR]"; exit 1 ;;
esac
