'''
Module provides WSGI-based methods for handling HTTP Get and Post requests that
are specific only to git-http-backend's Smart HTTP protocol.

Copyright (c) 2011  Gael Pasgrimaud <gael@gawel.org>

This file is part of GitWeb Project.

GitWeb Project is free software: you can redistribute it and/or modify
it under the terms of the GNU Lesser General Public License as published by
the Free Software Foundation, either version 2.1 of the License, or
(at your option) any later version.

GitWeb Project is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public License
along with GitWeb Project.  If not, see <http://www.gnu.org/licenses/>.
'''
import os
import sys
import socket
import logging
import subprocess
import subprocessio
from webob import Request, Response, exc

log = logging.getLogger(__name__)

class FileWrapper(object):

    def __init__(self, fd, content_length):
        self.fd = fd
        self.content_length = content_length
        self.remain = content_length

    def read(self, size):
        if size <= self.remain:
            try:
                data = self.fd.read(size)
            except socket.error:
                raise IOError(self)
            self.remain -= size
        elif self.remain:
            data = self.fd.read(self.remain)
            self.remain = 0
        else:
            data = None
        return data

    def __repr__(self):
        return '<FileWrapper %s len: %s, read: %s>' % (
                self.fd, self.content_length, self.content_length - self.keep)

class GitRepository(object):
    git_folder_signature = set(['config', 'head', 'info', 'objects', 'refs'])
    commands = ['git-upload-pack', 'git-receive-pack']

    def __init__(self, content_path):
        if os.path.isdir(os.path.join(content_path, '.git')):
            content_path = os.path.join(content_path, '.git')
        files = set([f.lower() for f in os.listdir(content_path)])
        assert self.git_folder_signature.intersection(files) == self.git_folder_signature, content_path
        self.content_path = content_path
        self.valid_accepts = ['application/x-%s-result' % c for c in self.commands]

    def inforefs(self, request, environ):
        """WSGI Response producer for HTTP GET Git Smart HTTP /info/refs request."""

        git_command = request.GET['service']
        if git_command not in self.commands:
            return exc.HTTPMethodNotAllowed()

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

    def backend(self, request, environ):
        """
        WSGI Response producer for HTTP POST Git Smart HTTP requests.
        Reads commands and data from HTTP POST's body.
        returns an iterator obj with contents of git command's response to stdout
        """

        git_command = request.path_info.strip('/')
        if git_command not in self.commands:
            return exc.HTTPMethodNotAllowed()

        if 'CONTENT_LENGTH' in environ:
            inputstream = FileWrapper(environ['wsgi.input'], request.content_length)
        else:
            inputstream = environ['wsgi.input']

        try:
            out = subprocessio.SubprocessIOChunker(
                r'git %s --stateless-rpc "%s"' % (git_command[4:], self.content_path),
                inputstream = inputstream
                )
        except EnvironmentError, e:
            raise exc.HTTPExpectationFailed()

        if git_command in [u'git-receive-pack']:
            # updating refs manually after each push. Needed for pre-1.7.0.4 git clients using regular HTTP mode.
            subprocess.call(u'git --git-dir "%s" update-server-info' % self.content_path, shell=True)

        resp = Response()
        resp.content_type = 'application/x-%s-result' % git_command.encode('utf8')
        resp.app_iter = out
        return resp


    def __call__(self, environ, start_response):
        request = Request(environ)
        if request.path_info.startswith('/info/refs'):
            app = self.inforefs
        elif [a for a in self.valid_accepts if a in request.accept]:
            app = self.backend

        try:
            resp = app(request, environ)
        except exc.HTTPException, e:
            resp = e
            log.exception(e)
        except Exception, e:
            log.exception(e)
            resp = exc.HTTPInternalServerError()

        start_response(resp.status, resp.headers.items())
        return resp.app_iter

class GitDirectory(object):

    repository_app = GitRepository

    def __init__(self, content_path, auto_create=True, **kwargs):
        if not os.path.isdir(content_path):
            if auto_create:
                os.makedirs(content_path)
            else:
                raise OSError(content_path)
        self.content_path = content_path
        self.auto_create = auto_create
        if 'pre_clone_hook' in kwargs:
            self.pre_clone_hook = kwargs['pre_clone_hook']
        if 'post_clone_hook' in kwargs:
            self.pre_clone_hook = kwargs['post_clone_hook']

    def pre_clone_hook(self, content_path, request):
        pass

    def post_clone_hook(self, content_path, request):
        pass

    def __call__(self, environ, start_response):
        request = Request(environ)
        repo_name = request.path_info_pop()
        if not repo_name.endswith('.git'):
            return exc.HTTPNotFound()(environ, start_response)
        repo_name = repo_name[:-4]
        content_path = os.path.realpath(os.path.join(self.content_path, repo_name))
        if self.content_path not in content_path:
            return exc.HTTPForbidden()(environ, start_response)
        try:
            app = GitRepository(content_path)
        except (AssertionError, OSError):
            if os.path.isdir(os.path.join(content_path, '.git')):
                app = self.repository_app(os.path.join(content_path, '.git'))
            else:
                if self.auto_create and 'application/x-git-receive-pack-result' in request.accept:
                    try:
                        self.pre_clone_hook(content_path, request)
                        subprocess.call(u'git init --quiet --bare "%s"' % content_path, shell=True)
                        self.post_clone_hook(content_path, request)
                    except exc.HTTPException, e:
                        return e(environ, start_response)
                    app = self.repository_app(content_path)
                else:
                    return exc.HTTPNotFound()(environ, start_response)
        return app(environ, start_response)



def make_app(global_config, content_path='', **local_config):
    if 'content_path' in global_config:
        content_path = global_config['content_path']
    return GitRepository(content_path)

def make_dir_app(global_config, content_path='', auto_create=None, **local_config):
    if 'content_path' in global_config:
        content_path = global_config['content_path']
    return GitDirectory(content_path, auto_create=auto_create)

