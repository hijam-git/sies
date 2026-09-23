"""Where a file goes, and who can reach it (docs/01 §8).

No network: a fake S3 client stands in for R2, so these test the decisions this
project makes — the key, the privacy, the expiry, the refusals — rather than
Cloudflare's behaviour, which is not ours to test.
"""

import io
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from core.storage import R2Storage

R2_SET = dict(R2_ACCOUNT_ID='acc', R2_ACCESS_KEY_ID='key',
              R2_SECRET_ACCESS_KEY='secret', R2_BUCKET='sies-media',
              R2_PRESIGN_TTL=300)


class FakeS3:
    """Enough of boto3's client to hold this module to its own contract."""

    def __init__(self):
        self.objects = {}
        self.extra_args = {}
        self.presigned = []
        self.deleted = []

    def upload_fileobj(self, fileobj, bucket, key, ExtraArgs=None):
        self.objects[key] = fileobj.read()
        self.extra_args[key] = ExtraArgs or {}

    def upload_file(self, path, bucket, key):
        with open(path, 'rb') as handle:
            self.objects[key] = handle.read()

    def get_object(self, Bucket, Key):
        return {'Body': io.BytesIO(self.objects[Key])}

    def head_object(self, Bucket, Key):
        return {'ContentLength': len(self.objects[Key])}

    def delete_object(self, Bucket, Key):
        self.deleted.append(Key)
        self.objects.pop(Key, None)

    def list_objects_v2(self, **kwargs):
        prefix = kwargs.get('Prefix', '')
        return {'Contents': [{'Key': k, 'LastModified': _NOW}
                             for k in self.objects if k.startswith(prefix)],
                'IsTruncated': False}

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        self.presigned.append((Params['Key'], ExpiresIn))
        return f'https://r2.example/{Params["Key"]}?X-Amz-Expires={ExpiresIn}'


from datetime import datetime, timezone as _tz  # noqa: E402

_NOW = datetime.now(_tz.utc)


@override_settings(**R2_SET)
class KeyTests(SimpleTestCase):
    """The uploaded filename is never the key."""

    def setUp(self):
        self.fake = FakeS3()
        self.storage = R2Storage()
        patcher = patch('core.storage.r2_client', return_value=self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_two_files_of_the_same_name_do_not_collide(self):
        """Phones name every photo IMG_20240101.jpg.

        Django's default renames only on a collision; that is not enough when
        the collision silently replaces another student's photograph.
        """
        first = self.storage.save('students/photos/IMG_0001.jpg', ContentFile(b'a'))
        second = self.storage.save('students/photos/IMG_0001.jpg', ContentFile(b'b'))

        self.assertNotEqual(first, second)
        self.assertEqual(self.fake.objects[first], b'a')
        self.assertEqual(self.fake.objects[second], b'b')

    def test_the_folder_and_the_extension_survive(self):
        name = self.storage.save('documents/2026/03/birth.pdf', ContentFile(b'x'))

        self.assertTrue(name.startswith('documents/2026/03/'))
        self.assertTrue(name.endswith('.pdf'))
        self.assertNotIn('birth', name)

    def test_nothing_is_stored_as_public_or_cacheable(self):
        """A shared cache holding a birth certificate is the thing this bucket
        exists to avoid."""
        name = self.storage.save('documents/x.pdf', ContentFile(b'x'))

        cache_control = self.fake.extra_args[name]['CacheControl']
        self.assertIn('private', cache_control)
        self.assertIn('no-store', cache_control)

    def test_the_content_type_is_stored(self):
        name = self.storage.save('branches/logo.png', ContentFile(b'x'))

        self.assertEqual(self.fake.extra_args[name]['ContentType'], 'image/png')


@override_settings(**R2_SET)
class ReadTests(SimpleTestCase):
    def setUp(self):
        self.fake = FakeS3()
        self.storage = R2Storage()
        patcher = patch('core.storage.r2_client', return_value=self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_file_reads_back_exactly(self):
        """`students.views._stream` opens the file to send a document — the
        authenticated download path has to keep working unchanged."""
        name = self.storage.save('documents/a.pdf', ContentFile(b'hello'))

        self.assertEqual(self.storage.open(name).read(), b'hello')
        self.assertEqual(self.storage.size(name), 5)

    def test_every_url_expires(self):
        """There is no permanent link to leak, forward or index."""
        name = self.storage.save('students/photos/a.jpg', ContentFile(b'x'))

        url = self.storage.url(name)

        self.assertIn('X-Amz-Expires=300', url)
        self.assertEqual(self.fake.presigned[-1], (name, 300))

    def test_a_deleted_file_is_deleted(self):
        name = self.storage.save('documents/a.pdf', ContentFile(b'x'))

        self.storage.delete(name)

        self.assertIn(name, self.fake.deleted)


class FallbackTests(SimpleTestCase):
    """No credentials is not an error — it is the volume, as before."""

    @override_settings(R2_ACCOUNT_ID='', R2_ACCESS_KEY_ID='',
                       R2_SECRET_ACCESS_KEY='', R2_BUCKET='')
    def test_an_install_without_r2_is_not_configured(self):
        from core.storage import r2_is_configured

        self.assertFalse(r2_is_configured())

    @override_settings(**R2_SET)
    def test_a_configured_install_says_so(self):
        from core.storage import r2_is_configured

        self.assertTrue(r2_is_configured())


class BackupCommandTests(TestCase):
    """The refusals. Each one is a way to lose, or expose, the database."""

    @override_settings(**R2_SET, R2_BACKUP_BUCKET='')
    def test_it_refuses_without_a_backup_bucket(self):
        with self.assertRaises(CommandError) as caught:
            call_command('backup_to_r2')

        self.assertIn('R2_BACKUP_BUCKET', str(caught.exception))

    @override_settings(**R2_SET, R2_BACKUP_BUCKET='sies-media')
    def test_it_refuses_to_put_a_dump_in_the_media_bucket(self):
        """The media bucket is read by the application. A dump beside the
        student photos is every fee record one guessed key away."""
        with self.assertRaises(CommandError) as caught:
            call_command('backup_to_r2')

        self.assertIn('media bucket', str(caught.exception))

    @override_settings(R2_ACCOUNT_ID='', R2_ACCESS_KEY_ID='',
                       R2_SECRET_ACCESS_KEY='', R2_BUCKET='',
                       R2_BACKUP_BUCKET='sies-backups')
    def test_it_refuses_when_r2_is_not_configured(self):
        with self.assertRaises(CommandError) as caught:
            call_command('backup_to_r2')

        self.assertIn('not configured', str(caught.exception))

    @override_settings(**R2_SET, R2_BACKUP_BUCKET='sies-backups',
                       SIES_SERVER_NAME='prod')
    def test_a_dump_is_uploaded_under_this_servers_name(self):
        import tempfile

        fake = FakeS3()
        with tempfile.TemporaryDirectory() as directory:
            path = f'{directory}/sies-2026-09-23.dump'
            with open(path, 'wb') as handle:
                handle.write(b'PGDMP')

            with patch('core.storage.r2_client', return_value=fake):
                call_command('backup_to_r2', dir=directory)

        key = next(iter(fake.objects))
        # The server name is in the FILENAME, not only the path: one bucket may
        # hold production and staging, and the prune reads names.
        self.assertTrue(key.startswith('db/prod/prod--'))
        self.assertIn('sies-2026-09-23.dump', key)

    @override_settings(**R2_SET, R2_BACKUP_BUCKET='sies-backups',
                       SIES_SERVER_NAME='prod')
    def test_running_it_twice_uploads_once(self):
        import tempfile

        fake = FakeS3()
        with tempfile.TemporaryDirectory() as directory:
            path = f'{directory}/sies-2026-09-23.dump'
            with open(path, 'wb') as handle:
                handle.write(b'PGDMP')

            with patch('core.storage.r2_client', return_value=fake):
                call_command('backup_to_r2', dir=directory)
                call_command('backup_to_r2', dir=directory)

        self.assertEqual(len(fake.objects), 1)
