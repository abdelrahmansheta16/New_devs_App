#!/usr/bin/env bash
# Verifies the revenue dashboard fixes against a running docker-compose stack.
#
#   docker compose up --build -d
#   ./scripts/verify_fixes.sh
#
# Uses the client test accounts from ASSIGNMENT.md. Requires curl + jq.

set -uo pipefail

API="${API:-http://localhost:8000/api/v1}"
BODY="$(mktemp)"
trap 'rm -f "$BODY"' EXIT
PASS=0
FAIL=0

login() {
  curl -s -X POST "$API/auth/login" -H 'Content-Type: application/json' \
    -d "{\"email\":\"$1\",\"password\":\"$2\"}" | jq -r '.access_token // empty'
}

# GET with a bearer token; prints the HTTP status and leaves the body in $BODY.
get() {
  curl -s -o "$BODY" -w '%{http_code}' -H "Authorization: Bearer $1" "$API$2"
}

# Prints "<total_revenue> <reservations_count>" or "HTTP <status>".
summary() {
  local code
  code=$(get "$1" "/dashboard/summary?$2")
  if [ "$code" = "200" ]; then
    jq -r '"\(.total_revenue) \(.reservations_count)"' "$BODY"
  else
    echo "HTTP $code"
  fi
}

check() {
  if [ "$2" = "$3" ]; then
    echo "  PASS  $1  ->  $3"
    PASS=$((PASS + 1))
  else
    echo "  FAIL  $1  (expected: $2, got: $3)"
    FAIL=$((FAIL + 1))
  fi
}

SUNSET=$(login sunset@propertyflow.com client_a_2024)
OCEAN=$(login ocean@propertyflow.com client_b_2024)
[ -n "$SUNSET" ] && [ -n "$OCEAN" ] || { echo "Login failed - is the stack up?"; exit 1; }

echo "Client A - Sunset Properties (tenant-a)"
get "$SUNSET" "/dashboard/properties" > /dev/null
check "property list is tenant-scoped" "prop-001,prop-002,prop-003" "$(jq -r '[.data[].id] | join(",")' "$BODY")"
check "prop-001 all-time" "2250.00 4" "$(summary "$SUNSET" "property_id=prop-001")"
check "prop-001 March 2024 (Paris time)" "2250.00 4" "$(summary "$SUNSET" "property_id=prop-001&month=3&year=2024")"
check "prop-001 February 2024 (Paris time)" "0.00 0" "$(summary "$SUNSET" "property_id=prop-001&month=2&year=2024")"
check "prop-002 March 2024" "4975.50 4" "$(summary "$SUNSET" "property_id=prop-002&month=3&year=2024")"
check "prop-003 March 2024" "6100.50 2" "$(summary "$SUNSET" "property_id=prop-003&month=3&year=2024")"
check "other tenant's prop-004 is hidden" "HTTP 404" "$(summary "$SUNSET" "property_id=prop-004")"

echo
echo "Client B - Ocean Rentals (tenant-b), right after Client A warmed the cache"
get "$OCEAN" "/dashboard/properties" > /dev/null
check "property list is tenant-scoped" "prop-001:Mountain Lodge Beta,prop-004:Lakeside Cottage,prop-005:Urban Loft Modern" \
  "$(jq -r '[.data[] | "\(.id):\(.name)"] | join(",")' "$BODY")"
for i in 1 2 3 4 5; do
  check "prop-001 refresh #$i (must never show Sunset's 2250.00)" "0.00 0" "$(summary "$OCEAN" "property_id=prop-001")"
done
check "prop-004 March 2024 (New York time)" "1776.50 4" "$(summary "$OCEAN" "property_id=prop-004&month=3&year=2024")"
check "prop-005 March 2024 (New York time)" "3256.00 3" "$(summary "$OCEAN" "property_id=prop-005&month=3&year=2024")"
check "other tenant's prop-002 is hidden" "HTTP 404" "$(summary "$OCEAN" "property_id=prop-002")"

echo
echo "Auth hardening"
check "hardcoded mock token rejected" "401" "$(get mock-token-123 "/dashboard/summary?property_id=prop-002")"
check "password-less mock login rejected" "401" "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API/auth/login" \
  -H 'Content-Type: application/json' -d '{"email":"candidate@propertyflow.com","password":"anything"}')"
check "month without year rejected" "HTTP 422" "$(summary "$SUNSET" "property_id=prop-001&month=3")"

echo
echo "Result: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
