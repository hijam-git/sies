"""Copy database dumps offsite to a private Cloudflare R2 bucket.

`scripts/auto_backup.sh` writes `pg_dump` output and a media tarball to a
directory on the server. That is a backup of everything except the failure that
actually happens: the disk, the droplet, or the account. This command is the
second copy, and it runs **inside the backend container**, which already holds
the R2 credentials it needs for uploads — nothing extra to configure per host,
per user or per shell.

Adapted from `~/awliaa/backend/app/core/management/commands/backup_to_r2.py`
(CLAUDE.md §3: copy the patterns), including the two refusals that matter:

* **It will not write to the media bucket.** That bucket holds student photos
  and is read by the application; a database dump beside them is every student,
  every guardian's phone number and every fee record in one file, one guessed
  key away. `R2_BACKUP_BUCKET` must be set, and must differ.
* **It will not pretend an upload happened.** A missing credential, a missing
  bucket or a failed put is a non-zero exit, because this runs from cron and a
  backup job that reports success while doing nothing is worse than no backup
  job at all — it is the same outcome plus false confidence.

Retention is three months by default. Local storage is pruned aggressively by
the shell script because it shares a disk with Postgres; R2 is not, because
going further back than the box can is the whole point of an offsite copy.
"""

import os
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

PREFIX = 'db'


class Command(BaseCommand):
    help = 'Upload database backups to a private Cloudflare R2 bucket'

    def add_arguments(self, parser):
        parser.add_argument('--file', default='',
                            help='A specific dump to upload. Default: the newest in --dir.')
        parser.add_argument('--dir', default='backups',
                            help='Where the dumps are (default: backups/).')
        parser.add_argument('--all', action='store_true',
                            help='Upload every dump in the directory, not only the '
                                 'newest. Skips ones already there, so it is safe '
                                 'to repeat.')
        parser.add_argument('--retention-days', type=int, default=90,
                            help='Delete remote dumps older than this. 0 keeps '
                                 'everything. Default 90.')
        parser.add_argument('--list', action='store_true',
                            help='Show what is in the bucket and change nothing.')

    # ── setup ───────────────────────────────────────────────────────────────

    def bucket(self):
        bucket = (getattr(settings, 'R2_BACKUP_BUCKET', '') or '').strip()
        media = (getattr(settings, 'R2_BUCKET', '') or '').strip()

        if not bucket:
            raise CommandError(
                'R2_BACKUP_BUCKET is empty. Create a SEPARATE private bucket in '
                'Cloudflare R2 — no r2.dev domain, no custom domain — and name '
                'it there. A dump in the media bucket is every student and every '
                'fee record one guessed key away.')
        if media and bucket == media:
            raise CommandError(
                f'R2_BACKUP_BUCKET is the media bucket ({bucket}). The media '
                'bucket is read by the application; a database dump does not go '
                'in it. Use a separate private bucket.')
        return bucket

    def client(self):
        from core.storage import r2_client, r2_is_configured

        if not r2_is_configured():
            raise CommandError(
                'R2 is not configured. Set R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, '
                'R2_SECRET_ACCESS_KEY and R2_BUCKET in the environment.')
        return r2_client()

    # ── the work ────────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        bucket = self.bucket()
        client = self.client()
        server = getattr(settings, 'SIES_SERVER_NAME', 'server')

        if options['list']:
            return self.show(client, bucket)

        dumps = self.local_dumps(options)
        if not dumps:
            raise CommandError(
                f'No dump found in {options["dir"]}/. `scripts/auto_backup.sh` '
                'writes them; run it first, or pass --file.')

        remote = self.remote_keys(client, bucket)
        uploaded = 0
        for path in dumps:
            # The server name is in the FILENAME, not only the path: one bucket
            # may hold production, staging and a migration box at once, and the
            # prune below decides what is safe to delete by reading names.
            key = f'{PREFIX}/{server}/{server}--{os.path.basename(path)}'
            if key in remote:
                self.stdout.write(f'  already there: {key}')
                continue
            size = os.path.getsize(path)
            client.upload_file(path, bucket, key)
            uploaded += 1
            self.stdout.write(self.style.SUCCESS(
                f'  uploaded {key} ({size / 1_048_576:.1f} MB)'))

        pruned = self.prune(client, bucket, server, options['retention_days'])
        self.stdout.write(self.style.SUCCESS(
            f'{uploaded} uploaded, {pruned} pruned, bucket {bucket}'))

    def local_dumps(self, options):
        if options['file']:
            if not os.path.exists(options['file']):
                raise CommandError(f'No such file: {options["file"]}')
            return [options['file']]

        directory = options['dir']
        if not os.path.isdir(directory):
            return []
        found = sorted(
            (os.path.join(directory, name) for name in os.listdir(directory)
             if name.endswith(('.dump', '.sql', '.sql.gz', '.tar', '.tar.gz'))),
            key=os.path.getmtime, reverse=True,
        )
        return found if options['all'] else found[:1]

    def remote_keys(self, client, bucket):
        keys, token = set(), None
        while True:
            kwargs = {'Bucket': bucket, 'Prefix': f'{PREFIX}/'}
            if token:
                kwargs['ContinuationToken'] = token
            page = client.list_objects_v2(**kwargs)
            for row in page.get('Contents', []):
                keys.add(row['Key'])
            if not page.get('IsTruncated'):
                return keys
            token = page.get('NextContinuationToken')

    def prune(self, client, bucket, server, days):
        """Delete this server's old dumps. **Only this server's.**

        Matching on the server name is why it is in the filename: without it,
        a staging box running the same cron would prune production's history.
        """
        if not days:
            return 0

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        removed = 0
        token = None
        while True:
            kwargs = {'Bucket': bucket, 'Prefix': f'{PREFIX}/{server}/'}
            if token:
                kwargs['ContinuationToken'] = token
            page = client.list_objects_v2(**kwargs)
            for row in page.get('Contents', []):
                if row['LastModified'] < cutoff:
                    client.delete_object(Bucket=bucket, Key=row['Key'])
                    removed += 1
                    self.stdout.write(f'  pruned {row["Key"]}')
            if not page.get('IsTruncated'):
                return removed
            token = page.get('NextContinuationToken')

    def show(self, client, bucket):
        keys = sorted(self.remote_keys(client, bucket))
        if not keys:
            self.stdout.write('The bucket holds no dumps yet.')
            return
        for key in keys:
            self.stdout.write(f'  {key}')
        self.stdout.write(self.style.SUCCESS(f'{len(keys)} dumps in {bucket}'))
