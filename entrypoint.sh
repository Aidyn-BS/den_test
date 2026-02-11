#!/bin/bash
set -e

# If GOOGLE_CREDENTIALS_B64 is set and file doesn't exist — decode it
if [ -n "$GOOGLE_CREDENTIALS_B64" ] && [ ! -f "google_credentials.json" ]; then
    echo "$GOOGLE_CREDENTIALS_B64" | base64 -d > google_credentials.json
    echo "Decoded google_credentials.json from GOOGLE_CREDENTIALS_B64"
fi

# Auto-init database schema on first run
if [ -f "schema.sql" ] && [ -n "$DB_HOST" ]; then
    echo "Running schema.sql on database..."
    python -c "
import psycopg2, os
try:
    conn = psycopg2.connect(
        host=os.environ['DB_HOST'],
        port=os.environ.get('DB_PORT', '5432'),
        dbname=os.environ.get('DB_NAME', 'dental_clinic'),
        user=os.environ.get('DB_USER', 'postgres'),
        password=os.environ.get('DB_PASSWORD', ''),
    )
    conn.autocommit = True
    with open('schema.sql') as f:
        conn.cursor().execute(f.read())
    conn.close()
    print('Schema OK')
except Exception as e:
    print(f'Schema init: {e}')
"
fi

exec "$@"
