#!/usr/bin/env bash
# WaveBook VPS backup — SQLite database + local uploads to a private GCS bucket.
#
# Uses the same gcloud CLI authentication as the app's GCS image uploads.
# Run daily via cron, e.g.:
#   0 3 * * * /opt/wavebook/backend/backup.sh >> /var/log/wavebook-backup.log 2>&1
#
# Requirements:
#   - gcloud installed and authenticated (gcloud auth login / service account key)
#   - GCS_BACKUP_BUCKET set in backend/.env (e.g. wavebook-backups)
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DB_PATH="${DATABASE_PATH:-$BACKEND_DIR/data/wavebook.db}"
UPLOADS_DIR="$BACKEND_DIR/uploads"
BUCKET="${GCS_BACKUP_BUCKET:-}"
STAMP="$(date +%Y-%m-%d_%H-%M-%S)"

if [ -z "$BUCKET" ]; then
  echo "GCS_BACKUP_BUCKET is not set — skipping backup."
  exit 0
fi

if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud CLI not found — skipping backup."
  exit 1
fi

echo "==> Backing up WaveBook to gs://$BUCKET ($STAMP)"

# 1. SQLite database (safe copy via sqlite3 .backup so the live DB is untouched)
if [ -f "$DB_PATH" ]; then
  TMP_DB="$(mktemp --suffix=.db)"
  sqlite3 "$DB_PATH" ".backup '$TMP_DB'"
  gcloud storage cp "$TMP_DB" "gs://$BUCKET/db/wavebook-$STAMP.db"
  rm -f "$TMP_DB"
  echo "    DB backed up."
else
  echo "    No database found at $DB_PATH — skipping."
fi

# 2. Local uploads (product images that are not in GCS)
if [ -d "$UPLOADS_DIR" ] && [ -n "$(ls -A "$UPLOADS_DIR" 2>/dev/null)" ]; then
  TMP_TAR="$(mktemp --suffix=.tar.gz)"
  tar -czf "$TMP_TAR" -C "$BACKEND_DIR" uploads
  gcloud storage cp "$TMP_TAR" "gs://$BUCKET/uploads/uploads-$STAMP.tar.gz"
  rm -f "$TMP_TAR"
  echo "    Uploads backed up."
else
  echo "    No local uploads — skipping."
fi

# 3. Prune old backups (keep the 14 most recent DB + upload archives)
echo "==> Pruning old backups (keeping 14)"
gcloud storage ls "gs://$BUCKET/db/" 2>/dev/null | sort | head -n -14 | while read -r obj; do
  gcloud storage rm "$obj" 2>/dev/null || true
done
gcloud storage ls "gs://$BUCKET/uploads/" 2>/dev/null | sort | head -n -14 | while read -r obj; do
  gcloud storage rm "$obj" 2>/dev/null || true
done

echo "==> Backup complete."
