#!/usr/bin/env python
# coding: utf-8
#
# Copyright 2009 Facebook
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

u"""非阻塞，单线程 HTTP server。

典型的应用很少与 `HTTPServer` 类直接交互，除非在进程开始时开启server
（尽管这经常间接的通过 `tornado.web.Application.listen` 来完成）。

.. versionchanged:: 4.0

   曾经在此模块中的 ``HTTPRequest`` 类
   已经被移到 `tornado.httputil.HTTPServerRequest` 。
   其旧名称仍作为一个别名。
"""

from __future__ import absolute_import, division, print_function, with_statement

import socket

from tornado.escape import native_str
from tornado.http1connection import HTTP1ServerConnection, HTTP1ConnectionParameters
from tornado import gen
from tornado import httputil
from tornado import iostream
from tornado import netutil
from tornado.tcpserver import TCPServer
from tornado.util import Configurable


class HTTPServer(TCPServer, Configurable,
                 httputil.HTTPServerConnectionDelegate):
    ur"""非阻塞，单线程 HTTP server。

    一个server可以由一个 `.HTTPServerConnectionDelegate` 的子类定义，
    或者，为了向后兼容，由一个以 `.HTTPServerRequest` 为参数的callback定义。
    它的委托对象(delegate)通常是 `tornado.web.Application` 。

    `HTTPServer` 默认支持keep-alive链接（对于HTTP/1.1自动开启，而对于HTTP/1.0，
    需要client发起 ``Connection: keep-alive`` 请求）。

    如果 ``xheaders`` 是 ``True`` ，我们支持
    ``X-Real-Ip``/``X-Forwarded-For`` 和
    ``X-Scheme``/``X-Forwarded-Proto`` 首部字段，他们将会覆盖
    所有请求的 remote IP 与 URI scheme/protocol 。
    当Tornado运行在反向代理或者负载均衡(load balancer)之后时，
    这些首部字段非常有用。如果Tornado运行在一个不设置任何一个支持的
    ``xheaders`` 的SSL-decoding代理之后， ``protocol`` 参数也能设置为 ``https`` 。

    要使server可以服务于SSL加密的流量，需要把 ``ssl_option`` 参数
    设置为一个 `ssl.SSLContext` 对象。为了兼容旧版本的Python ``ssl_options``
    可能也是一个字典(dictionary)，其中包含传给 `ssl.wrap_socket` 方法的keyword arguments。

       ssl_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
       ssl_ctx.load_cert_chain(os.path.join(data_dir, "mydomain.crt"),
                               os.path.join(data_dir, "mydomain.key"))
       HTTPServer(applicaton, ssl_options=ssl_ctx)

    `HTTPServer` 的初始化依照以下三种模式之一（初始化方法定义
    在 `tornado.tcpserver.TCPServer` ）：

    1. `~tornado.tcpserver.TCPServer.listen`: 简单的单进程::

            server = HTTPServer(app)
            server.listen(8888)
            IOLoop.current().start()

       在很多情形下， `tornado.web.Application.listen` 可以用来避免显式的
       创建 `HTTPServer` 。

    2. `~tornado.tcpserver.TCPServer.bind`/`~tornado.tcpserver.TCPServer.start`:
       简单的多进程::

            server = HTTPServer(app)
            server.bind(8888)
            server.start(0)  # Fork 多个子进程
            IOLoop.current().start()

       当使用这个接口时，一个 `.IOLoop` 不能被传给 `HTTPServer`
       的构造方法(constructor)。 `~.TCPServer.start` 将默认
       在单例 `.IOLoop` 上开启server。

    3. `~tornado.tcpserver.TCPServer.add_sockets`: 高级多进程::

            sockets = tornado.netutil.bind_sockets(8888)
            tornado.process.fork_processes(0)
            server = HTTPServer(app)
            server.add_sockets(sockets)
            IOLoop.current().start()

       `~.TCPServer.add_sockets` 接口更加复杂，
       但是，当fork发生的时候，它可以与 `tornado.process.fork_processes`
       一起使用来提供更好的灵活性。
       如果你想使用其他的方法，而不是 `tornado.netutil.bind_sockets` ，
       来创建监听socket， `~.TCPServer.add_sockets` 也可以被用在单进程server中。

    .. versionchanged:: 4.0
       增加了 ``decompress_request``, ``chunk_size``, ``max_header_size``,
       ``idle_connection_timeout``, ``body_timeout``, ``max_body_size``
       参数。支持 `.HTTPServerConnectionDelegate` 实例化为 ``request_callback`` 。

    .. versionchanged:: 4.1
       `.HTTPServerConnectionDelegate.start_request` 现在需要传入两个参数来调用
       ``(server_conn, request_conn)`` （根据文档内容）而不是一个 ``(request_conn)``.

    .. versionchanged:: 4.2
       `HTTPServer` 现在是 `tornado.util.Configurable` 的一个子类。
    """
    def __init__(self, *args, **kwargs):
        # Ignore args to __init__; real initialization belongs in
        # initialize since we're Configurable. (there's something
        # weird in initialization order between this class,
        # Configurable, and TCPServer so we can't leave __init__ out
        # completely)
        pass

    def initialize(self, request_callback, no_keep_alive=False, io_loop=None,
                   xheaders=False, ssl_options=None, protocol=None,
                   decompress_request=False,
                   chunk_size=None, max_header_size=None,
                   idle_connection_timeout=None, body_timeout=None,
                   max_body_size=None, max_buffer_size=None):
        self.request_callback = request_callback
        self.no_keep_alive = no_keep_alive
        self.xheaders = xheaders
        self.protocol = protocol
        self.conn_params = HTTP1ConnectionParameters(
            decompress=decompress_request,
            chunk_size=chunk_size,
            max_header_size=max_header_size,
            header_timeout=idle_connection_timeout or 3600,
            max_body_size=max_body_size,
            body_timeout=body_timeout)
        TCPServer.__init__(self, io_loop=io_loop, ssl_options=ssl_options,
                           max_buffer_size=max_buffer_size,
                           read_chunk_size=chunk_size)
        self._connections = set()

    @classmethod
    def configurable_base(cls):
        return HTTPServer

    @classmethod
    def configurable_default(cls):
        return HTTPServer

    @gen.coroutine
    def close_all_connections(self):
        while self._connections:
            # Peek at an arbitrary element of the set
            conn = next(iter(self._connections))
            yield conn.close()

    def handle_stream(self, stream, address):
        context = _HTTPRequestContext(stream, address,
                                      self.protocol)
        conn = HTTP1ServerConnection(
            stream, self.conn_params, context)
        self._connections.add(conn)
        conn.start_serving(self)

    def start_request(self, server_conn, request_conn):
        return _ServerRequestAdapter(self, server_conn, request_conn)

    def on_close(self, server_conn):
        self._connections.remove(server_conn)


class _HTTPRequestContext(object):
    def __init__(self, stream, address, protocol):
        self.address = address
        # Save the socket's address family now so we know how to
        # interpret self.address even after the stream is closed
        # and its socket attribute replaced with None.
        if stream.socket is not None:
            self.address_family = stream.socket.family
        else:
            self.address_family = None
        # In HTTPServerRequest we want an IP, not a full socket address.
        if (self.address_family in (socket.AF_INET, socket.AF_INET6) and
                address is not None):
            self.remote_ip = address[0]
        else:
            # Unix (or other) socket; fake the remote address.
            self.remote_ip = '0.0.0.0'
        if protocol:
            self.protocol = protocol
        elif isinstance(stream, iostream.SSLIOStream):
            self.protocol = "https"
        else:
            self.protocol = "http"
        self._orig_remote_ip = self.remote_ip
        self._orig_protocol = self.protocol

    def __str__(self):
        if self.address_family in (socket.AF_INET, socket.AF_INET6):
            return self.remote_ip
        elif isinstance(self.address, bytes):
            # Python 3 with the -bb option warns about str(bytes),
            # so convert it explicitly.
            # Unix socket addresses are str on mac but bytes on linux.
            return native_str(self.address)
        else:
            return str(self.address)

    def _apply_xheaders(self, headers):
        """Rewrite the ``remote_ip`` and ``protocol`` fields."""
        # Squid uses X-Forwarded-For, others use X-Real-Ip
        ip = headers.get("X-Forwarded-For", self.remote_ip)
        ip = ip.split(',')[-1].strip()
        ip = headers.get("X-Real-Ip", ip)
        if netutil.is_valid_ip(ip):
            self.remote_ip = ip
        # AWS uses X-Forwarded-Proto
        proto_header = headers.get(
            "X-Scheme", headers.get("X-Forwarded-Proto",
                                    self.protocol))
        if proto_header in ("http", "https"):
            self.protocol = proto_header

    def _unapply_xheaders(self):
        """Undo changes from `_apply_xheaders`.

        Xheaders are per-request so they should not leak to the next
        request on the same connection.
        """
        self.remote_ip = self._orig_remote_ip
        self.protocol = self._orig_protocol


class _ServerRequestAdapter(httputil.HTTPMessageDelegate):
    """Adapts the `HTTPMessageDelegate` interface to the interface expected
    by our clients.
    """
    def __init__(self, server, server_conn, request_conn):
        self.server = server
        self.connection = request_conn
        self.request = None
        if isinstance(server.request_callback,
                      httputil.HTTPServerConnectionDelegate):
            self.delegate = server.request_callback.start_request(
                server_conn, request_conn)
            self._chunks = None
        else:
            self.delegate = None
            self._chunks = []

    def headers_received(self, start_line, headers):
        if self.server.xheaders:
            self.connection.context._apply_xheaders(headers)
        if self.delegate is None:
            self.request = httputil.HTTPServerRequest(
                connection=self.connection, start_line=start_line,
                headers=headers)
        else:
            return self.delegate.headers_received(start_line, headers)

    def data_received(self, chunk):
        if self.delegate is None:
            self._chunks.append(chunk)
        else:
            return self.delegate.data_received(chunk)

    def finish(self):
        if self.delegate is None:
            self.request.body = b''.join(self._chunks)
            self.request._parse_body()
            self.server.request_callback(self.request)
        else:
            self.delegate.finish()
        self._cleanup()

    def on_connection_close(self):
        if self.delegate is None:
            self._chunks = None
        else:
            self.delegate.on_connection_close()
        self._cleanup()

    def _cleanup(self):
        if self.server.xheaders:
            self.connection.context._unapply_xheaders()


HTTPRequest = httputil.HTTPServerRequest
