#!/usr/bin/env bash
# Julkaise My Festival API Rahtiin komentoriviltä / Deploy My Festival API to Rahti from the command line
#
# FI: Vaihtoehto web-konsolille. Tarvitset oc-työkalun ja kirjautumisen:
#     https://console.rahti.csc.fi → oikea yläkulma → "Copy login command" → liitä terminaaliin.
# EN: Alternative to the web console. You need the oc tool and a login:
#     https://console.rahti.csc.fi → top right → "Copy login command" → paste into a terminal.
#
# Käyttö / Usage:  ./deploy_rahti.sh <csc-käyttäjätunnus/username> <github-repo-url> [csc-projektinumero]
set -euo pipefail
USER_ID="${1:?csc username}"
REPO="${2:?github repo url}"
CSC_PROJECT="${3:-2021201}"          # FI: kurssin CSC-projekti / EN: course CSC project
NS="festival-${USER_ID}"
APP="festival-api"

oc new-project "$NS" --display-name="My Festival API ($USER_ID)" \
   --description="csc_project: ${CSC_PROJECT}" || oc project "$NS"
oc new-app "$REPO" --strategy=docker --name="$APP"
oc set resources "deployment/$APP" --requests=cpu=50m,memory=128Mi --limits=cpu=250m,memory=256Mi
oc create route edge "$APP" --service="$APP" --insecure-policy=Redirect || true
oc rollout status "deployment/$APP" --timeout=600s
HOST=$(oc get route "$APP" -o jsonpath='{.spec.host}')
echo
echo "API: https://$HOST"
echo "Testaa / Test:  python test_endpoints.py https://$HOST"
