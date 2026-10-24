#!/usr/bin/env bash
#
# SPDX-FileCopyrightText: 2026 The LineageOS Project
# SPDX-License-Identifier: Apache-2.0
#
# Publish a build to the Updater: optionally upload the zip to SourceForge,
# write the OTA feed entry (packages/apps/Updater/tools/pixelos_feed.py, which
# reads size, sha256, timestamp, patch level and the A/B streaming offsets
# from the zip) and the changelog into the OTA repository, then commit and push.
#
# usage: SF_PROJECT=<project> [SF_USER=<user>] tools/ota_release.sh <zip> [changelog.md]
#
#   SF_PROJECT  SourceForge project; zips live in /TB710FU/ of its files
#   SF_USER     SourceForge user; when set the zip is uploaded with rsync over
#               ssh (needs an ssh key in the SourceForge account), otherwise it
#               must already be uploaded
#   OTA_REPO    clone of the OTA repository (default: next to the source root)
#   NO_PUSH=1   commit without pushing
set -euo pipefail
TREE=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
TOP=$(cd "$TREE/../../.." && pwd)
DEVICE=TB710FU
BRANCH=seventeen
OTA_URL=https://github.com/Buffersolve/PixelOS_TB710FU_OTA
OTA_REPO=${OTA_REPO:-$(dirname "$TOP")/PixelOS_TB710FU_OTA}
FEED_TOOL=$TOP/packages/apps/Updater/tools/pixelos_feed.py

ZIP=${1:?usage: SF_PROJECT=<project> $0 <zip> [changelog.md]}
CHANGELOG=${2:-}
: "${SF_PROJECT:?set SF_PROJECT to the SourceForge project name}"
NAME=$(basename "$ZIP")
[[ $NAME =~ ^PixelOS_${DEVICE}-([0-9.]+)-[0-9]{8}-[0-9]{4}\.zip$ ]] \
    || { echo "ERROR: $NAME is not a PixelOS_$DEVICE-<version>-<date>.zip" >&2; exit 1; }
VERSION=${BASH_REMATCH[1]}
URL=https://downloads.sourceforge.net/project/$SF_PROJECT/$DEVICE/$NAME

if [ -n "${SF_USER:-}" ]; then
    rsync -P -e ssh "$ZIP" "$SF_USER@frs.sourceforge.net:/home/frs/project/$SF_PROJECT/$DEVICE/"
fi

# The Updater downloads and streams from this URL, so it must serve the whole
# file (SourceForge can take a few minutes to reach the mirrors after upload).
SIZE=$(stat -c %s "$ZIP")
REMOTE=$({ curl -sfIL "$URL" || true; } | tr -d '\r' | awk 'tolower($1) == "content-length:" { n = $2 } END { print n }')
if [ "$REMOTE" != "$SIZE" ]; then
    echo "ERROR: $URL serves ${REMOTE:-nothing}, expected $SIZE bytes; upload it or retry later" >&2
    exit 1
fi

[ -d "$OTA_REPO/.git" ] || git clone "$OTA_URL" "$OTA_REPO"
git -C "$OTA_REPO" pull -q --ff-only

mkdir -p "$OTA_REPO/$BRANCH/changelogs"
FEED=$OTA_REPO/$BRANCH/$DEVICE.json
python3 "$FEED_TOOL" generate-ota "$ZIP" --url "$URL" --version "$VERSION" --output "$FEED"
python3 "$FEED_TOOL" validate-ota "$FEED" --artifact "$ZIP"
if [ -n "$CHANGELOG" ]; then
    cp "$CHANGELOG" "$OTA_REPO/$BRANCH/changelogs/$DEVICE.md"
fi

git -C "$OTA_REPO" add -A "$BRANCH"
git -C "$OTA_REPO" commit -q -m "$DEVICE: ${NAME%.zip}"
[ "${NO_PUSH:-0}" = 1 ] || git -C "$OTA_REPO" push -q
echo "Published ${NAME%.zip}: $URL"
