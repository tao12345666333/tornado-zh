#!/usr/bin/env python
# coding: utf-8

"""阻塞和非阻塞的 HTTP 客户端接口.

这个模块定义了一个被两种实现方式 ``simple_httpclient`` 和
``curl_httpclient`` 共享的通用接口 . 应用程序可以选择直接实例化相对应的实现类,
或使用本模块提供的 `AsyncHTTPClient` 类, 通过复写
`AsyncHTTPClient.configure` 方法来选择一种实现 .

默认的实现是 ``simple_httpclient``, 这可以能满足大多数用户的需要 . 然而, 一
些应用程序可能会因为以下原因想切换到 ``curl_httpclient`` :

* ``curl_httpclient`` 有一些 ``simple_httpclient`` 不具有的功能特性,
  包括对 HTTP 代理和使用指定网络接口能力的支持.

* ``curl_httpclient`` 更有可能与不完全符合 HTTP 规范的网站兼容, 或者与
  使用很少使用 HTTP 特性的网站兼容.

* ``curl_httpclient`` 更快.

* ``curl_httpclient`` 是 Tornado 2.0 之前的默认值.

注意, 如果你正在使用 ``curl_httpclient``, 强力建议你使用最新版本的
``libcurl`` 和 ``pycurl``.  当前 libcurl 能被支持的最小版本是
7.21.1, pycurl 能被支持的最小版本是 7.18.2. 强烈建议你所安装的 ``libcurl``
是和异步 DNS 解析器 (threaded 或 c-ares) 一起构建的,
否则你可能会遇到各种请求超时的问题 (更多信息请查看
http://curl.haxx.se/libcurl/c/curl_easy_setopt.html#CURLOPTCONNECTTIMEOUTMS
和 curl_httpclient.py 里面的注释).

为了选择 ``curl_httpclient``, 只需要在启动的时候调用
`AsyncHTTPClient.configure` ::

    AsyncHTTPClient.configure("tornado.curl_httpclient.CurlAsyncHTTPClient")
"""

from __future__ import absolute_import, division, print_function, with_statement

import functools
import time
import weakref

from tornado.concurrent import TracebackFuture
from tornado.escape import utf8, native_str
from tornado import httputil, stack_context
from tornado.ioloop import IOLoop
from tornado.util import Configurable


class HTTPClient(object):
    """一个阻塞的 HTTP 客户端.

    提供这个接口是为了方便使用和测试; 大多数运行于 IOLoop 的应用程序
    会使用 `AsyncHTTPClient` 来替代它.
    一般的用法就像这样 ::

        http_client = httpclient.HTTPClient()
        try:
            response = http_client.fetch("http://www.google.com/")
            print response.body
        except httpclient.HTTPError as e:
            # HTTPError is raised for non-200 responses; the response
            # can be found in e.response.
            print("Error: " + str(e))
        except Exception as e:
            # Other errors are possible, such as IOError.
            print("Error: " + str(e))
        http_client.close()
    """
    def __init__(self, async_client_class=None, **kwargs):
        self._io_loop = IOLoop(make_current=False)
        if async_client_class is None:
            async_client_class = AsyncHTTPClient
        self._async_client = async_client_class(self._io_loop, **kwargs)
        self._closed = False

    def __del__(self):
        self.close()

    def close(self):
        """关闭该 HTTPClient, 释放所有使用的资源."""
        if not self._closed:
            self._async_client.close()
            self._io_loop.close()
            self._closed = True

    def fetch(self, request, **kwargs):
        """执行一个请求, 返回一个 `HTTPResponse` 对象.

        该请求可以是一个 URL 字符串或是一个 `HTTPRequest` 对象.
        如果它是一个字符串, 我们会使用任意关键字参数构造一个
        `HTTPRequest` : ``HTTPRequest(request, **kwargs)``

        如果在 fetch 过程中发生错误, 我们将抛出一个 `HTTPError` 除非
        ``raise_error`` 关键字参数被设置为 False.
        """
        response = self._io_loop.run_sync(functools.partial(
            self._async_client.fetch, request, **kwargs))
        return response


class AsyncHTTPClient(Configurable):
    """一个非阻塞 HTTP 客户端.

    使用示例::

        def handle_request(response):
            if response.error:
                print "Error:", response.error
            else:
                print response.body

        http_client = AsyncHTTPClient()
        http_client.fetch("http://www.google.com/", handle_request)

    这个类的构造器有几个比较神奇的考虑: 它实际创建了一个基于特定实现的子
    类的实例, 并且该实例被作为一种伪单例重用 (每一个 `.IOLoop` ).
    使用关键字参数 ``force_instance=True`` 可以用来限制这种单例行为.
    只有使用了 ``force_instance=True`` 时候, 才可以传递 ``io_loop`` 以外其他
    的参数给 `AsyncHTTPClient` 构造器.
    实现的子类以及它的构造器的参数可以通过静态方法 `configure()` 设置.

    所有 `AsyncHTTPClient` 实现都支持一个 ``defaults`` 关键字参数,
    可以被用来设置默认 `HTTPRequest` 属性的值. 例如::

        AsyncHTTPClient.configure(
            None, defaults=dict(user_agent="MyUserAgent"))
        # or with force_instance:
        client = AsyncHTTPClient(force_instance=True,
            defaults=dict(user_agent="MyUserAgent"))

    .. versionchanged:: 4.1
       ``io_loop`` 参数被废弃.
    """
    @classmethod
    def configurable_base(cls):
        return AsyncHTTPClient

    @classmethod
    def configurable_default(cls):
        from tornado.simple_httpclient import SimpleAsyncHTTPClient
        return SimpleAsyncHTTPClient

    @classmethod
    def _async_clients(cls):
        attr_name = '_async_client_dict_' + cls.__name__
        if not hasattr(cls, attr_name):
            setattr(cls, attr_name, weakref.WeakKeyDictionary())
        return getattr(cls, attr_name)

    def __new__(cls, io_loop=None, force_instance=False, **kwargs):
        io_loop = io_loop or IOLoop.current()
        if force_instance:
            instance_cache = None
        else:
            instance_cache = cls._async_clients()
        if instance_cache is not None and io_loop in instance_cache:
            return instance_cache[io_loop]
        instance = super(AsyncHTTPClient, cls).__new__(cls, io_loop=io_loop,
                                                       **kwargs)
        # Make sure the instance knows which cache to remove itself from.
        # It can't simply call _async_clients() because we may be in
        # __new__(AsyncHTTPClient) but instance.__class__ may be
        # SimpleAsyncHTTPClient.
        instance._instance_cache = instance_cache
        if instance_cache is not None:
            instance_cache[instance.io_loop] = instance
        return instance

    def initialize(self, io_loop, defaults=None):
        self.io_loop = io_loop
        self.defaults = dict(HTTPRequest._DEFAULTS)
        if defaults is not None:
            self.defaults.update(defaults)
        self._closed = False

    def close(self):
        """销毁该 HTTP 客户端, 释放所有被使用的文件描述符.

        因为 `AsyncHTTPClient` 对象透明重用的方式, 该方法
        **在正常使用时并不需要** .
        ``close()`` 一般只有在`.IOLoop` 也被关闭, 或在创建
        `AsyncHTTPClient` 的时候使用了 ``force_instance=True`` 参数才需要.

        在 `AsyncHTTPClient` 调用 ``close()`` 方法后, 其他方法就不能被调用
        了.

        """
        if self._closed:
            return
        self._closed = True
        if self._instance_cache is not None:
            if self._instance_cache.get(self.io_loop) is not self:
                raise RuntimeError("inconsistent AsyncHTTPClient cache")
            del self._instance_cache[self.io_loop]

    def fetch(self, request, callback=None, raise_error=True, **kwargs):
        """执行一个请求, 异步的返回一个 `HTTPResponse`.

        The request may be either a string URL or an `HTTPRequest` object.
        If it is a string, we construct an `HTTPRequest` using any additional
        kwargs: ``HTTPRequest(request, **kwargs)``

        This method returns a `.Future` whose result is an
        `HTTPResponse`.  By default, the ``Future`` will raise an `HTTPError`
        if the request returned a non-200 response code. Instead, if
        ``raise_error`` is set to False, the response will always be
        returned regardless of the response code.

        If a ``callback`` is given, it will be invoked with the `HTTPResponse`.
        In the callback interface, `HTTPError` is not automatically raised.
        Instead, you must check the response's ``error`` attribute or
        call its `~HTTPResponse.rethrow` method.
        """
        if self._closed:
            raise RuntimeError("fetch() called on closed AsyncHTTPClient")
        if not isinstance(request, HTTPRequest):
            request = HTTPRequest(url=request, **kwargs)
        # We may modify this (to add Host, Accept-Encoding, etc),
        # so make sure we don't modify the caller's object.  This is also
        # where normal dicts get converted to HTTPHeaders objects.
        request.headers = httputil.HTTPHeaders(request.headers)
        request = _RequestProxy(request, self.defaults)
        future = TracebackFuture()
        if callback is not None:
            callback = stack_context.wrap(callback)

            def handle_future(future):
                exc = future.exception()
                if isinstance(exc, HTTPError) and exc.response is not None:
                    response = exc.response
                elif exc is not None:
                    response = HTTPResponse(
                        request, 599, error=exc,
                        request_time=time.time() - request.start_time)
                else:
                    response = future.result()
                self.io_loop.add_callback(callback, response)
            future.add_done_callback(handle_future)

        def handle_response(response):
            if raise_error and response.error:
                future.set_exception(response.error)
            else:
                future.set_result(response)
        self.fetch_impl(request, handle_response)
        return future

    def fetch_impl(self, request, callback):
        raise NotImplementedError()

    @classmethod
    def configure(cls, impl, **kwargs):
        """配置 `AsyncHTTPClient` 使用的子类.

        ``AsyncHTTPClient()`` 实际创建一个这个子类的实例.
        This method may be called with either a class object or the
        fully-qualified name of such a class (or ``None`` to use the default,
        ``SimpleAsyncHTTPClient``)

        If additional keyword arguments are given, they will be passed
        to the constructor of each subclass instance created.  The
        keyword argument ``max_clients`` determines the maximum number
        of simultaneous `~AsyncHTTPClient.fetch()` operations that can
        execute in parallel on each `.IOLoop`.  Additional arguments
        may be supported depending on the implementation class in use.

        Example::

           AsyncHTTPClient.configure("tornado.curl_httpclient.CurlAsyncHTTPClient")
        """
        super(AsyncHTTPClient, cls).configure(impl, **kwargs)


class HTTPRequest(object):
    """HTTP 客户端请求对象."""

    # Default values for HTTPRequest parameters.
    # Merged with the values on the request object by AsyncHTTPClient
    # implementations.
    _DEFAULTS = dict(
        connect_timeout=20.0,
        request_timeout=20.0,
        follow_redirects=True,
        max_redirects=5,
        decompress_response=True,
        proxy_password='',
        allow_nonstandard_methods=False,
        validate_cert=True)

    def __init__(self, url, method="GET", headers=None, body=None,
                 auth_username=None, auth_password=None, auth_mode=None,
                 connect_timeout=None, request_timeout=None,
                 if_modified_since=None, follow_redirects=None,
                 max_redirects=None, user_agent=None, use_gzip=None,
                 network_interface=None, streaming_callback=None,
                 header_callback=None, prepare_curl_callback=None,
                 proxy_host=None, proxy_port=None, proxy_username=None,
                 proxy_password=None, allow_nonstandard_methods=None,
                 validate_cert=None, ca_certs=None,
                 allow_ipv6=None,
                 client_key=None, client_cert=None, body_producer=None,
                 expect_100_continue=False, decompress_response=None,
                 ssl_options=None):
        r"""All parameters except ``url`` are optional.

        :arg string url: URL to fetch
        :arg string method: HTTP method, e.g. "GET" or "POST"
        :arg headers: Additional HTTP headers to pass on the request
        :type headers: `~tornado.httputil.HTTPHeaders` or `dict`
        :arg body: HTTP request body as a string (byte or unicode; if unicode
           the utf-8 encoding will be used)
        :arg body_producer: Callable used for lazy/asynchronous request bodies.
           It is called with one argument, a ``write`` function, and should
           return a `.Future`.  It should call the write function with new
           data as it becomes available.  The write function returns a
           `.Future` which can be used for flow control.
           Only one of ``body`` and ``body_producer`` may
           be specified.  ``body_producer`` is not supported on
           ``curl_httpclient``.  When using ``body_producer`` it is recommended
           to pass a ``Content-Length`` in the headers as otherwise chunked
           encoding will be used, and many servers do not support chunked
           encoding on requests.  New in Tornado 4.0
        :arg string auth_username: Username for HTTP authentication
        :arg string auth_password: Password for HTTP authentication
        :arg string auth_mode: Authentication mode; default is "basic".
           Allowed values are implementation-defined; ``curl_httpclient``
           supports "basic" and "digest"; ``simple_httpclient`` only supports
           "basic"
        :arg float connect_timeout: Timeout for initial connection in seconds
        :arg float request_timeout: Timeout for entire request in seconds
        :arg if_modified_since: Timestamp for ``If-Modified-Since`` header
        :type if_modified_since: `datetime` or `float`
        :arg bool follow_redirects: Should redirects be followed automatically
           or return the 3xx response?
        :arg int max_redirects: Limit for ``follow_redirects``
        :arg string user_agent: String to send as ``User-Agent`` header
        :arg bool decompress_response: Request a compressed response from
           the server and decompress it after downloading.  Default is True.
           New in Tornado 4.0.
        :arg bool use_gzip: Deprecated alias for ``decompress_response``
           since Tornado 4.0.
        :arg string network_interface: Network interface to use for request.
           ``curl_httpclient`` only; see note below.
        :arg callable streaming_callback: If set, ``streaming_callback`` will
           be run with each chunk of data as it is received, and
           ``HTTPResponse.body`` and ``HTTPResponse.buffer`` will be empty in
           the final response.
        :arg callable header_callback: If set, ``header_callback`` will
           be run with each header line as it is received (including the
           first line, e.g. ``HTTP/1.0 200 OK\r\n``, and a final line
           containing only ``\r\n``.  All lines include the trailing newline
           characters).  ``HTTPResponse.headers`` will be empty in the final
           response.  This is most useful in conjunction with
           ``streaming_callback``, because it's the only way to get access to
           header data while the request is in progress.
        :arg callable prepare_curl_callback: If set, will be called with
           a ``pycurl.Curl`` object to allow the application to make additional
           ``setopt`` calls.
        :arg string proxy_host: HTTP proxy hostname.  To use proxies,
           ``proxy_host`` and ``proxy_port`` must be set; ``proxy_username`` and
           ``proxy_pass`` are optional.  Proxies are currently only supported
           with ``curl_httpclient``.
        :arg int proxy_port: HTTP proxy port
        :arg string proxy_username: HTTP proxy username
        :arg string proxy_password: HTTP proxy password
        :arg bool allow_nonstandard_methods: Allow unknown values for ``method``
           argument?
        :arg bool validate_cert: For HTTPS requests, validate the server's
           certificate?
        :arg string ca_certs: filename of CA certificates in PEM format,
           or None to use defaults.  See note below when used with
           ``curl_httpclient``.
        :arg string client_key: Filename for client SSL key, if any.  See
           note below when used with ``curl_httpclient``.
        :arg string client_cert: Filename for client SSL certificate, if any.
           See note below when used with ``curl_httpclient``.
        :arg ssl.SSLContext ssl_options: `ssl.SSLContext` object for use in
           ``simple_httpclient`` (unsupported by ``curl_httpclient``).
           Overrides ``validate_cert``, ``ca_certs``, ``client_key``,
           and ``client_cert``.
        :arg bool allow_ipv6: Use IPv6 when available?  Default is true.
        :arg bool expect_100_continue: If true, send the
           ``Expect: 100-continue`` header and wait for a continue response
           before sending the request body.  Only supported with
           simple_httpclient.

        .. note::

            When using ``curl_httpclient`` certain options may be
            inherited by subsequent fetches because ``pycurl`` does
            not allow them to be cleanly reset.  This applies to the
            ``ca_certs``, ``client_key``, ``client_cert``, and
            ``network_interface`` arguments.  If you use these
            options, you should pass them on every request (you don't
            have to always use the same values, but it's not possible
            to mix requests that specify these options with ones that
            use the defaults).

        .. versionadded:: 3.1
           The ``auth_mode`` argument.

        .. versionadded:: 4.0
           The ``body_producer`` and ``expect_100_continue`` arguments.

        .. versionadded:: 4.2
           The ``ssl_options`` argument.
        """
        # Note that some of these attributes go through property setters
        # defined below.
        self.headers = headers
        if if_modified_since:
            self.headers["If-Modified-Since"] = httputil.format_timestamp(
                if_modified_since)
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.proxy_username = proxy_username
        self.proxy_password = proxy_password
        self.url = url
        self.method = method
        self.body = body
        self.body_producer = body_producer
        self.auth_username = auth_username
        self.auth_password = auth_password
        self.auth_mode = auth_mode
        self.connect_timeout = connect_timeout
        self.request_timeout = request_timeout
        self.follow_redirects = follow_redirects
        self.max_redirects = max_redirects
        self.user_agent = user_agent
        if decompress_response is not None:
            self.decompress_response = decompress_response
        else:
            self.decompress_response = use_gzip
        self.network_interface = network_interface
        self.streaming_callback = streaming_callback
        self.header_callback = header_callback
        self.prepare_curl_callback = prepare_curl_callback
        self.allow_nonstandard_methods = allow_nonstandard_methods
        self.validate_cert = validate_cert
        self.ca_certs = ca_certs
        self.allow_ipv6 = allow_ipv6
        self.client_key = client_key
        self.client_cert = client_cert
        self.ssl_options = ssl_options
        self.expect_100_continue = expect_100_continue
        self.start_time = time.time()

    @property
    def headers(self):
        return self._headers

    @headers.setter
    def headers(self, value):
        if value is None:
            self._headers = httputil.HTTPHeaders()
        else:
            self._headers = value

    @property
    def body(self):
        return self._body

    @body.setter
    def body(self, value):
        self._body = utf8(value)

    @property
    def body_producer(self):
        return self._body_producer

    @body_producer.setter
    def body_producer(self, value):
        self._body_producer = stack_context.wrap(value)

    @property
    def streaming_callback(self):
        return self._streaming_callback

    @streaming_callback.setter
    def streaming_callback(self, value):
        self._streaming_callback = stack_context.wrap(value)

    @property
    def header_callback(self):
        return self._header_callback

    @header_callback.setter
    def header_callback(self, value):
        self._header_callback = stack_context.wrap(value)

    @property
    def prepare_curl_callback(self):
        return self._prepare_curl_callback

    @prepare_curl_callback.setter
    def prepare_curl_callback(self, value):
        self._prepare_curl_callback = stack_context.wrap(value)


class HTTPResponse(object):
    """HTTP 响应对象.

    属性:

    * request: HTTPRequest 对象

    * code: numeric HTTP status code, e.g. 200 or 404

    * reason: human-readable reason phrase describing the status code

    * headers: `tornado.httputil.HTTPHeaders` object

    * effective_url: final location of the resource after following any
      redirects

    * buffer: ``cStringIO`` object for response body

    * body: response body as string (created on demand from ``self.buffer``)

    * error: Exception object, if any

    * request_time: seconds from request start to finish

    * time_info: dictionary of diagnostic timing information from the request.
      Available data are subject to change, but currently uses timings
      available from http://curl.haxx.se/libcurl/c/curl_easy_getinfo.html,
      plus ``queue``, which is the delay (if any) introduced by waiting for
      a slot under `AsyncHTTPClient`'s ``max_clients`` setting.
    """
    def __init__(self, request, code, headers=None, buffer=None,
                 effective_url=None, error=None, request_time=None,
                 time_info=None, reason=None):
        if isinstance(request, _RequestProxy):
            self.request = request.request
        else:
            self.request = request
        self.code = code
        self.reason = reason or httputil.responses.get(code, "Unknown")
        if headers is not None:
            self.headers = headers
        else:
            self.headers = httputil.HTTPHeaders()
        self.buffer = buffer
        self._body = None
        if effective_url is None:
            self.effective_url = request.url
        else:
            self.effective_url = effective_url
        if error is None:
            if self.code < 200 or self.code >= 300:
                self.error = HTTPError(self.code, message=self.reason,
                                       response=self)
            else:
                self.error = None
        else:
            self.error = error
        self.request_time = request_time
        self.time_info = time_info or {}

    def _get_body(self):
        if self.buffer is None:
            return None
        elif self._body is None:
            self._body = self.buffer.getvalue()

        return self._body

    body = property(_get_body)

    def rethrow(self):
        """If there was an error on the request, raise an `HTTPError`."""
        if self.error:
            raise self.error

    def __repr__(self):
        args = ",".join("%s=%r" % i for i in sorted(self.__dict__.items()))
        return "%s(%s)" % (self.__class__.__name__, args)


class HTTPError(Exception):
    """一个 HTTP 请求失败后抛出的异常.

    属性:

    * ``code`` - 整数的 HTTP 错误码, e.g. 404. 当没有接收到 HTTP 响应时
      将会使用 599 错误码, e.g. for a timeout.

    * ``response`` - `HTTPResponse` object, if any.

    注意如果 ``follow_redirects`` 为 False, 重定向将导致 HTTPErrors,
    and you can look at ``error.response.headers['Location']`` to see the
    destination of the redirect.
    """
    def __init__(self, code, message=None, response=None):
        self.code = code
        self.message = message or httputil.responses.get(code, "Unknown")
        self.response = response
        super(HTTPError, self).__init__(code, message, response)

    def __str__(self):
        return "HTTP %d: %s" % (self.code, self.message)


class _RequestProxy(object):
    """将对象和默认字典相结合.

    本质上是被 AsyncHTTPClient 的实现使用.
    """
    def __init__(self, request, defaults):
        self.request = request
        self.defaults = defaults

    def __getattr__(self, name):
        request_attr = getattr(self.request, name)
        if request_attr is not None:
            return request_attr
        elif self.defaults is not None:
            return self.defaults.get(name, None)
        else:
            return None


def main():
    from tornado.options import define, options, parse_command_line
    define("print_headers", type=bool, default=False)
    define("print_body", type=bool, default=True)
    define("follow_redirects", type=bool, default=True)
    define("validate_cert", type=bool, default=True)
    args = parse_command_line()
    client = HTTPClient()
    for arg in args:
        try:
            response = client.fetch(arg,
                                    follow_redirects=options.follow_redirects,
                                    validate_cert=options.validate_cert,
                                    )
        except HTTPError as e:
            if e.response is not None:
                response = e.response
            else:
                raise
        if options.print_headers:
            print(response.headers)
        if options.print_body:
            print(native_str(response.body))
    client.close()

if __name__ == "__main__":
    main()
