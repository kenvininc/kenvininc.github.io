#!/bin/sh
# Chạy với quyền root chỉ để sửa quyền thư mục dữ liệu, sau đó chạy app bằng user "app".
set -e

mkdir -p "$MEDIA_ROOT" "$STATIC_ROOT"
chown -R app:app "$MEDIA_ROOT" "$STATIC_ROOT"

run() { setpriv --reuid=app --regid=app --init-groups env HOME=/home/app "$@"; }

echo "Chờ database..."
i=0
until run python -c "import psycopg,os; psycopg.connect(host=os.environ.get('POSTGRES_HOST','db'), port=os.environ.get('POSTGRES_PORT','5432'), dbname=os.environ['POSTGRES_DB'], user=os.environ['POSTGRES_USER'], password=os.environ['POSTGRES_PASSWORD'], connect_timeout=3).close()" 2>/dev/null; do
  i=$((i+1)); [ "$i" -gt 60 ] && echo "Không kết nối được database" && exit 1
  sleep 2
done

run python manage.py migrate --noinput
run python manage.py createcachetable
run python manage.py collectstatic --noinput -v 0

if [ "$#" -gt 0 ]; then
  exec setpriv --reuid=app --regid=app --init-groups env HOME=/home/app "$@"
fi
exec setpriv --reuid=app --regid=app --init-groups env HOME=/home/app gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 --workers "${GUNICORN_WORKERS:-3}" --timeout 60 \
  --access-logfile - --error-logfile - \
  --access-logformat '%(t)s "%(r)s" %(s)s %(b)s %(L)ss'
