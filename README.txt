GitWeb is a fork of `git_http_backend.py
<https://github.com/dvdotsenko/git_http_backend.py>`_ using Webob

Dependencies
============

* Python 2.6
* Git >= 1.6.6 (On the server and on the client side.)

Installation
============

With easy_install::

  easy_install GitWeb

Get the source::

  git clone git://github.com/gawel/GitWeb.git

Usage
=====

The `gunicorn <http://gunicorn.org/>`_ WSGI server is recommended since it have
a great support of chunked transfer-encoding.

Here is a simple Paste config file::

  [server:main]
  use = egg:gunicorn

  [app:main]
  use = egg:GitWeb
  content_path = %(here)s/repos
  auto_create = true


License
=======

See file named COPYING.LESSER for license terms governing over the entire 
project. 

(Some, explisitely labeled so constituent files/works are licensed under
separate, more-permissive terms. See disclaimers at the start of the files for details.)

Contributors
============

- Gael Pasgrimaud <gael@gawel.org>

    Author of the fork

- Daniel Dotsenko <dotsa@hotmail.com>

    Maintener of git_http_backend.py and creator of subprocessio

