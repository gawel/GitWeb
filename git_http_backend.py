#!/usr/bin/env python
'''
Module provides WSGI-based methods for handling HTTP Get and Post requests that
are specific only to git-http-backend's Smart HTTP protocol.

See __version__ statement below for indication of what version of Git's
Smart HTTP server this backend is (designed to be) compatible with.

Copyright (c) 2010  Daniel Dotsenko <dotsa@hotmail.com>
Selected, specifically marked so classes are also
  Copyright (C) 2006 Luke Arno - http://lukearno.com/

This file is part of git_http_backend.py Project.

git_http_backend.py Project is free software: you can redistribute it and/or modify
it under the terms of the GNU Lesser General Public License as published by
the Free Software Foundation, either version 2.1 of the License, or
(at your option) any later version.

git_http_backend.py Project is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public License
along with git_http_backend.py Project.  If not, see <http://www.gnu.org/licenses/>.
'''
import os
import sys
import logging
import subprocessio
from webob import Request, Response, exc

log = logging.getLogger(__name__)

class GitRepository(object):
    bufsize = 65536
    gzip_response = False
    git_folder_signature = set(['config', 'head', 'info', 'objects', 'refs'])
    commands = ['git-upload-pack', 'git-receive-pack']

    def __init__(self, content_path):
        self.content_path = content_path

    def inforefs(self, request):
        """WSGI Response producer for HTTP GET Git Smart HTTP /info/refs request."""

        git_command = request.GET['service']
        assert git_command in self.commands

        # note to self:
        # please, resist the urge to add '\n' to git capture and increment line count by 1.
        # The code in Git client not only does NOT need '\n', but actually blows up
        # if you sprinkle "flush" (0000) as "0001\n".
        # It reads binary, per number of bytes specified.
        # if you do add '\n' as part of data, count it.
        smart_server_advert = '# service=%s' % git_command
        try:
            out = subprocessio.SubprocessIOChunker(
                r'git %s --stateless-rpc --advertise-refs "%s"' % (git_command[4:], self.content_path),
                starting_values = [ str(hex(len(smart_server_advert)+4)[2:].rjust(4,'0') + smart_server_advert + '0000') ]
                )
        except EnvironmentError, e:
            raise exc.HTTPExpectationFailed()
        resp = Response()
        resp.content_type = 'application/x-%s-advertisement' % str(git_command)
        resp.app_iter = out
        return resp

    def backend(self, request):
        """
        WSGI Response producer for HTTP POST Git Smart HTTP requests.
        Reads commands and data from HTTP POST's body.
        returns an iterator obj with contents of git command's response to stdout
        """

        git_command = request.path_info.strip('/')
        assert git_command in self.commands

        try:
            out = subprocessio.SubprocessIOChunker(
                r'git %s --stateless-rpc "%s"' % (git_command[4:], self.content_path),
                inputstream = request.environ['wsgi.input']
                )
        except EnvironmentError, e:
            raise exc.HTTPExpectationFailed()

        if git_command in [u'git-receive-pack']:
            # updating refs manually after each push. Needed for pre-1.7.0.4 git clients using regular HTTP mode.
            subprocess.call(u'git --git-dir "%s" update-server-info' % repo_path, shell=True)

        resp = Response()
        resp.content_type = 'application/x-%s-result' % git_command.encode('utf8')
        resp.app_iter = out
        return resp


    def __call__(self, environ, start_response):
        request = Request(environ)
        print request
        if request.path_info.startswith('/info/refs'):
            app = self.inforefs
        else:
            app = self.backend
        try:
            resp = app(request)
        except exc.HTTPException, e:
            resp = e(environ, start_response)
        except Exception, e:
            log.exception(e)
            resp = exc.HTTPInternalServerError()
        #print 'Response\n', resp
        return resp(environ, start_response)

def make_app(global_config, content_path='', **local_config):
    return GitRepository(content_path)

