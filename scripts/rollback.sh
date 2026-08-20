#!/usr/bin/env bash
set -Eeuo pipefail

IMAGE=${1:?Usage: rollback.sh IMAGE RELEASE_DIR}
RELEASE_DIR=${2:?Usage: rollback.sh IMAGE RELEASE_DIR}
APP_ROOT=${APP_ROOT:-/opt/innova}
ENV_FILE=${APP_ENV_FILE:-"${APP_ROOT}/shared/.env"}
COMPOSE_FILE="${RELEASE_DIR}/docker-compose.prod.yml"
STATE_DIR="${APP_ROOT}/shared"

export APP_IMAGE="${IMAGE}"
export APP_ENV_FILE="${ENV_FILE}"

compose() {
    docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" "$@"
}

current_image=""
current_release=""
if [[ -f "${STATE_DIR}/current-image" ]]; then
    current_image=$(<"${STATE_DIR}/current-image")
fi
if [[ -f "${STATE_DIR}/current-release" ]]; then
    current_release=$(<"${STATE_DIR}/current-release")
fi

docker pull "${IMAGE}"
compose up -d --wait --wait-timeout 180 db redis
compose up -d --no-deps --wait --wait-timeout 180 api worker telegram-bot

if [[ -n "${current_image}" && "${current_image}" != "${IMAGE}" ]]; then
    printf '%s\n' "${current_image}" >"${STATE_DIR}/previous-image"
    printf '%s\n' "${current_release}" >"${STATE_DIR}/previous-release"
fi

printf '%s\n' "${IMAGE}" >"${STATE_DIR}/current-image"
printf '%s\n' "${RELEASE_DIR}" >"${STATE_DIR}/current-release"
ln -sfn "${RELEASE_DIR}" "${APP_ROOT}/current"

echo "Rollback completed: ${IMAGE}"
