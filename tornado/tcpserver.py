#!/usr/bin/env python
#
# Copyright 2011 Facebook
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""A non-blocking, single-threaded TCP server."""
from __future__ import absolute_import, division, print_function, with_statement

import errno
import os
import socket

from tornado.log import app_log
from tornado.ioloop import IOLoop
from tornado.iostream import IOStream, SSLIOStream
from tornado.netutil import bind_sockets, add_accept_handler, ssl_wrap_socket
from tornado import process
from tornado.util import errno_from_exception

try:
    import ssl
except ImportError:
    # ssl is not available on Google App Engine.
    ssl = None


class TCPServer(object):
    r"""一个非阻塞, 单线程的 TCP 服务.

    想要使用 `TCPServer`, 只需要定义一个子类, 复写 `handle_stream`
    方法即可. 例如, 一个简单的 echo server 可以做如下定义::

      from tornado.tcpserver import TCPServer
      from tornado.iostream import StreamClosedError
      from tornado import gen

      class EchoServer(TCPServer):
          @gen.coroutine
          def handle_stream(self, stream, address):
              while True:
                  try:
                      data = yield stream.read_until(b"\n")
                      yield stream.write(data)
                  except StreamClosedError:
                      break

    为了使该服务提供 SSL 传输, 通过一个``ssl_options`` 关键字参数
    传递进去 `ssl.SSLContext` 对象即可. 为了兼容旧版本的 Python
    ``ssl_options`` 也可以是一个字典作为`ssl.wrap_socket` 方法的关键字参数.::

       ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
       ssl_ctx.load_cert_chain(os.path.join(data_dir, "mydomain.crt"),
                               os.path.join(data_dir, "mydomain.key"))
       TCPServer(ssl_options=ssl_ctx)

    `TCPServer` 初始化可以是以下三种模式之一:

    1. `listen`: 简单的单进程模式::

            server = TCPServer()
            server.listen(8888)
            IOLoop.current().start()

    2. `bind`/`start`: 简单的多进程模式::

            server = TCPServer()
            server.bind(8888)
            server.start(0)  # Forks multiple sub-processes
            IOLoop.current().start()

       当使用这个接口, `.IOLoop` 一定 *不能* 被传递给
       `TCPServer` 构造器.  `start` 总是会在默认单一的 `.IOLoop`
       上启动服务.

    3. `add_sockets`: 高级多进程模式::

            sockets = bind_sockets(8888)
            tornado.process.fork_processes(0)
            server = TCPServer()
            server.add_sockets(sockets)
            IOLoop.current().start()

       `add_sockets` 接口更加复杂, 但是它可以和 `tornado.process.fork_processes`
       一起被使用, 当 fork 发生的时候给你更多灵活性.  `add_sockets` 也可以被用于
       单进程服务中, 如果你想要使用 `~tornado.netutil.bind_sockets` 以外的方式
       创建你监听的 socket.

    .. versionadded:: 3.1
       ``max_buffer_size`` 参数.
    """
    def __init__(self, io_loop=None, ssl_options=None, max_buffer_size=None,
                 read_chunk_size=None):
        self.io_loop = io_loop
        self.ssl_options = ssl_options
        self._sockets = {}  # fd -> socket object
        self._pending_sockets = []
        self._started = False
        self.max_buffer_size = max_buffer_size
        self.read_chunk_size = read_chunk_size

        # Verify the SSL options. Otherwise we don't get errors until clients
        # connect. This doesn't verify that the keys are legitimate, but
        # the SSL module doesn't do that until there is a connected socket
        # which seems like too much work
        if self.ssl_options is not None and isinstance(self.ssl_options, dict):
            # Only certfile is required: it can contain both keys
            if 'certfile' not in self.ssl_options:
                raise KeyError('missing key "certfile" in ssl_options')

            if not os.path.exists(self.ssl_options['certfile']):
                raise ValueError('certfile "%s" does not exist' %
                                 self.ssl_options['certfile'])
            if ('keyfile' in self.ssl_options and
                    not os.path.exists(self.ssl_options['keyfile'])):
                raise ValueError('keyfile "%s" does not exist' %
                                 self.ssl_options['keyfile'])

    def listen(self, port, address=""):
        """开始在给定的端口接收连接.

        这个方法可能不只被调用一次, 可能会被调用多次在多个端口上.
        `listen` 立即生效; 它没必要在 `TCPServer.start` 之后调用.
        然而, 它必须要启动 `.IOLoop`.
        """
        sockets = bind_sockets(port, address=address)
        self.add_sockets(sockets)

    def add_sockets(self, sockets):
        """Makes this server start accepting connections on the given sockets.

        The ``sockets`` parameter is a list of socket objects such as
        those returned by `~tornado.netutil.bind_sockets`.
        `add_sockets` is typically used in combination with that
        method and `tornado.process.fork_processes` to provide greater
        control over the initialization of a multi-process server.
        """
        if self.io_loop is None:
            self.io_loop = IOLoop.current()

        for sock in sockets:
            self._sockets[sock.fileno()] = sock
            add_accept_handler(sock, self._handle_connection,
                               io_loop=self.io_loop)

    def add_socket(self, socket):
        """Singular version of `add_sockets`.  Takes a single socket object."""
        self.add_sockets([socket])

    def bind(self, port, address=None, family=socket.AF_UNSPEC, backlog=128):
        """Binds this server to the given port on the given address.

        To start the server, call `start`. If you want to run this server
        in a single process, you can call `listen` as a shortcut to the
        sequence of `bind` and `start` calls.

        Address may be either an IP address or hostname.  If it's a hostname,
        the server will listen on all IP addresses associated with the
        name.  Address may be an empty string or None to listen on all
        available interfaces.  Family may be set to either `socket.AF_INET`
        or `socket.AF_INET6` to restrict to IPv4 or IPv6 addresses, otherwise
        both will be used if available.

        The ``backlog`` argument has the same meaning as for
        `socket.listen <socket.socket.listen>`.

        This method may be called multiple times prior to `start` to listen
        on multiple ports or interfaces.
        """
        sockets = bind_sockets(port, address=address, family=family,
                               backlog=backlog)
        if self._started:
            self.add_sockets(sockets)
        else:
            self._pending_sockets.extend(sockets)

    def start(self, num_processes=1):
        """Starts this server in the `.IOLoop`.

        By default, we run the server in this process and do not fork any
        additional child process.

        If num_processes is ``None`` or <= 0, we detect the number of cores
        available on this machine and fork that number of child
        processes. If num_processes is given and > 1, we fork that
        specific number of sub-processes.

        Since we use processes and not threads, there is no shared memory
        between any server code.

        Note that multiple processes are not compatible with the autoreload
        module (or the ``autoreload=True`` option to `tornado.web.Application`
        which defaults to True when ``debug=True``).
        When using multiple processes, no IOLoops can be created or
        referenced until after the call to ``TCPServer.start(n)``.
        """
        assert not self._started
        self._started = True
        if num_processes != 1:
            process.fork_processes(num_processes)
        sockets = self._pending_sockets
        self._pending_sockets = []
        self.add_sockets(sockets)

    def stop(self):
        """Stops listening for new connections.

        Requests currently in progress may still continue after the
        server is stopped.
        """
        for fd, sock in self._sockets.items():
            self.io_loop.remove_handler(fd)
            sock.close()

    def handle_stream(self, stream, address):
        """Override to handle a new `.IOStream` from an incoming connection.

        This method may be a coroutine; if so any exceptions it raises
        asynchronously will be logged. Accepting of incoming connections
        will not be blocked by this coroutine.

        If this `TCPServer` is configured for SSL, ``handle_stream``
        may be called before the SSL handshake has completed. Use
        `.SSLIOStream.wait_for_handshake` if you need to verify the client's
        certificate or use NPN/ALPN.

        .. versionchanged:: 4.2
           Added the option for this method to be a coroutine.
        """
        raise NotImplementedError()

    def _handle_connection(self, connection, address):
        if self.ssl_options is not None:
            assert ssl, "Python 2.6+ and OpenSSL required for SSL"
            try:
                connection = ssl_wrap_socket(connection,
                                             self.ssl_options,
                                             server_side=True,
                                             do_handshake_on_connect=False)
            except ssl.SSLError as err:
                if err.args[0] == ssl.SSL_ERROR_EOF:
                    return connection.close()
                else:
                    raise
            except socket.error as err:
                # If the connection is closed immediately after it is created
                # (as in a port scan), we can get one of several errors.
                # wrap_socket makes an internal call to getpeername,
                # which may return either EINVAL (Mac OS X) or ENOTCONN
                # (Linux).  If it returns ENOTCONN, this error is
                # silently swallowed by the ssl module, so we need to
                # catch another error later on (AttributeError in
                # SSLIOStream._do_ssl_handshake).
                # To test this behavior, try nmap with the -sT flag.
                # https://github.com/tornadoweb/tornado/pull/750
                if errno_from_exception(err) in (errno.ECONNABORTED, errno.EINVAL):
                    return connection.close()
                else:
                    raise
        try:
            if self.ssl_options is not None:
                stream = SSLIOStream(connection, io_loop=self.io_loop,
                                     max_buffer_size=self.max_buffer_size,
                                     read_chunk_size=self.read_chunk_size)
            else:
                stream = IOStream(connection, io_loop=self.io_loop,
                                  max_buffer_size=self.max_buffer_size,
                                  read_chunk_size=self.read_chunk_size)
            future = self.handle_stream(stream, address)
            if future is not None:
                self.io_loop.add_future(future, lambda f: f.result())
        except Exception:
            app_log.error("Error in connection callback", exc_info=True)
