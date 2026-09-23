#!/usr/bin/env bash
# Render an admission form to a file you can open and print.
#
#   scripts/print_form.sh                 # first pending application, filled
#   scripts/print_form.sh 8               # that application
#   scripts/print_form.sh 8 blank         # the blank stack version
#
# The API needs a JWT, which a browser address bar cannot send, so this fetches
# the form with a token and writes it to ~/sies-forms/. Font URLs are rewritten
# to absolute ones against the running stack, so the saved file still prints
# with the right Bangla and Arabic faces rather than falling back to a system
# font — which is the whole reason those faces are self-hosted.
#
# This exists so the form can be looked at from the command line. The normal way
# to print one is the Print form button on Students -> Admissions.

set -uo pipefail
cd "$(dirname "$0")/.."

API=http://localhost:5000/api
BASE=http://localhost:5000
OUT="$HOME/sies-forms"
DC="docker compose -f docker-compose.dev.yml"
PHONE=${SIES_PHONE:-01700000000}
PASSWORD=${SIES_PASSWORD:-sies@2026}

MODE=${2:-filled}

TOKEN=$(curl -s -X POST "$API/auth/login/" -H 'Content-Type: application/json' \
        -d "{\"phone\":\"$PHONE\",\"password\":\"$PASSWORD\"}" \
      | grep -o '"access":"[^"]*"' | cut -d'"' -f4)
if [ -z "$TOKEN" ]; then
  echo "Could not log in as $PHONE. Is the stack up?  scripts/dev.sh up" >&2
  exit 1
fi

ID=${1:-}
if [ -z "$ID" ]; then
  ID=$($DC exec -T sies-backend python manage.py shell -c \
       'from students.models import Admission
a = Admission.objects.filter(status="pending").first()
print(a.pk if a else "")' 2>/dev/null | tr -d '\r' | tail -1)
fi
if [ -z "$ID" ]; then
  echo "No pending application found. Seed one:  scripts/dev.sh seed" >&2
  exit 1
fi

mkdir -p "$OUT"
FILE="$OUT/admission-form-$ID-$MODE.html"

curl -s -f "$API/admissions/$ID/form/?mode=$MODE" \
     -H "Authorization: Bearer $TOKEN" -o "$FILE" || {
  echo "Failed to render application $ID." >&2
  exit 1
}

# The form references /myadmin/fonts/... which resolves when the browser sits on
# the app's origin but not when the page is opened from disk. Point them at the
# running server so a saved copy keeps its fonts.
sed -i "s#url('/myadmin/fonts/#url('$BASE/myadmin/fonts/#g" "$FILE"

echo "Wrote $FILE"
echo
echo "Open it and press Ctrl+P — it is already A4 with print margins set."
echo "From Windows, the folder is under:"
echo "  \\\\wsl.localhost\\Ubuntu$OUT"
