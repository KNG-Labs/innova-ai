#!/usr/bin/env bash
set -Eeuo pipefail

IMAGE=${1:?Usage: deploy.sh IMAGE RELEASE_DIR}
RELEASE_DIR=${2:?Usage: deploy.sh IMAGE RELEASE_DIR}
APP_ROOT=${APP_ROOT:-/opt/innova}
ENV_FILE=${APP_ENV_FILE:-"${APP_ROOT}/shared/.env"}
COMPOSE_FILE="${RELEASE_DIR}/docker-compose.prod.yml"
STATE_DIR="${APP_ROOT}/shared"
BACKUP_DIR="${APP_ROOT}/backups"

mkdir -p "${STATE_DIR}" "${BACKUP_DIR}"
chmod 700 "${STATE_DIR}" "${BACKUP_DIR}"

exec 9>"${STATE_DIR}/deploy.lock"
flock 9

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "Runtime env file not found: ${ENV_FILE}" >&2
    exit 1
fi

if [[ ! -f "${COMPOSE_FILE}" ]]; then
    echo "Compose file not found: ${COMPOSE_FILE}" >&2
    exit 1
fi

export APP_IMAGE="${IMAGE}"
export APP_ENV_FILE="${ENV_FILE}"

compose() {
    docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" "$@"
}

previous_image=""
previous_release=""
if [[ -f "${STATE_DIR}/current-image" ]]; then
    previous_image=$(<"${STATE_DIR}/current-image")
fi
if [[ -f "${STATE_DIR}/current-release" ]]; then
    previous_release=$(<"${STATE_DIR}/current-release")
fi

on_error() {
    local exit_code=$?
    trap - ERR

    echo "Deployment failed for ${IMAGE}" >&2
    if [[ -n "${previous_image}" && -n "${previous_release}" ]]; then
        echo "Restoring previous image ${previous_image}" >&2
        bash "${previous_release}/scripts/rollback.sh" \
            "${previous_image}" \
            "${previous_release}" || true
    else
        echo "No previous release is available for rollback" >&2
    fi

    exit "${exit_code}"
}
trap on_error ERR

docker pull "${IMAGE}"

compose up -d --wait --wait-timeout 180 db redis

backup_timestamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_tmp="${BACKUP_DIR}/pre-deploy-${backup_timestamp}.sql.gz.tmp"
backup_file="${BACKUP_DIR}/pre-deploy-${backup_timestamp}.sql.gz"
compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
    | gzip >"${backup_tmp}"
chmod 600 "${backup_tmp}"
mv "${backup_tmp}" "${backup_file}"

compose --profile tools run --rm migrate
compose up -d --no-deps --wait --wait-timeout 180 api worker telegram-bot

if [[ -n "${previous_image}" && -n "${previous_release}" ]]; then
    printf '%s\n' "${previous_image}" >"${STATE_DIR}/previous-image"
    printf '%s\n' "${previous_release}" >"${STATE_DIR}/previous-release"
fi

printf '%s\n' "${IMAGE}" >"${STATE_DIR}/current-image"
printf '%s\n' "${RELEASE_DIR}" >"${STATE_DIR}/current-release"
ln -sfn "${RELEASE_DIR}" "${APP_ROOT}/current"

find "${BACKUP_DIR}" -type f -name 'pre-deploy-*.sql.gz' -mtime +14 -delete

trap - ERR
echo "Deployment completed: ${IMAGE}"
