# CliQ. nightly backup job for Railway (cron service). Client tools match
# Railway's Postgres major version (18).
FROM postgres:18
RUN apt-get update \
    && apt-get install --no-install-recommends -y python3 python3-boto3 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY backup_job.py /usr/local/bin/backup_job.py
USER postgres
CMD ["python3", "/usr/local/bin/backup_job.py"]
