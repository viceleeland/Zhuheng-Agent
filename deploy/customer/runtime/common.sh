#!/usr/bin/env bash
# Shared Linux deployment boundaries. Source from the entry-point scripts.

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

require_host() {
  [[ $(uname -s) == Linux && $(uname -m) == x86_64 ]] || fail 'Linux x86_64 is required.'
  [[ $EUID == 0 ]] || fail 'Run with sudo on the Docker host; numeric file owners must be preserved.'
  local tool
  for tool in docker python3 sha256sum tar realpath stat flock find sort install timeout; do
    command -v "$tool" >/dev/null || fail "Missing prerequisite: $tool"
  done
  [[ -S /var/run/docker.sock ]] || fail 'A local Docker Engine socket is required.'
  dk info >/dev/null
  dk compose version >/dev/null
  dk compose up --help | grep -q -- --wait || fail 'Docker Compose v2 with --wait is required.'
}

dk() { docker --host unix:///var/run/docker.sock "$@"; }

dc() {
  # Shell variables must not silently override the reviewed customer file.
  env -i PATH="$PATH" HOME="$HOME" JIANGQING_ENV_FILE="$ENV_FILE" \
    YUXI_STORAGE_MIGRATION_QUIESCENCE_TOKEN="${MIGRATION_TOKEN:-}" \
    docker --host unix:///var/run/docker.sock compose --project-name "$PROJECT" \
    --env-file "$ENV_FILE" -f "$RUNTIME_DIR/compose.yaml" "$@"
}

safe_path() {
  local path=$1 current
  [[ $path =~ ^/[a-zA-Z0-9._/-]+$ && $path != / ]] || fail "Use an absolute path without spaces: $path"
  [[ $(realpath -m -- "$path") == "$path" ]] || fail "Path must be canonical: $path"
  case "$path" in
    /etc|/etc/*|/usr|/usr/*|/bin|/bin/*|/sbin|/sbin/*|/dev|/dev/*|/proc|/proc/*|/sys|/sys/*|/tmp|/tmp/*|/run|/run/*|/var/tmp|/var/tmp/*)
      fail "System or temporary path is not allowed: $path" ;;
  esac
  current=$path
  while [[ $current != / ]]; do
    [[ ! -L $current ]] || fail "Symlink path component is not allowed: $current"
    current=$(dirname -- "$current")
  done
}

env_value() {
  local value
  value=$(sed -n "s/^${1}=//p" "$ENV_FILE")
  [[ $value != *$'\n'* && $value != *$'\r'* ]] || fail "Duplicate or invalid .env assignment: $1"
  if [[ $value == \'*\' || $value == \"*\" ]]; then value=${value:1:${#value}-2}; fi
  [[ -n $value && $value != *'$'* && $value != *'\\'* ]] || fail "Use a nonempty literal .env value: $1"
  printf '%s' "$value"
}

load_context() {
  ENV_FILE=$1
  [[ $ENV_FILE == /* ]] || ENV_FILE="$PWD/$ENV_FILE"
  safe_path "$ENV_FILE"
  [[ -f $ENV_FILE ]] || fail "Missing configuration: $ENV_FILE (run install.sh init)."
  local mode secret other value
  mode=$(stat -c %a -- "$ENV_FILE")
  (( (8#$mode & 077) == 0 )) || fail 'Customer .env must be readable only by its owner (chmod 600).'
  [[ $(stat -c %u -- "$ENV_FILE") == 0 ]] || fail 'Customer .env must be owned by root.'
  PROJECT=$(env_value COMPOSE_PROJECT_NAME)
  [[ $PROJECT =~ ^[a-z][a-z0-9-]{2,39}$ ]] || fail 'Project name must be 3-40 lowercase letters, digits or hyphens.'
  DATA_DIR=$(env_value DATA_DIR)
  BACKUP_DIR=$(env_value BACKUP_DIR)
  INSTANCE_ID=$(env_value YUXI_INSTANCE_ID)
  [[ $INSTANCE_ID =~ ^[a-zA-Z0-9_-]{16,80}$ ]] || fail 'Invalid YUXI_INSTANCE_ID.'
  safe_path "$DATA_DIR"; safe_path "$BACKUP_DIR"
  case "$DATA_DIR" in /opt|/srv|/home|/root|/var) fail 'DATA_DIR must be a dedicated instance subdirectory.';; esac
  case "$BACKUP_DIR" in /opt|/srv|/home|/root|/var) fail 'BACKUP_DIR must be a dedicated backup subdirectory.';; esac
  [[ $BACKUP_DIR != "$DATA_DIR" && $BACKUP_DIR != "$DATA_DIR/"* && $DATA_DIR != "$BACKUP_DIR/"* ]] || fail 'Data and backup directories must not overlap.'
  [[ $ENV_FILE != "$DATA_DIR/"* ]] || fail 'Keep .env outside DATA_DIR; data backups intentionally exclude it.'
  SECURITY_KEYS=(JWT_SECRET_KEY API_KEY_DERIVATION_SECRET SANDBOX_PROVISIONER_TOKEN)
  for secret in "${SECURITY_KEYS[@]}" POSTGRES_PASSWORD NEO4J_PASSWORD MINIO_SECRET_KEY; do
    value=$(env_value "$secret")
    [[ $value =~ ^[a-zA-Z0-9_-]{32,128}$ ]] || fail "$secret must be 32-128 URL-safe literal characters."
    for other in "${SECURITY_KEYS[@]}"; do
      [[ $secret == "$other" || $value != "$(env_value "$other")" ]] || fail 'Security secrets must be independent.'
    done
  done
  value=$(env_value MINIO_ACCESS_KEY)
  [[ $value =~ ^[a-zA-Z0-9_-]{16,64}$ ]] || fail 'Invalid MINIO_ACCESS_KEY.'
  dc config --quiet
  assert_project_identity
}

lock_instance() {
  local parent
  parent=$(dirname -- "$DATA_DIR")
  if [[ ! -d $parent ]]; then install -d -m 0755 -- "$parent"; fi
  [[ ! -L $DATA_DIR.lock ]] || fail 'Instance lock must not be a symlink.'
  exec 9>>"$DATA_DIR.lock"
  flock -n 9 || fail 'Another operation holds this instance lock.'
}

assert_project_identity() {
  local ids id instance source mounts
  ids=$(dk ps -aq --filter "label=com.docker.compose.project=$PROJECT")
  for id in $ids; do
    instance=$(dk inspect --format '{{index .Config.Labels "io.jiangqing.customer.instance"}}' "$id")
    [[ $instance == "$INSTANCE_ID" ]] || fail "Compose project already belongs to another instance: $PROJECT"
    mounts=$(dk inspect --format '{{range .Mounts}}{{if eq .Type "bind"}}{{println .Source}}{{end}}{{end}}' "$id")
    while IFS= read -r source; do
      [[ -z $source || $source == /var/run/docker.sock || $source == "$DATA_DIR/"* ]] || fail "Existing project uses another bind directory: $source"
    done <<<"$mounts"
  done
}

write_marker() { printf 'jiangqing-customer-data-v1\n%s\n%s\n' "$PROJECT" "$INSTANCE_ID" >"$DATA_DIR/.jiangqing-instance"; }

require_marker() {
  [[ -f $DATA_DIR/.jiangqing-instance && ! -L $DATA_DIR/.jiangqing-instance ]] || fail 'This is not an initialized customer DATA_DIR.'
  [[ $(cat -- "$DATA_DIR/.jiangqing-instance") == "$(printf 'jiangqing-customer-data-v1\n%s\n%s' "$PROJECT" "$INSTANCE_ID")" ]] || fail 'Data marker does not match the configured instance.'
  local directory
  for directory in postgres redis minio minio-config etcd milvus neo4j neo4j-logs user-data skill-sources skill-projections legacy-saves; do
    [[ -d $DATA_DIR/$directory && ! -L $DATA_DIR/$directory ]] || fail "Missing or symlinked data directory: $directory"
  done
}

config_fingerprint() {
  local key
  for key in YUXI_INSTANCE_ID JWT_SECRET_KEY API_KEY_DERIVATION_SECRET SANDBOX_PROVISIONER_TOKEN POSTGRES_PASSWORD NEO4J_PASSWORD MINIO_ACCESS_KEY MINIO_SECRET_KEY; do
    printf '%s=%s\n' "$key" "$(env_value "$key")"
  done | sha256sum | cut -d ' ' -f 1
}

verify_bundle() {
  PACKAGE_DIR=$(dirname -- "$RUNTIME_DIR")
  [[ -f $PACKAGE_DIR/SHA256SUMS && ! -L $PACKAGE_DIR/SHA256SUMS ]] || fail 'Missing bundle SHA256SUMS.'
  python3 - "$PACKAGE_DIR" <<'PY'
import pathlib, re, sys
root = pathlib.Path(sys.argv[1])
names = set()
for line in (root / "SHA256SUMS").read_text().splitlines():
    match = re.fullmatch(r"[0-9a-f]{64} [ *]([A-Za-z0-9._/-]+)", line)
    if not match:
        raise SystemExit("Invalid SHA256SUMS entry")
    name = pathlib.PurePosixPath(match[1])
    if name.is_absolute() or ".." in name.parts or str(name) in names:
        raise SystemExit("Unsafe or duplicate manifest path")
    target = root / name
    if not target.is_file() or target.resolve() != target or target.is_symlink():
        raise SystemExit("Missing or symlinked bundle file: " + str(name))
    names.add(str(name))
for path in (root / "runtime").rglob("*"):
    if path.is_file() and path.name != ".env":
        if path.relative_to(root).as_posix() not in names:
            raise SystemExit("Unchecksummed runtime file: " + str(path))
archives = list((root / "images").glob("*.tar"))
if not archives or any(path.relative_to(root).as_posix() not in names for path in archives):
    raise SystemExit("Missing or unchecksummed offline image archive")
PY
  (cd -- "$PACKAGE_DIR" && sha256sum --check --strict --status SHA256SUMS)
  printf 'Bundle checksums verified.\n'
}

verify_images() {
  local images image platform
  images=$(dc config --images)
  images+=$'\n'"$(env_value SANDBOX_IMAGE)"
  while IFS= read -r image; do
    [[ -n $image ]] || continue
    platform=$(dk image inspect --format '{{.Os}}/{{.Architecture}}' "$image") || fail "Missing offline image: $image"
    [[ $platform == linux/amd64 ]] || fail "Wrong image platform for $image: $platform"
  done <<<"$images"
}

assert_data_unmounted() {
  local ids id source mounts
  ids=$(dk ps "$@" -q)
  for id in $ids; do
    mounts=$(dk inspect --format '{{range .Mounts}}{{if eq .Type "bind"}}{{println .Source}}{{end}}{{end}}' "$id")
    while IFS= read -r source; do
      [[ $source != "$DATA_DIR" && $source != "$DATA_DIR/"* ]] || fail "Container $id still mounts this DATA_DIR."
    done <<<"$mounts"
  done
}

ORIGINAL_SERVICES=()
ORIGINAL_CONTAINERS=()
ORIGINAL_SANDBOXES=()
NEEDS_RESUME=0

quiesce_instance() {
  local running ids id name source mounts owner
  running=$(dc ps --status running --quiet)
  ORIGINAL_SERVICES=()
  ORIGINAL_CONTAINERS=()
  for id in $running; do
    name=$(dk inspect --format '{{index .Config.Labels "com.docker.compose.service"}}' "$id")
    [[ -n $name && $name != '<no value>' ]] || fail 'Running container has no Compose service identity.'
    [[ $name != storage-migrator ]] || fail 'A storage migration is currently running.'
    ORIGINAL_SERVICES+=("$name")
    ORIGINAL_CONTAINERS+=("$id")
  done
  ORIGINAL_SANDBOXES=()
  NEEDS_RESUME=1
  dc stop --timeout 120 web api worker sandbox-provisioner
  ids=$(dk ps -q --filter "label=io.jiangqing.customer.project=$PROJECT" \
    --filter "label=io.jiangqing.customer.instance=$INSTANCE_ID" \
    --filter label=app=yuxi-sandbox --filter label=managed-by=yuxi-sandbox-provisioner)
  for id in $ids; do
    owner=$(dk inspect --format '{{index .Config.Labels "io.jiangqing.customer.project"}} {{index .Config.Labels "io.jiangqing.customer.instance"}}' "$id")
    [[ $owner == "$PROJECT $INSTANCE_ID" ]] || fail 'Sandbox does not belong to this customer instance.'
    name=$(dk inspect --format '{{.Name}}' "$id")
    [[ $name == "/$PROJECT-sandbox-"* ]] || fail 'Unexpected sandbox name.'
    mounts=$(dk inspect --format '{{range .Mounts}}{{if eq .Type "bind"}}{{println .Source}}{{end}}{{end}}' "$id")
    while IFS= read -r source; do
      [[ -z $source || $source == "$DATA_DIR/user-data/"* || $source == "$DATA_DIR/skill-projections/"* ]] || fail "Sandbox bind is outside this instance: $source"
    done <<<"$mounts"
    ORIGINAL_SANDBOXES+=("$id")
    dk stop --time 60 "$id" >/dev/null
  done
  dc stop --timeout 120
  [[ -z $(dk ps -q --filter "label=com.docker.compose.project=$PROJECT") ]] || fail 'A project container is still running.'
  assert_data_unmounted
}

wait_for_container_health() {
  local deadline=$((SECONDS + $1)) remaining states name status health ready pending
  shift
  (( $# )) || return 0
  while :; do
    remaining=$((deadline - SECONDS))
    if (( remaining <= 0 )); then
      printf 'ERROR: Timed out waiting for original containers: %s\n' "${pending:-unknown}" >&2
      return 1
    fi
    (( remaining <= 15 )) || remaining=15
    if ! states=$(timeout --kill-after=2s "${remaining}s" docker --host unix:///var/run/docker.sock inspect \
      --format '{{.Name}} {{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$@"); then
      printf 'ERROR: Could not read all original container states within the deadline.\n' >&2
      return 1
    fi
    ready=1
    pending=
    while read -r name status health; do
      case "$status:$health" in
        running:healthy|running:none) ;;
        exited:*|dead:*|removing:*)
          printf 'ERROR: Original container %s failed after restart: %s/%s\n' "$name" "$status" "$health" >&2
          return 1 ;;
        *) ready=0; pending+="$name=$status/$health " ;;
      esac
    done <<<"$states"
    (( ready )) && return 0
    sleep 1
  done
}

resume_instance() {
  local result=0
  (( NEEDS_RESUME )) || return 0
  # Compose start can rerun exited dependencies; resume only the recorded IDs.
  if (( ${#ORIGINAL_CONTAINERS[@]} )); then dk start "${ORIGINAL_CONTAINERS[@]}" >/dev/null || result=1; fi
  if (( ${#ORIGINAL_SANDBOXES[@]} )); then dk start "${ORIGINAL_SANDBOXES[@]}" >/dev/null || result=1; fi
  if (( result == 0 )); then
    wait_for_container_health 600 "${ORIGINAL_CONTAINERS[@]}" "${ORIGINAL_SANDBOXES[@]}" || result=1
  fi
  NEEDS_RESUME=0
  (( result == 0 )) || printf 'ERROR: Restart failed; inspect this instance immediately.\n' >&2
  return "$result"
}
