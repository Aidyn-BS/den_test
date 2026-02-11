#!/bin/bash
set -e

# If GOOGLE_CREDENTIALS_B64 is set and file doesn't exist — decode it
if [ -n "$GOOGLE_CREDENTIALS_B64" ] && [ ! -f "google_credentials.json" ]; then
    echo "$GOOGLE_CREDENTIALS_B64" | base64 -d > google_credentials.json
    echo "Decoded google_credentials.json from GOOGLE_CREDENTIALS_B64"
fi

exec "$@"
