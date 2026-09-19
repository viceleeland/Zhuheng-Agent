#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
RUNTIME_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
source "$RUNTIME_DIR/common.sh"

backup_cleanup() {
  local result=$?
  trap - EXIT INT TERM
  if [[ -n ${BACKUP_PART:-} && -f $BACKUP_PART && ! -L $BACKUP_PART ]]; then
    if ! rm -f -- "$BACKUP_PART"; then result=1; fi
  fi
  if ! resume_instance; then result=1; fi
  (( result == 0 )) || printf 'Backup failed. No successful-backup status was recorded.\n' >&2
  exit "$result"
}

create_backup() {
  require_marker
  local keep archive basename metadata
  keep=$(env_value BACKUP_KEEP)
  [[ $keep =~ ^[1-9][0-9]{0,2}$ ]] || fail 'BACKUP_KEEP must be 1-999.'
  install -d -m 0700 -- "$BACKUP_DIR"
  [[ $(stat -c %u -- "$BACKUP_DIR") == 0 ]] || fail 'BACKUP_DIR must be owned by root.'
  chmod 0700 -- "$BACKUP_DIR"
  basename="jiangqing-${PROJECT}-$(date -u +%Y%m%dT%H%M%SZ)-data.tar.gz"
  archive="$BACKUP_DIR/$basename"
  [[ ! -e $archive && ! -e $archive.partial && ! -L $archive.partial ]] || fail 'Backup filename already exists.'
  BACKUP_PART="$archive.partial"
  trap backup_cleanup EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  quiesce_instance
  printf 'All writers stopped; copying persistent data.\n'
  tar --acls --xattrs --numeric-owner --exclude='./legacy-saves/.storage-migration-quiesced' \
    -C "$DATA_DIR" -czf "$BACKUP_PART" .
  resume_instance
  python3 "$RUNTIME_DIR/archive-check.py" "$BACKUP_PART"
  metadata="$archive.meta"
  [[ ! -e $metadata && ! -L $metadata && ! -e $archive.sha256 && ! -L $archive.sha256 ]] || fail 'Backup sidecar already exists.'
  {
    printf 'format=jiangqing-cold-backup-v1\nproject=%s\nfingerprint=%s\n' "$PROJECT" "$(config_fingerprint)"
    printf 'created_utc=%s\n' "$(date -u +%FT%TZ)"
    printf 'env_included=false\n'
    local ids id
    ids=$(dk ps -aq --filter "label=com.docker.compose.project=$PROJECT")
    for id in $ids; do dk inspect --format 'image={{.Config.Image}} {{.Image}}' "$id"; done
  } >"$metadata"
  mv -- "$BACKUP_PART" "$archive"
  BACKUP_PART=
  (cd -- "$BACKUP_DIR" && sha256sum "$basename" "$basename.meta" >"$basename.sha256")
  chmod 0600 -- "$archive" "$metadata" "$archive.sha256"
  (cd -- "$BACKUP_DIR" && sha256sum --check --strict --status "$basename.sha256")
  trap - EXIT INT TERM
  # Only complete, recognizable backup triplets are eligible for retention.
  python3 - "$BACKUP_DIR" "$PROJECT" "$keep" <<'PY'
import pathlib, re, sys
root, project, keep = pathlib.Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
pattern = re.compile(r"jiangqing-" + re.escape(project) + r"-\d{8}T\d{6}Z-data\.tar\.gz")
eligible = []
for archive in root.iterdir():
    if not pattern.fullmatch(archive.name):
        continue
    files = [archive, pathlib.Path(str(archive) + ".meta"), pathlib.Path(str(archive) + ".sha256")]
    if not all(p.is_file() and not p.is_symlink() and p.stat().st_uid == 0 for p in files):
        continue
    header = files[1].read_text().splitlines()[:2]
    if header == ["format=jiangqing-cold-backup-v1", "project=" + project]:
        eligible.append(files)
for files in sorted(eligible, key=lambda group: group[0].name, reverse=True)[keep:]:
    for path in files:
        path.unlink()
PY
  LAST_BACKUP=$archive
  printf 'Backup complete: %s\nKeep its .meta and .sha256 companions. Store the matching .env separately and securely.\n' "$archive"
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
  [[ $# -le 1 ]] || fail 'Usage: sudo bash backup.sh [ENV_FILE]'
  require_host
  load_context "${1:-$RUNTIME_DIR/.env}"
  lock_instance
  create_backup
fi
