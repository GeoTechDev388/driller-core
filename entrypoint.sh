#!/bin/sh
set -eu

if [ -n "${POSTGRES_HOST:-}" ] && [ -n "${POSTGRES_PORT:-}" ]; then
  echo "Waiting for database socket at ${POSTGRES_HOST}:${POSTGRES_PORT}..."
  python - <<'PY'
import os
import socket
import time

host = os.environ["POSTGRES_HOST"]
port = int(os.environ["POSTGRES_PORT"])
deadline = time.time() + 60

while True:
    try:
        with socket.create_connection((host, port), timeout=2):
            print(f"Database socket reachable at {host}:{port}")
            break
    except OSError:
        if time.time() >= deadline:
            raise SystemExit(f"Database socket not reachable at {host}:{port}")
        time.sleep(1)
PY

  echo "Waiting for PostgreSQL to accept real connections..."
  python - <<'PY'
import os
import time
import psycopg

dbname = os.environ.get("POSTGRES_DB", "")
user = os.environ.get("POSTGRES_USER", "")
password = os.environ.get("POSTGRES_PASSWORD", "")
host = os.environ["POSTGRES_HOST"]
port = os.environ["POSTGRES_PORT"]

deadline = time.time() + 90
last_error = None

while time.time() < deadline:
    try:
        conn = psycopg.connect(
            dbname=dbname,
            user=user,
            password=password,
            host=host,
            port=port,
            connect_timeout=3,
        )
        conn.close()
        print("PostgreSQL is ready for Django connections.")
        break
    except Exception as exc:
        last_error = exc
        print(f"PostgreSQL not ready yet: {exc}")
        time.sleep(2)
else:
    raise SystemExit(f"PostgreSQL did not become ready in time: {last_error}")
PY
fi

echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting Gunicorn..."
exec gunicorn driller_core.wsgi:application --bind 0.0.0.0:${PORT:-8003}
