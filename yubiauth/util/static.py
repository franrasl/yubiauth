# Copyright (c) 2007 Ian Bicking and Contributors
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import mimetypes
import os

from webob import exc
from webob.dec import wsgify
from webob.response import Response

__all__ = [
    'FileApp', 'DirectoryApp',
]

mimetypes._winreg = None # do not load mimetypes from windows registry
mimetypes.add_type('text/javascript', '.js') # stdlib default is application/x-javascript
mimetypes.add_type('image/x-icon', '.ico') # not among defaults


class FileApp(object):
    """An application that will send the file at the given filename.

    Adds a mime type based on `mimetypes.guess_type()`.
    """

    def __init__(self, filename, **kw):
        self.filename = filename
        content_type, content_encoding = mimetypes.guess_type(filename)
        kw.setdefault('content_type', content_type)
        kw.setdefault('content_encoding', content_encoding)
        kw.setdefault('accept_ranges', 'bytes')
        self.kw = kw

    @wsgify
    def __call__(self, req):
        if req.method not in ('GET', 'HEAD'):
            return exc.HTTPMethodNotAllowed("You cannot %s a file" %
                                            req.method)
        try:
            stat = os.stat(self.filename)
        except (IOError, OSError) as e:
            msg = "Can't open %r: %s" % (self.filename, e)
            return exc.HTTPNotFound(comment=msg)

        try:
            file = open(self.filename, 'rb')
        except (IOError, OSError) as e:
            msg = "You are not permitted to view this file (%s)" % e
            return exc.HTTPForbidden(msg)

        return Response(
            app_iter = FileIter(file),
            content_length = stat.st_size,
            last_modified = stat.st_mtime,
            #@@ etag
            **self.kw
        ).conditional_response_app


class FileIter(object):
    def __init__(self, file):
        self.file = file

    def app_iter_range(self, seek=None, limit=None, block_size=1<<16):
        """Iter over the content of the file.

        You can set the `seek` parameter to read the file starting from a
        specific position.

        You can set the `limit` parameter to read the file up to specific
        position.

        Finally, you can change the number of bytes read at once by setting the
        `block_size` parameter.
        """

        if seek:
            self.file.seek(seek)
            if limit is not None:
                limit -= seek
        try:
            while True:
                data = self.file.read(min(block_size, limit)
                                      if limit is not None
                                      else block_size)
                if not data:
                    return
                yield data
                if limit is not None:
                    limit -= len(data)
                    if limit <= 0:
                        return
        finally:
            self.file.close()

    __iter__ = app_iter_range


class DirectoryApp(object):
    """An application that dispatches requests to corresponding `FileApp`s based
    on PATH_INFO.

    This app double-checks not to serve any files that are not in a
    subdirectory.  To customize `FileApp` instances creation, override
    `make_fileapp` method.
    """

    def __init__(self, path, **kw):
        self.path = os.path.abspath(path)
        if not self.path.endswith(os.path.sep):
            self.path += os.path.sep
        assert os.path.isdir(self.path)
        self.fileapp_kw = kw

    def make_fileapp(self, path):
        return FileApp(path, **self.fileapp_kw)

    @wsgify
    def __call__(self, req):
        path = os.path.abspath(os.path.join(self.path,
                                            req.path_info.lstrip('/')))
        if not os.path.isfile(path):
            return exc.HTTPNotFound(comment=path)
        elif not path.startswith(self.path):
            return exc.HTTPForbidden()
        else:
            return self.make_fileapp(path)
