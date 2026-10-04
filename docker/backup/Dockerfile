# Paśnik — obraz kontenera backupu (profil `backup`, 09_DEPLOYMENT §3).
#
# Baza: `postgres:16` — TA SAMA wersja co serwis `db`, więc `pg_dump`/`pg_restore`
# zawsze pasują do serwera (dump z nowszego klienta na starszy serwer to klasyczna
# awaria restore). Dokładamy tylko `python3` pod prune retencji
# (`backend/scripts/backup_prune.py` — czysta stdlib, testowana pytestem).
#
# UID 10001 = użytkownik `pasnik` z obrazu aplikacji: oba kontenery dzielą
# wolumen uploadów, więc restore musi pisać jako ten sam użytkownik, którym
# aplikacja czyta (docker/Dockerfile).
#
# Budowanie z korzenia repo: docker build -f docker/backup/Dockerfile .
FROM postgres:16

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 pasnik \
    && useradd --system --uid 10001 --gid pasnik --home /backups --shell /usr/sbin/nologin pasnik \
    && mkdir -p /backups /data/uploads \
    && chown -R pasnik:pasnik /backups /data

COPY --chmod=755 docker/backup/backup.sh docker/backup/restore.sh docker/backup/cron-loop.sh /opt/backup/
COPY --chmod=644 backend/scripts/backup_prune.py /opt/backup/prune.py

# Skróty dla `docker compose run --rm backup backup|restore ...`.
RUN ln -s /opt/backup/backup.sh /usr/local/bin/backup \
    && ln -s /opt/backup/restore.sh /usr/local/bin/restore

USER pasnik
WORKDIR /backups

# Obraz bazowy `postgres:17` ma ENTRYPOINT uruchamiający serwer — nadpisujemy.
ENTRYPOINT []
CMD ["/opt/backup/cron-loop.sh"]
