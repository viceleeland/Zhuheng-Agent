#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
RUNTIME_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
source "$RUNTIME_DIR/common.sh"
[[ $# == 2 ]] || fail 'Usage: sudo bash restore.sh ARCHIVE ENV_FILE (new project and empty DATA_DIR only)'
archive=$1
[[ $archive == /* ]] || archive="$PWD/$archive"
require_host
safe_path "$archive"
load_context "$2"
lock_instance
verify_bundle
[[ -z $(dk ps -aq --filter "label=com.docker.compose.project=$PROJECT") ]] || fail 'Restore requires a new Compose project without existing containers.'
[[ ! -e $DATA_DIR || -z $(find "$DATA_DIR" -mindepth 1 -maxdepth 1 -print -quit) ]] || fail 'Restore refuses to overwrite existing data.'
assert_data_unmounted -a
for file in "$archive" "$archive.meta" "$archive.sha256"; do
  [[ -f $file && ! -L $file ]] || fail "Missing or symlinked backup file: $file"
done
basename=$(basename -- "$archive")
[[ $basename =~ ^jiangqing-[a-z][a-z0-9-]{2,39}-[0-9]{8}T[0-9]{6}Z-data\.tar\.gz$ ]] || fail 'Unrecognized backup filename.'
python3 - "$archive" <<'PY'
import pathlib, re, sys
archive = pathlib.Path(sys.argv[1])
lines = pathlib.Path(str(archive) + ".sha256").read_text().splitlines()
if len(lines) != 2:
    raise SystemExit("Invalid backup checksum file")
for line, name in zip(lines, [archive.name, archive.name + ".meta"]):
    if not re.fullmatch(r"[0-9a-f]{64}  " + re.escape(name), line):
        raise SystemExit("Unexpected path in backup checksum file")
PY
(cd -- "$(dirname -- "$archive")" && sha256sum --check --strict --status "$basename.sha256")
[[ $(head -n 1 -- "$archive.meta") == format=jiangqing-cold-backup-v1 ]] || fail 'Unsupported backup format.'
expected_fingerprint=$(sed -n 's/^fingerprint=//p' "$archive.meta")
[[ $expected_fingerprint == "$(config_fingerprint)" ]] || fail 'Provide the original .env security/storage credentials and YUXI_INSTANCE_ID; only change the project, paths and network settings.'

# GNU tar may preserve database ownership only after the archive passes validation.
python3 "$RUNTIME_DIR/archive-check.py" "$archive"

for image_archive in "$PACKAGE_DIR"/images/*.tar; do dk load --input "$image_archive"; done
verify_images

install -d -m 0700 -- "$DATA_DIR"
tar --acls --xattrs --numeric-owner --same-owner --keep-old-files --delay-directory-restore \
  -C "$DATA_DIR" -xzf "$archive"
[[ $(tail -n 1 -- "$DATA_DIR/.jiangqing-instance") == "$INSTANCE_ID" ]] || fail 'Restored instance ID does not match; leave the new directory stopped for inspection.'
write_marker
chmod 0700 -- "$DATA_DIR"
printf 'Data restored into %s. No service was started.\nReview the backup .meta image versions, then run:\n  sudo bash %s/install.sh upgrade %s\n' "$DATA_DIR" "$RUNTIME_DIR" "$ENV_FILE"
