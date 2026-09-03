#!/bin/bash
set -euo pipefail

TITLE="A.C.E. Recovery Updater 1.7.2"
REPO_RAW="https://raw.githubusercontent.com/LGBerlin/Ace-updating-versions-/main"
BUNDLE_ID="local.ace.app"
TARGET_VERSION="1.7.2"

say_line() { printf '%s\n' "$*"; }

fail() {
  say_line ""
  say_line "ERROR: $*"
  say_line ""
  read -r -p "Press Return to close..." _ || true
  exit 1
}

sha256_file() {
  /usr/bin/shasum -a 256 "$1" | /usr/bin/awk '{print $1}'
}

plist_value() {
  /usr/libexec/PlistBuddy -c "Print :$2" "$1" 2>/dev/null || true
}

is_ace_app() {
  local app="$1"
  [ -d "$app/Contents" ] || return 1
  [ -f "$app/Contents/Info.plist" ] || return 1
  [ "$(plist_value "$app/Contents/Info.plist" CFBundleIdentifier)" = "$BUNDLE_ID" ]
}

find_app() {
  local candidate=""
  if [ -n "${ACE_APP:-}" ] && is_ace_app "$ACE_APP"; then printf '%s' "$ACE_APP"; return 0; fi
  for candidate in "/Applications/A.C.E.app" "$HOME/Applications/A.C.E.app"; do
    if is_ace_app "$candidate"; then printf '%s' "$candidate"; return 0; fi
  done
  while IFS= read -r candidate; do
    if [ -n "$candidate" ] && is_ace_app "$candidate"; then printf '%s' "$candidate"; return 0; fi
  done < <(/usr/bin/mdfind "kMDItemCFBundleIdentifier == '$BUNDLE_ID'" 2>/dev/null || true)
  return 1
}

clear
say_line "$TITLE"
say_line "================================"
say_line ""
APP="$(find_app || true)"
[ -n "$APP" ] || fail "Could not find A.C.E. automatically. Put A.C.E.app in /Applications and run this again."
CURRENT_VERSION="$(plist_value "$APP/Contents/Info.plist" CFBundleShortVersionString)"
say_line "Found: $APP"
say_line "Installed version: ${CURRENT_VERSION:-unknown}"
say_line ""
case "$CURRENT_VERSION" in 1.7.0|1.7.1|1.7.2) ;; *) fail "This recovery updater is intended for A.C.E. 1.7.0–1.7.2. Found version '${CURRENT_VERSION:-unknown}'." ;; esac
RES="$APP/Contents/Resources"
[ -d "$RES" ] || fail "A.C.E. Resources folder is missing."
[ -w "$RES" ] || fail "A.C.E. is not writable by this account. Move A.C.E.app to your Applications folder as your user and try again."
[ -w "$APP/Contents" ] || fail "A.C.E. Contents folder is not writable by this account."
TMP="$(/usr/bin/mktemp -d -t ace-recovery-172.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT
BACKUP_ROOT="$HOME/Library/Application Support/A.C.E./Recovery Backups"
STAMP="$(/bin/date '+%Y%m%d-%H%M%S')"
BACKUP="$BACKUP_ROOT/$STAMP"
mkdir -p "$BACKUP/Contents/Resources"
say_line "Backing up the current A.C.E. files..."
for f in "Contents/Resources/ACE Base 1.6.4.py" "Contents/Resources/ACE Base 1.6.5.py" "Contents/Resources/ACE Bootstrap.py" "Contents/Info.plist"; do
  if [ -f "$APP/$f" ]; then mkdir -p "$BACKUP/$(dirname "$f")"; /bin/cp -p "$APP/$f" "$BACKUP/$f"; fi
done

download_and_verify() {
  local url="$1" out="$2" expected="$3"
  /usr/bin/curl --fail --location --silent --show-error --connect-timeout 12 --max-time 60 "$url" -o "$out" || fail "Could not download $(basename "$out"). Check the Mac's internet connection."
  local actual; actual="$(sha256_file "$out")"
  [ "$actual" = "$expected" ] || fail "Integrity check failed for $(basename "$out"). Expected $expected but received $actual."
}

say_line "Downloading verified 1.7.2 recovery files..."
download_and_verify "$REPO_RAW/updates/1.6.4/Contents/Resources/ACE%20Bootstrap%201.6.4%20integration.py" "$TMP/ACE Base 1.6.4.py" "427160fe296b276f6116061fb8768c73690342b194f178d84e15e73e134ef17a"
download_and_verify "$REPO_RAW/updates/1.6.5/Contents/Resources/ACE%20Bootstrap%201.6.5%20attachments.py" "$TMP/ACE Base 1.6.5.py" "05080748a60577087bb3f690e7fe8a07178ce50d876a5736a51eb093fccbc91a"
download_and_verify "$REPO_RAW/updates/1.7.2/Contents/Resources/ACE%20Bootstrap%201.7.2%20stabilization.py" "$TMP/ACE Bootstrap.py" "2e54fbea6b2a9ef7a999bac2786d0f2def2955a4b9f7046b3699cbc7a16073e5"
download_and_verify "$REPO_RAW/updates/1.7.2/Contents/Info.plist" "$TMP/Info.plist" "d045cb85437a94f31c9edeba800947732539b420a75140fe46e55b8c2ab04c57"
DOWNLOADED_VERSION="$(plist_value "$TMP/Info.plist" CFBundleShortVersionString)"
[ "$DOWNLOADED_VERSION" = "$TARGET_VERSION" ] || fail "Downloaded Info.plist does not identify itself as A.C.E. $TARGET_VERSION."
say_line "Closing A.C.E. if it is running..."
/usr/bin/osascript -e 'tell application id "local.ace.app" to quit' >/dev/null 2>&1 || true
/bin/sleep 2
restore_backup() {
  say_line "Restoring the pre-recovery backup..."
  for f in "Contents/Resources/ACE Base 1.6.4.py" "Contents/Resources/ACE Base 1.6.5.py" "Contents/Resources/ACE Bootstrap.py" "Contents/Info.plist"; do
    if [ -f "$BACKUP/$f" ]; then /bin/cp -p "$BACKUP/$f" "$APP/$f" || true; fi
  done
}
say_line "Installing A.C.E. $TARGET_VERSION..."
if ! /bin/cp "$TMP/ACE Base 1.6.4.py" "$RES/ACE Base 1.6.4.py" || ! /bin/cp "$TMP/ACE Base 1.6.5.py" "$RES/ACE Base 1.6.5.py" || ! /bin/cp "$TMP/ACE Bootstrap.py" "$RES/ACE Bootstrap.py" || ! /bin/cp "$TMP/Info.plist" "$APP/Contents/Info.plist"; then restore_backup; fail "Installation failed. The original files were restored."; fi
/bin/chmod 644 "$RES/ACE Base 1.6.4.py" "$RES/ACE Base 1.6.5.py" "$RES/ACE Bootstrap.py" "$APP/Contents/Info.plist" || true
[ -d "$RES/__pycache__" ] && /bin/rm -rf "$RES/__pycache__" || true
verify_installed() { local file="$1" expected="$2" actual; actual="$(sha256_file "$file")"; [ "$actual" = "$expected" ]; }
if ! verify_installed "$RES/ACE Base 1.6.4.py" "427160fe296b276f6116061fb8768c73690342b194f178d84e15e73e134ef17a" || ! verify_installed "$RES/ACE Base 1.6.5.py" "05080748a60577087bb3f690e7fe8a07178ce50d876a5736a51eb093fccbc91a" || ! verify_installed "$RES/ACE Bootstrap.py" "2e54fbea6b2a9ef7a999bac2786d0f2def2955a4b9f7046b3699cbc7a16073e5" || ! verify_installed "$APP/Contents/Info.plist" "d045cb85437a94f31c9edeba800947732539b420a75140fe46e55b8c2ab04c57"; then restore_backup; fail "Installed-file verification failed. The original files were restored."; fi
FINAL_VERSION="$(plist_value "$APP/Contents/Info.plist" CFBundleShortVersionString)"
[ "$FINAL_VERSION" = "$TARGET_VERSION" ] || { restore_backup; fail "A.C.E. did not verify as version $TARGET_VERSION after installation."; }
touch "$APP" || true
say_line ""
say_line "Recovery complete. A.C.E. is now $FINAL_VERSION."
say_line "Backup saved at:"
say_line "$BACKUP"
say_line ""
say_line "Opening A.C.E..."
/usr/bin/open "$APP"
say_line ""
say_line "You can close this Terminal window."
