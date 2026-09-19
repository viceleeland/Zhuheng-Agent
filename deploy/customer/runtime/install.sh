#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
RUNTIME_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
source "$RUNTIME_DIR/backup.sh"

[[ $# -le 2 ]] || fail 'Usage: sudo bash install.sh {init|check|install|upgrade} [ENV_FILE]'
action=${1:-check}
ENV_FILE=${2:-$RUNTIME_DIR/.env}
[[ $action =~ ^(init|check|install|upgrade)$ ]] || fail 'Unknown action.'
require_host

prompt_admin() {
  [[ -t 0 ]] || fail 'Administrator initialization requires an interactive terminal; rerun upgrade from a terminal.'
  read -r -p 'Initial administrator ID (3-20 letters/digits/underscores): ' admin_uid
  [[ $admin_uid =~ ^[a-zA-Z0-9_]{3,20}$ ]] || fail 'Invalid administrator ID.'
  read -r -s -p 'Initial administrator password (at least 12 characters): ' admin_password
  printf '\n'
  read -r -s -p 'Repeat administrator password: ' admin_repeat
  printf '\n'
  [[ ${#admin_password} -ge 12 && $admin_password == "$admin_repeat" ]] || fail 'Administrator passwords do not match or are too short.'
  unset admin_repeat
}

if [[ $action == init ]]; then
  [[ $ENV_FILE == /* ]] || ENV_FILE="$PWD/$ENV_FILE"
  safe_path "$ENV_FILE"
  [[ ! -e $ENV_FILE && ! -L $ENV_FILE ]] || fail 'Refusing to overwrite existing configuration.'
  [[ -d $(dirname -- "$ENV_FILE") ]] || fail 'Create the configuration parent directory first.'
  verify_bundle
  python3 - "$RUNTIME_DIR/.env.example" "$ENV_FILE" <<'PY'
import os, pathlib, secrets, sys
template = pathlib.Path(sys.argv[1]).read_text()
values = {key: secrets.token_hex(32) for key in (
    "JWT_SECRET_KEY", "API_KEY_DERIVATION_SECRET", "SANDBOX_PROVISIONER_TOKEN",
    "POSTGRES_PASSWORD", "NEO4J_PASSWORD", "MINIO_SECRET_KEY",
)}
values["MINIO_ACCESS_KEY"] = secrets.token_hex(12)
values["YUXI_INSTANCE_ID"] = "customer-" + secrets.token_hex(16)
for key, value in values.items():
    template = template.replace(key + "=\n", key + "=" + value + "\n")
with os.fdopen(os.open(sys.argv[2], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as file:
    file.write(template)
PY
  printf 'Created %s with independent random secrets.\nReview paths, model credentials and browser origin, then run install.sh install.\n' "$ENV_FILE"
  exit 0
fi

load_context "$ENV_FILE"
lock_instance
verify_bundle
if [[ $action == check ]]; then
  verify_images
  printf 'Configuration, bundle checksums and local linux/amd64 images verified. No services were started.\n'
  exit 0
fi

if [[ $action == install ]]; then
  [[ -z $(dk ps -aq --filter "label=com.docker.compose.project=$PROJECT") ]] || fail 'This project already exists; use upgrade with its matching configuration.'
  [[ ! -e $DATA_DIR || -z $(find "$DATA_DIR" -mindepth 1 -maxdepth 1 -print -quit) ]] || fail 'New installation requires an empty DATA_DIR.'
  assert_data_unmounted -a
  prompt_admin
else
  require_marker
  create_backup
  printf 'Pre-upgrade backup: %s\n' "$LAST_BACKUP"
fi

for image_archive in "$PACKAGE_DIR"/images/*.tar; do dk load --input "$image_archive"; done
verify_images

if [[ $action == install ]]; then
  install -d -m 0700 -- "$DATA_DIR"
  for directory in postgres redis minio minio-config etcd milvus neo4j neo4j-logs user-data skill-sources skill-projections legacy-saves; do
    install -d -m 0755 -- "$DATA_DIR/$directory"
  done
  write_marker
fi

install_cleanup() {
  local result=$?
  trap - EXIT INT TERM
  if [[ -n ${proof_file:-} && -f $proof_file && ! -L $proof_file ]]; then
    if ! rm -f -- "$proof_file"; then result=1; fi
  fi
  if ! resume_instance; then result=1; fi
  if (( result != 0 )); then
    printf 'Installation/upgrade failed. Data was retained. Inspect logs and repair before starting services; do not delete volumes.\n' >&2
  fi
  exit "$result"
}
trap install_cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
quiesce_instance
MIGRATION_TOKEN=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
proof_file="$DATA_DIR/legacy-saves/.storage-migration-quiesced"
[[ ! -L $proof_file ]] || fail 'Migration proof must not be a symlink.'
printf '%s\n' "$MIGRATION_TOKEN" >"$proof_file"
dc up -d --no-deps --wait --wait-timeout 180 postgres
# From this command onward a schema change may have begun; keep writers stopped on failure.
NEEDS_RESUME=0
dc up --no-deps --force-recreate --abort-on-container-exit --exit-code-from storage-migrator storage-migrator
if dc run --rm --no-deps -T --volume "$RUNTIME_DIR/admin-init.py:/app/customer-admin-init.py:ro" \
  --entrypoint python api /app/customer-admin-init.py --check-initialized; then
  unset admin_password
else
  admin_status=$?
  [[ $admin_status == 3 ]] || fail 'Could not verify the initial administrator state.'
  [[ -n ${admin_password:-} ]] || prompt_admin
  printf '%s\n%s\n' "$admin_uid" "$admin_password" | dc run --rm --no-deps -T \
    --volume "$RUNTIME_DIR/admin-init.py:/app/customer-admin-init.py:ro" \
    --entrypoint python api /app/customer-admin-init.py
  unset admin_password
fi
dc up -d --wait --wait-timeout 600
dc ps
printf 'Customer instance started. Default local entry: http://127.0.0.1:5185\nUse the customer HTTPS reverse proxy for remote access and microphone capture.\n'
