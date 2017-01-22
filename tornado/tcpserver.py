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

"""一个非阻塞, 单线程 TCP 服务."""
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

    为了使该服务提供 SSL 传输, 通过一个名为``ssl_options`` 的关键字参数
    传递进去 `ssl.SSLContext` 对象即可. 为了兼容旧版本的 Python,
    ``ssl_options`` 也可以是一个字典, 作为`ssl.wrap_socket` 方法的关键字参数.::

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

        这个方法可能不只被调用一次, 可能会在多个端口上被调用多次.
        `listen` 方法将立即生效, 所以它没必要在 `TCPServer.start` 之后调用.
        然而, 必须要启动 `.IOLoop` 才可以.
        """
        sockets = bind_sockets(port, address=address)
        self.add_sockets(sockets)

    def add_sockets(self, sockets):
        """使服务开始接收给定端口的连接.

        ``sockets`` 参数是一个 socket 对象的列表, 例如那些被
        `~tornado.netutil.bind_sockets` 所返回的对象.
        `add_sockets` 通常和 `tornado.process.fork_processes` 相结合使用,
        以便于在一个多进程服务初始化时提供更多控制.
        """
        if self.io_loop is None:
            self.io_loop = IOLoop.current()

        for sock in sockets:
            self._sockets[sock.fileno()] = sock
            add_accept_handler(sock, self._handle_connection,
                               io_loop=self.io_loop)

    def add_socket(self, socket):
        """单数版本的 `add_sockets`.  接受一个单一的 socket 对象."""
        self.add_sockets([socket])

    def bind(self, port, address=None, family=socket.AF_UNSPEC, backlog=128):
        """绑定该服务到指定的地址的指定端口上.

        要启动该服务, 调用 `start`. 如果你想要在一个单进程上运行该服务,
        你可以调用 `listen` 作为顺序调用 `bind` 和 `start` 的一个快捷方式.

        address 参数可以是 IP 地址或者主机名.  如果它是主机名,
        该服务将监听在和该名称有关的所有 IP 地址上.  地址也可以是空字符串或者
        None, 服务将监听所有可用的接口. family 可以被设置为 `socket.AF_INET` 或
        `socket.AF_INET6` 用来限定是 IPv4 或 IPv6 地址, 否则如果可用的话, 两者
        都将被使用.

        ``backlog`` 参数和 `socket.listen <socket.socket.listen>` 是相同含义.

        这个方法可能在 `start` 之前被调用多次来监听在多个端口或接口上.
        """
        sockets = bind_sockets(port, address=address, family=family,
                               backlog=backlog)
        if self._started:
            self.add_sockets(sockets)
        else:
            self._pending_sockets.extend(sockets)

    def start(self, num_processes=1):
        """在 `.IOLoop` 中启动该服务.

        默认情况下, 我们在该进程中运行服务, 并且不会 fork 出任何额外
        的子进程.

        如果 num_processes 为 ``None`` 或 <= 0, 我们检测这台机器上可用的
        核心数并 fork 相同数量的子进程. 如果给定了 num_processes 并且 > 1,
        我们 fork 指定数量的子进程.

        因为我们使用进程而不是线程, 在任何服务代码之间没有共享内存.

        注意多进程模式和 autoreload 模块不兼容(或者是当 ``debug=True`` 时
        `tornado.web.Application` 的 ``autoreload=True`` 选项默认为 True).
        当使用多进程模式时, 直到 ``TCPServer.start(n)`` 调用后, 才能创建或者
        引用 IOLoops .
        """
        assert not self._started
        self._started = True
        if num_processes != 1:
            process.fork_processes(num_processes)
        sockets = self._pending_sockets
        self._pending_sockets = []
        self.add_sockets(sockets)

    def stop(self):
        """停止对新连接的监听.

        正在进行的请求可能仍然会继续在服务停止之后.
        """
        for fd, sock in self._sockets.items():
            self.io_loop.remove_handler(fd)
            sock.close()

    def handle_stream(self, stream, address):
        """通过复写这个方法从进来的连接处理一个新的 `.IOStream` .

        这个方法可能是一个协程; if so any exceptions it raises
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
