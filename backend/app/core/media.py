"""/media from the disk, for a production install with no R2 (core/urls.py).

Nothing else in the production stack can serve the media volume — there is no
nginx, and whitenoise serves only what collectstatic wrote — so without this
every photo and logo is a 404. `serve` streams the file (FileResponse), so a
large scan does not sit in a worker's memory.

**documents/ is never served here.** Those are birth certificates and transfer
letters, and they leave only through the authenticated download
(students.views._stream). A public path beside it would make that permission
check decoration.

The refusal is made on the NORMALISED path. A URL pattern that merely does not
start with documents/ is not enough: `serve` collapses `students/../documents/x`
to `documents/x` after the pattern has already matched, and hands the file over.
"""

import posixpath

from django.conf import settings
from django.http import Http404
from django.views.static import serve

PRIVATE_PREFIX = 'documents'


def serve_media(request, path):
    clean = posixpath.normpath(path.replace('\\', '/')).lstrip('/')
    if (clean in ('', '.') or clean.startswith('..')
            or clean == PRIVATE_PREFIX or clean.startswith(PRIVATE_PREFIX + '/')):
        raise Http404
    return serve(request, clean, document_root=settings.MEDIA_ROOT)
