#!/usr/bin/env sh
set -eu

BASE_URL="${BASE_URL:-http://localhost:8000}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost}"
USERNAME="${DJANGO_SUPERUSER_USERNAME:-admin}"
PASSWORD="${DJANGO_SUPERUSER_PASSWORD:-admin123}"

echo "== Bug Shoot self check =="
echo "Frontend: ${FRONTEND_URL}"
echo "Backend:  ${BASE_URL}"

echo "1. Checking frontend..."
curl -fsS "${FRONTEND_URL}" >/dev/null

echo "2. Checking login..."
TOKEN="$(
  curl -fsS -X POST "${BASE_URL}/api/auth/login/" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"${USERNAME}\",\"password\":\"${PASSWORD}\"}" \
  | python -c 'import json,sys; print(json.load(sys.stdin).get("access",""))'
)"

if [ -z "${TOKEN}" ]; then
  echo "Login failed: empty access token" >&2
  exit 1
fi

echo "3. Checking authenticated project list..."
curl -fsS "${BASE_URL}/api/debug/projects/" \
  -H "Authorization: Bearer ${TOKEN}" >/dev/null

echo "Self check passed."
