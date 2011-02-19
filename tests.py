# -*- coding: utf-8 -*-
import unittest2 as unittest
from os.path import join
import subprocess
import tempfile
import socket
import signal
import shutil
import time
import os

def kill(pid):
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        print 'process %s is not running' % pid

def get_free_port():
    s = socket.socket()
    s.bind(('',0))
    ip, port = s.getsockname()
    s.close()
    return port

ini_file = """
[server:main]
use = egg:gunicorn
port = %(port)s

[app:main]
use = egg:GitWeb#dir
content_path = %(repos)s
auto_create = true
"""

def call(*args, **kwargs):
    print 'running %r' % ' '.join(args)
    if subprocess.call(args, **kwargs) != 0:
        print 'error while running command: %s' % ' '.join(args)

def realpath(*args):
    dirname = os.path.realpath(join(*args))
    if not os.path.isdir(dirname) and dirname[-4] != '.':
        os.makedirs(dirname)
    return dirname

class TestGit(unittest.TestCase):

    def setUp(self):
        self.addCleanup(os.chdir, os.getcwd())
        self.wd = tempfile.mkdtemp(prefix='gitweb-')
        self.addCleanup(shutil.rmtree, self.wd)

        repos = realpath(self.wd, 'repos')
        repo = realpath(self.wd, 'repos', 'sample')
        port = get_free_port()
        self.url = 'http://127.0.0.1:%s/' % port

        config = realpath(self.wd, 'repos', 'config.ini')
        open(config, 'w').write(ini_file % locals())

        cmd = ['bin/paster', 'serve', config]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(kill, p.pid)

        os.chdir(repo)
        call('git', 'init')
        call('git', 'update-server-info')

        time.sleep(1)

        os.chdir(self.wd)

    def test_simple(self):
        url = self.url+'new.git'
        os.makedirs('new')
        os.chdir('new')
        call('git', 'init')
        open('README', 'w').write('test '*1024)
        call('git', 'add', 'README')
        call('git', 'commit', '-m', 'test')
        call('git', 'clone', '.', url)

    def test_existing_repo(self):
        url = self.url+'repo.git'
        call('git', 'clone', url)
        os.chdir('repo')
        open('README', 'w').write('test '*(1024*1024*2))
        call('git', 'add', 'README')
        call('git', 'commit', '-m', 'test')
        call('git', 'push', 'origin', 'master')

