"""Where uploaded files live (docs/01 §8).

Every `FileField` and `ImageField` in this project — a student's photo, a
scanned birth certificate, a branch logo, a voucher attachment — goes through
Django's storage API, so moving them off the server's disk is a question of
which backend `STORAGES['default']` names and nothing else. No model changes,
no migrations, no call-site changes.

**The bucket is PRIVATE, and that is not a default anyone may relax.** Awliaa's
R2 bucket is public because a product photo is meant to be seen by strangers;
this one holds a twelve-year-old's birth certificate and an institution's fee
vouchers. Two things follow, and both are implemented here rather than left to
a Cloudflare dashboard setting:

* `url()` returns a **presigned** link that expires (`R2_PRESIGN_TTL`,
  five minutes by default). There is no permanent URL to leak, forward or
  index.
* `Document.file` is still streamed through the authenticated endpoint that
  already exists (`students.views._stream`) — `open()` works against R2 exactly
  as it did against the disk, so the rule that a document only ever leaves
  through a permission check is unchanged.

**Not configured means the local disk**, exactly as before. An install with no
R2 credentials keeps working on its volume, which is what dev, CI and a
single-server deployment all do — the same shape as `SMS_PROVIDER=console`.
"""

import mimetypes
import os
import threading
import uuid
from datetime import datetime

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible


def r2_is_configured() -> bool:
    """True when every credential the bucket needs is present."""
    return all([
        getattr(settings, 'R2_ACCOUNT_ID', ''),
        getattr(settings, 'R2_ACCESS_KEY_ID', ''),
        getattr(settings, 'R2_SECRET_ACCESS_KEY', ''),
        getattr(settings, 'R2_BUCKET', ''),
    ])


def r2_endpoint() -> str:
    explicit = (getattr(settings, 'R2_ENDPOINT_URL', '') or '').strip()
    if explicit:
        return explicit
    account = (getattr(settings, 'R2_ACCOUNT_ID', '') or '').strip()
    return f'https://{account}.r2.cloudflarestorage.com' if account else ''


def r2_client(bucket_purpose='media'):
    """A boto3 S3 client pointed at R2.

    R2 speaks S3, with two fixed choices: signature v4 and the region `auto`.
    Built per call rather than cached on the class — boto3 clients are not
    thread-safe to share, and this runs under gunicorn and Celery both.
    """
    import boto3
    from botocore.config import Config

    return boto3.client(
        's3',
        endpoint_url=r2_endpoint(),
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        config=Config(signature_version='s3v4', retries={'max_attempts': 3}),
        region_name='auto',
    )


@deconstructible
class R2Storage(Storage):
    """Cloudflare R2, as a Django storage backend.

    Deconstructible because a `FileField` may name a storage in a migration;
    without it, `makemigrations` writes the instance's repr and fails to load.
    """

    def __init__(self, bucket=None, presign_ttl=None):
        self._bucket = bucket
        self._ttl = presign_ttl
        self._local = threading.local()

    # ── plumbing ────────────────────────────────────────────────────────────

    @property
    def bucket(self):
        return self._bucket or getattr(settings, 'R2_BUCKET', '')

    @property
    def ttl(self):
        return int(self._ttl or getattr(settings, 'R2_PRESIGN_TTL', 300))

    @property
    def client(self):
        # One client per thread, made once. `r2_client` is a module function so
        # a test can patch it without touching this class.
        if not hasattr(self._local, 'client'):
            self._local.client = r2_client()
        return self._local.client

    # ── the Storage interface ───────────────────────────────────────────────

    def get_available_name(self, name, max_length=None):
        """**Always a fresh key. Never the uploaded filename.**

        Django's default only renames on a collision, which is not enough here:
        phones name every photo `IMG_20240101.jpg`, so two students
        photographed on the same handset land on one key and the second upload
        silently replaces the first — the office edits one student and watches
        another's picture change. Awliaa hit exactly this with product photos
        (`catalog/models.py`), and the fix there was the same: generate the
        name, never accept it.

        The original extension is kept, because it is what tells a browser and
        an operating system what the file is.
        """
        folder = os.path.dirname(name)
        extension = os.path.splitext(name)[1].lower()
        stamp = datetime.now().strftime('%Y%m%d')
        unique = f'{stamp}-{uuid.uuid4().hex[:12]}{extension}'
        return os.path.join(folder, unique) if folder else unique

    def _save(self, name, content):
        content.seek(0)
        content_type = (getattr(content, 'content_type', '')
                        or mimetypes.guess_type(name)[0]
                        or 'application/octet-stream')
        self.client.upload_fileobj(
            content, self.bucket, name,
            ExtraArgs={
                'ContentType': content_type,
                # `private` and no caching: every read goes through a presigned
                # URL or the download endpoint, and a shared cache holding a
                # birth certificate is the thing this bucket exists to avoid.
                'CacheControl': 'private, max-age=0, no-store',
            },
        )
        return name

    def _open(self, name, mode='rb'):
        """Read a file back — what `_stream()` uses to send a document.

        Pulled whole into memory rather than streamed from the socket: these
        are photos and scans capped at 10 MB by `FILE_UPLOAD_MAX_MEMORY_SIZE`,
        and a lazy body would hold an R2 connection open for as long as the
        client takes to read it.
        """
        if 'w' in mode:
            raise ValueError('R2Storage opens files for reading only')
        body = self.client.get_object(Bucket=self.bucket, Key=name)['Body'].read()
        return ContentFile(body, name=name)

    def exists(self, name):
        """Whether the key is taken.

        Django calls this before saving. `get_available_name` above already
        guarantees a fresh key, so this answers False without a round trip —
        one HEAD per upload for a question whose answer is known is a request
        paid on every photo an office uploads.
        """
        return False

    def delete(self, name):
        if not name:
            return
        self.client.delete_object(Bucket=self.bucket, Key=name)

    def size(self, name):
        return self.client.head_object(Bucket=self.bucket, Key=name)['ContentLength']

    def url(self, name):
        """A link that **expires**.

        There is deliberately no permanent URL. A student's photo in a browser
        tab is a link somebody can forward; five minutes later it is a link to
        nothing, which is the difference between a leak and a moment.
        """
        return self.client.generate_presigned_url(
            'get_object',
            Params={'Bucket': self.bucket, 'Key': name},
            ExpiresIn=self.ttl,
        )
