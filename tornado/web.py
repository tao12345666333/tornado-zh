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

"""``tornado.web`` 提供了一种带有异步功能并允许它扩展到大量开放连接的
简单的web 框架, 使其成为处理 `长连接(long polling)
<http://en.wikipedia.org/wiki/Push_technology#Long_polling>`_ 的一种理想选择.

这里有一个简单的"Hello, world"示例应用:

.. testcode::

    import tornado.ioloop
    import tornado.web

    class MainHandler(tornado.web.RequestHandler):
        def get(self):
            self.write("Hello, world")

    if __name__ == "__main__":
        application = tornado.web.Application([
            (r"/", MainHandler),
        ])
        application.listen(8888)
        tornado.ioloop.IOLoop.current().start()

.. testoutput::
   :hide:


查看 :doc:`guide` 以了解更多信息.

线程安全说明
-------------------

一般情况下, 在 `RequestHandler` 中的方法和Tornado 中其他的方法不是
线程安全的. 尤其是, 一些方法例如 `~RequestHandler.write()`,
`~RequestHandler.finish()`, 和 `~RequestHandler.flush()` 要求只能从
主线程调用. 如果你使用多线程, 那么在结束请求之前, 使用
`.IOLoop.add_callback` 来把控制权传送回主线程是很重要的.

"""

from __future__ import absolute_import, division, print_function, with_statement

import base64
import binascii
import datetime
import email.utils
import functools
import gzip
import hashlib
import hmac
import mimetypes
import numbers
import os.path
import re
import stat
import sys
import threading
import time
import tornado
import traceback
import types
from io import BytesIO

from tornado.concurrent import Future
from tornado import escape
from tornado import gen
from tornado import httputil
from tornado import iostream
from tornado import locale
from tornado.log import access_log, app_log, gen_log
from tornado import stack_context
from tornado import template
from tornado.escape import utf8, _unicode
from tornado.util import (import_object, ObjectDict, raise_exc_info,
                          unicode_type, _websocket_mask)
from tornado.httputil import split_host_and_port


try:
    import Cookie  # py2
except ImportError:
    import http.cookies as Cookie  # py3

try:
    import urlparse  # py2
except ImportError:
    import urllib.parse as urlparse  # py3

try:
    from urllib import urlencode  # py2
except ImportError:
    from urllib.parse import urlencode  # py3


MIN_SUPPORTED_SIGNED_VALUE_VERSION = 1
"""这个Tornado版本所支持的最旧的签名值版本.

比这个签名值更旧的版本将不能被解码.

.. versionadded:: 3.2.1
"""

MAX_SUPPORTED_SIGNED_VALUE_VERSION = 2
"""这个Tornado版本所支持的最新的签名值版本.

比这个签名值更新的版本将不能被解码.

.. versionadded:: 3.2.1
"""

DEFAULT_SIGNED_VALUE_VERSION = 2
"""签名值版本通过 `.RequestHandler.create_signed_value` 产生.

可通过传递一个 ``version`` 关键字参数复写.

.. versionadded:: 3.2.1
"""

DEFAULT_SIGNED_VALUE_MIN_VERSION = 1
"""最旧的可以被 `.RequestHandler.get_secure_cookie` 接受的签名值.

可通过传递一个 ``min_version`` 关键字参数复写.

.. versionadded:: 3.2.1
"""


class RequestHandler(object):
    """HTTP请求处理的基类.

    子类至少应该定义以下"Entry points" 部分中被定义的方法其中之一.
    """
    SUPPORTED_METHODS = ("GET", "HEAD", "POST", "DELETE", "PATCH", "PUT",
                         "OPTIONS")

    _template_loaders = {}  # {path: template.BaseLoader}
    _template_loader_lock = threading.Lock()
    _remove_control_chars_regex = re.compile(r"[\x00-\x08\x0e-\x1f]")

    def __init__(self, application, request, **kwargs):
        super(RequestHandler, self).__init__()

        self.application = application
        self.request = request
        self._headers_written = False
        self._finished = False
        self._auto_finish = True
        self._transforms = None  # will be set in _execute
        self._prepared_future = None
        self.path_args = None
        self.path_kwargs = None
        self.ui = ObjectDict((n, self._ui_method(m)) for n, m in
                             application.ui_methods.items())
        # UIModules are available as both `modules` and `_tt_modules` in the
        # template namespace.  Historically only `modules` was available
        # but could be clobbered by user additions to the namespace.
        # The template {% module %} directive looks in `_tt_modules` to avoid
        # possible conflicts.
        self.ui["_tt_modules"] = _UIModuleNamespace(self,
                                                    application.ui_modules)
        self.ui["modules"] = self.ui["_tt_modules"]
        self.clear()
        self.request.connection.set_close_callback(self.on_connection_close)
        self.initialize(**kwargs)

    def initialize(self):
        """子类初始化(Hook).

        作为url spec的第三个参数传递的字典, 将作为关键字参数提供给
        initialize().

        例子::

            class ProfileHandler(RequestHandler):
                def initialize(self, database):
                    self.database = database

                def get(self, username):
                    ...

            app = Application([
                (r'/user/(.*)', ProfileHandler, dict(database=database)),
                ])
        """
        pass

    @property
    def settings(self):
        """ `self.application.settings <Application.settings>` 的别名."""
        return self.application.settings

    def head(self, *args, **kwargs):
        raise HTTPError(405)

    def get(self, *args, **kwargs):
        raise HTTPError(405)

    def post(self, *args, **kwargs):
        raise HTTPError(405)

    def delete(self, *args, **kwargs):
        raise HTTPError(405)

    def patch(self, *args, **kwargs):
        raise HTTPError(405)

    def put(self, *args, **kwargs):
        raise HTTPError(405)

    def options(self, *args, **kwargs):
        raise HTTPError(405)

    def prepare(self):
        """在每个请求的最开始被调用, 在 `get`/`post`/等方法之前.

        通过复写这个方法, 可以执行共同的初始化, 而不用考虑每个请求方法.

        异步支持: 这个方法使用 `.gen.coroutine` 或 `.return_future`
        装饰器来使它异步( `asynchronous` 装饰器不能被用在 `prepare`).
        如果这个方法返回一个 `.Future` 对象, 执行将不再进行, 直到
        `.Future` 对象完成.

        .. versionadded:: 3.1
           异步支持.
        """
        pass

    def on_finish(self):
        """在一个请求的最后被调用.

        复写这个方法来执行清理, 日志记录等. 这个方法和 `prepare` 是相
        对应的. ``on_finish`` 可能不产生任何输出, 因为它是在响应被送
        到客户端后才被调用.
        """
        pass

    def on_connection_close(self):
        """在异步处理中, 如果客户端关闭了连接将会被调用.

        复写这个方法来清除与长连接相关的资源. 注意这个方法只有当在异步处理
        连接被关闭才会被调用; 如果你需要在每个请求之后做清理, 请复写
        `on_finish` 方法来代替.

        在客户端离开后, 代理可能会保持连接一段时间 (也可能是无限期),
        所以这个方法可能不会被立即执行当终端用户关闭他们的连接.
        """
        if _has_stream_request_body(self.__class__):
            if not self.request.body.done():
                self.request.body.set_exception(iostream.StreamClosedError())
                self.request.body.exception()

    def clear(self):
        """重置这个响应的所有头部和内容."""
        self._headers = httputil.HTTPHeaders({
            "Server": "TornadoServer/%s" % tornado.version,
            "Content-Type": "text/html; charset=UTF-8",
            "Date": httputil.format_timestamp(time.time()),
        })
        self.set_default_headers()
        self._write_buffer = []
        self._status_code = 200
        self._reason = httputil.responses[200]

    def set_default_headers(self):
        """复写这个方法可以在请求开始的时候设置HTTP头.

        例如, 在这里可以设置一个自定义 ``Server`` 头. 注意在一般的
        请求过程流里可能不会实现你预期的效果, 因为头部可能在错误处
        理(error handling)中被重置.
        """
        pass

    def set_status(self, status_code, reason=None):
        """设置响应的状态码.

        :arg int status_code: 响应状态码. 如果 ``reason`` 是 ``None``,
            它必须在 `httplib.responses <http.client.responses>`.
        :arg string reason: 用人类可读的原因短语来描述状态码.
            如果是 ``None``, 它会由来自
            `httplib.responses <http.client.responses>` 的reason填满.
        """
        self._status_code = status_code
        if reason is not None:
            self._reason = escape.native_str(reason)
        else:
            try:
                self._reason = httputil.responses[status_code]
            except KeyError:
                raise ValueError("unknown status code %d", status_code)

    def get_status(self):
        """返回响应的状态码."""
        return self._status_code

    def set_header(self, name, value):
        """给响应设置指定的头部和对应的值.

        如果给定了一个datetime, 我们会根据HTTP 规范自动的对它格式化.
        如果值不是一个字符串, 我们会把它转换成字符串. 之后所有头部的值
        都将用UTF-8 编码.
        """
        self._headers[name] = self._convert_header_value(value)

    def add_header(self, name, value):
        """添加指定的响应头和对应的值.

        不像是 `set_header`, `add_header` 可以被多次调用来为相同的头
        返回多个值.
        """
        self._headers.add(name, self._convert_header_value(value))

    def clear_header(self, name):
        """清除输出头, 取消之前的 `set_header` 调用.

        注意这个方法不适用于被 `add_header` 设置了多个值的头.
        """
        if name in self._headers:
            del self._headers[name]

    _INVALID_HEADER_CHAR_RE = re.compile(br"[\x00-\x1f]")

    def _convert_header_value(self, value):
        if isinstance(value, bytes):
            pass
        elif isinstance(value, unicode_type):
            value = value.encode('utf-8')
        elif isinstance(value, numbers.Integral):
            # return immediately since we know the converted value will be safe
            return str(value)
        elif isinstance(value, datetime.datetime):
            return httputil.format_timestamp(value)
        else:
            raise TypeError("Unsupported header value %r" % value)
        # If \n is allowed into the header, it is possible to inject
        # additional headers or split the request.
        if RequestHandler._INVALID_HEADER_CHAR_RE.search(value):
            raise ValueError("Unsafe header value %r", value)
        return value

    _ARG_DEFAULT = []

    def get_argument(self, name, default=_ARG_DEFAULT, strip=True):
        """返回指定的name参数的值.

        如果没有提供默认值, 那么这个参数将被视为是必须的, 并且当
        找不到这个参数的时候我们会抛出一个 `MissingArgumentError`.

        如果一个在url上出现多次, 我们返回最后一个值.

        返回值永远是unicode.
        """
        return self._get_argument(name, default, self.request.arguments, strip)

    def get_arguments(self, name, strip=True):
        """返回指定name的参数列表.

        如果参数不存在, 返回一个空列表.

        返回值永远是unicode.
        """

        # Make sure `get_arguments` isn't accidentally being called with a
        # positional argument that's assumed to be a default (like in
        # `get_argument`.)
        assert isinstance(strip, bool)

        return self._get_arguments(name, self.request.arguments, strip)

    def get_body_argument(self, name, default=_ARG_DEFAULT, strip=True):
        """返回请求体中指定name的参数的值.

        如果没有提供默认值, 那么这个参数将被视为是必须的, 并且当
        找不到这个参数的时候我们会抛出一个 `MissingArgumentError`.

        如果一个在url上出现多次, 我们返回最后一个值.

        返回值永远是unicode.

        .. versionadded:: 3.2
        """
        return self._get_argument(name, default, self.request.body_arguments,
                                  strip)

    def get_body_arguments(self, name, strip=True):
        """返回由指定请求体中指定name的参数的列表.

        如果参数不存在, 返回一个空列表.

        返回值永远是unicode.

        .. versionadded:: 3.2
        """
        return self._get_arguments(name, self.request.body_arguments, strip)

    def get_query_argument(self, name, default=_ARG_DEFAULT, strip=True):
        """从请求的query string返回给定name的参数的值.

        如果没有提供默认值, 这个参数将被视为必须的, 并且当找不到这个
        参数的时候我们会抛出一个 `MissingArgumentError`.

        如果这个参数在url中多次出现, 我们将返回最后一次的值.

        返回值永远是unicode.

        .. versionadded:: 3.2
        """
        return self._get_argument(name, default,
                                  self.request.query_arguments, strip)

    def get_query_arguments(self, name, strip=True):
        """返回指定name的参数列表.

        如果参数不存在, 将返回空列表.

        返回值永远是unicode.

        .. versionadded:: 3.2
        """
        return self._get_arguments(name, self.request.query_arguments, strip)

    def _get_argument(self, name, default, source, strip=True):
        args = self._get_arguments(name, source, strip=strip)
        if not args:
            if default is self._ARG_DEFAULT:
                raise MissingArgumentError(name)
            return default
        return args[-1]

    def _get_arguments(self, name, source, strip=True):
        values = []
        for v in source.get(name, []):
            v = self.decode_argument(v, name=name)
            if isinstance(v, unicode_type):
                # Get rid of any weird control chars (unless decoding gave
                # us bytes, in which case leave it alone)
                v = RequestHandler._remove_control_chars_regex.sub(" ", v)
            if strip:
                v = v.strip()
            values.append(v)
        return values

    def decode_argument(self, value, name=None):
        """从请求中解码一个参数.

        这个参数已经被解码现在是一个字节字符串(byte string) . 默认情况下,
        这个方法会把参数解码成utf-8 并且返回一个unicode 字符串, 但是它可以
        被子类复写.

        这个方法既可以在 `get_argument()` 中被用作过滤器, 也可以用来从url
        总提取值并传递给 `get()`/`post()`/等.

        如果知道的话可以提供参数的name, 但是可能会为None
        (e.g. 在url正则表达式中未命名的组).
        """
        try:
            return _unicode(value)
        except UnicodeDecodeError:
            raise HTTPError(400, "Invalid unicode in %s: %r" %
                            (name or "url", value[:40]))

    @property
    def cookies(self):
        """ `self.request.cookies <.httputil.HTTPServerRequest.cookies>`
        的别名."""
        return self.request.cookies

    def get_cookie(self, name, default=None):
        """获取给定name的cookie值, 未获取到则返回默认值."""
        if self.request.cookies is not None and name in self.request.cookies:
            return self.request.cookies[name].value
        return default

    def set_cookie(self, name, value, domain=None, expires=None, path="/",
                   expires_days=None, **kwargs):
        """设置给定的cookie 名称/值还有给定的选项.

        另外的关键字参数在Cookie.Morsel直接设置.
        参见 http://docs.python.org/library/cookie.html#morsel-objects
        查看可用的属性.
        """
        # The cookie library only accepts type str, in both python 2 and 3
        name = escape.native_str(name)
        value = escape.native_str(value)
        if re.search(r"[\x00-\x20]", name + value):
            # Don't let us accidentally inject bad stuff
            raise ValueError("Invalid cookie %r: %r" % (name, value))
        if not hasattr(self, "_new_cookie"):
            self._new_cookie = Cookie.SimpleCookie()
        if name in self._new_cookie:
            del self._new_cookie[name]
        self._new_cookie[name] = value
        morsel = self._new_cookie[name]
        if domain:
            morsel["domain"] = domain
        if expires_days is not None and not expires:
            expires = datetime.datetime.utcnow() + datetime.timedelta(
                days=expires_days)
        if expires:
            morsel["expires"] = httputil.format_timestamp(expires)
        if path:
            morsel["path"] = path
        for k, v in kwargs.items():
            if k == 'max_age':
                k = 'max-age'

            # skip falsy values for httponly and secure flags because
            # SimpleCookie sets them regardless
            if k in ['httponly', 'secure'] and not v:
                continue

            morsel[k] = v

    def clear_cookie(self, name, path="/", domain=None):
        """删除给定名称的cookie.

        受cookie协议的限制, 必须传递和设置该名称cookie时候相同的path
        和domain来清除这个cookie(但是这里没有方法来找出在服务端所使
        用的给定cookie的值).
        """
        expires = datetime.datetime.utcnow() - datetime.timedelta(days=365)
        self.set_cookie(name, value="", path=path, expires=expires,
                        domain=domain)

    def clear_all_cookies(self, path="/", domain=None):
        """删除用户在本次请求中所有携带的cookie.

        查看 `clear_cookie` 方法来获取关于path和domain参数的更多信息.

        .. versionchanged:: 3.2

           添加 ``path`` 和 ``domain`` 参数.
        """
        for name in self.request.cookies:
            self.clear_cookie(name, path=path, domain=domain)

    def set_secure_cookie(self, name, value, expires_days=30, version=None,
                          **kwargs):
        """给cookie签名和时间戳以防被伪造.

        你必须在你的Application设置中指定 ``cookie_secret`` 来使用这个方法.
        它应该是一个长的, 字节随机序列作为HMAC 密钥来做签名.

        使用 `get_secure_cookie()` 方法来阅读通过这个方法设置的cookie.

        注意 ``expires_days`` 参数设置cookie在浏览器中的有效期, 并且它是
        独立于 `get_secure_cookie` 的 ``max_age_days`` 参数的.

        安全cookie(Secure cookies)可以包含任意的字节的值, 而不只是unicode
        字符串(不像是普通cookie)

        .. versionchanged:: 3.2.1

           添加 ``version`` 参数. 提出cookie version 2
           并将它作为默认设置.
        """
        self.set_cookie(name, self.create_signed_value(name, value,
                                                       version=version),
                        expires_days=expires_days, **kwargs)

    def create_signed_value(self, name, value, version=None):
        """产生用时间戳签名的字符串, 防止被伪造.

        一般通过set_secure_cookie 使用, 但对于无cookie使用来说就
        作为独立的方法来提供. 为了解码不作为cookie存储的值, 可以
        在 get_secure_cookie 使用可选的value参数.

        .. versionchanged:: 3.2.1

           添加 ``version`` 参数. 提出cookie version 2
           并将它作为默认设置.
        """
        self.require_setting("cookie_secret", "secure cookies")
        secret = self.application.settings["cookie_secret"]
        key_version = None
        if isinstance(secret, dict):
            if self.application.settings.get("key_version") is None:
                raise Exception("key_version setting must be used for secret_key dicts")
            key_version = self.application.settings["key_version"]

        return create_signed_value(secret, name, value, version=version,
                                   key_version=key_version)

    def get_secure_cookie(self, name, value=None, max_age_days=31,
                          min_version=None):
        """如果给定的签名过的cookie是有效的,则返回，否则返回None.

        解码后的cookie值作为字节字符串返回(不像 `get_cookie` ).

        .. versionchanged:: 3.2.1

           添加 ``min_version`` 参数. 引进cookie version 2;
           默认版本 1 和 2 都可以接受.
        """
        self.require_setting("cookie_secret", "secure cookies")
        if value is None:
            value = self.get_cookie(name)
        return decode_signed_value(self.application.settings["cookie_secret"],
                                   name, value, max_age_days=max_age_days,
                                   min_version=min_version)

    def get_secure_cookie_key_version(self, name, value=None):
        """返回安全cookie(secure cookie)的签名key版本.

        返回的版本号是int型的.
        """
        self.require_setting("cookie_secret", "secure cookies")
        if value is None:
            value = self.get_cookie(name)
        return get_signature_key_version(value)

    def redirect(self, url, permanent=False, status=None):
        """重定向到给定的URL(可以选择相对路径).

        如果指定了 ``status`` 参数, 这个值将作为HTTP状态码; 否则
        将通过 ``permanent`` 参数选择301 (永久) 或者 302 (临时).
        默认是 302 (临时重定向).
        """
        if self._headers_written:
            raise Exception("Cannot redirect after headers have been written")
        if status is None:
            status = 301 if permanent else 302
        else:
            assert isinstance(status, int) and 300 <= status <= 399
        self.set_status(status)
        self.set_header("Location", utf8(url))
        self.finish()

    def write(self, chunk):
        """把给定块写到输出buffer.

        为了把输出写到网络, 使用下面的flush() 方法.

        如果给定的块是一个字典, 我们会把它作为JSON来写同时会把响应头
        设置为 ``application/json``. (如果你写JSON但是设置不同的
        ``Content-Type``,  可以调用 set_header *在调用write() 之后* ).

        注意列表不能转换为JSON 因为一个潜在的跨域安全漏洞. 所有的JSON
        输出应该包在一个字典中. 更多细节参考
        http://haacked.com/archive/2009/06/25/json-hijacking.aspx/ 和
        https://github.com/facebook/tornado/issues/1009
        """
        if self._finished:
            raise RuntimeError("Cannot write() after finish()")
        if not isinstance(chunk, (bytes, unicode_type, dict)):
            message = "write() only accepts bytes, unicode, and dict objects"
            if isinstance(chunk, list):
                message += ". Lists not accepted for security reasons; see http://www.tornadoweb.org/en/stable/web.html#tornado.web.RequestHandler.write"
            raise TypeError(message)
        if isinstance(chunk, dict):
            chunk = escape.json_encode(chunk)
            self.set_header("Content-Type", "application/json; charset=UTF-8")
        chunk = utf8(chunk)
        self._write_buffer.append(chunk)

    def render(self, template_name, **kwargs):
        """使用给定参数渲染模板并作为响应."""
        html = self.render_string(template_name, **kwargs)

        # Insert the additional JS and CSS added by the modules on the page
        js_embed = []
        js_files = []
        css_embed = []
        css_files = []
        html_heads = []
        html_bodies = []
        for module in getattr(self, "_active_modules", {}).values():
            embed_part = module.embedded_javascript()
            if embed_part:
                js_embed.append(utf8(embed_part))
            file_part = module.javascript_files()
            if file_part:
                if isinstance(file_part, (unicode_type, bytes)):
                    js_files.append(file_part)
                else:
                    js_files.extend(file_part)
            embed_part = module.embedded_css()
            if embed_part:
                css_embed.append(utf8(embed_part))
            file_part = module.css_files()
            if file_part:
                if isinstance(file_part, (unicode_type, bytes)):
                    css_files.append(file_part)
                else:
                    css_files.extend(file_part)
            head_part = module.html_head()
            if head_part:
                html_heads.append(utf8(head_part))
            body_part = module.html_body()
            if body_part:
                html_bodies.append(utf8(body_part))

        def is_absolute(path):
            return any(path.startswith(x) for x in ["/", "http:", "https:"])
        if js_files:
            # Maintain order of JavaScript files given by modules
            paths = []
            unique_paths = set()
            for path in js_files:
                if not is_absolute(path):
                    path = self.static_url(path)
                if path not in unique_paths:
                    paths.append(path)
                    unique_paths.add(path)
            js = ''.join('<script src="' + escape.xhtml_escape(p) +
                         '" type="text/javascript"></script>'
                         for p in paths)
            sloc = html.rindex(b'</body>')
            html = html[:sloc] + utf8(js) + b'\n' + html[sloc:]
        if js_embed:
            js = b'<script type="text/javascript">\n//<![CDATA[\n' + \
                b'\n'.join(js_embed) + b'\n//]]>\n</script>'
            sloc = html.rindex(b'</body>')
            html = html[:sloc] + js + b'\n' + html[sloc:]
        if css_files:
            paths = []
            unique_paths = set()
            for path in css_files:
                if not is_absolute(path):
                    path = self.static_url(path)
                if path not in unique_paths:
                    paths.append(path)
                    unique_paths.add(path)
            css = ''.join('<link href="' + escape.xhtml_escape(p) + '" '
                          'type="text/css" rel="stylesheet"/>'
                          for p in paths)
            hloc = html.index(b'</head>')
            html = html[:hloc] + utf8(css) + b'\n' + html[hloc:]
        if css_embed:
            css = b'<style type="text/css">\n' + b'\n'.join(css_embed) + \
                b'\n</style>'
            hloc = html.index(b'</head>')
            html = html[:hloc] + css + b'\n' + html[hloc:]
        if html_heads:
            hloc = html.index(b'</head>')
            html = html[:hloc] + b''.join(html_heads) + b'\n' + html[hloc:]
        if html_bodies:
            hloc = html.index(b'</body>')
            html = html[:hloc] + b''.join(html_bodies) + b'\n' + html[hloc:]
        self.finish(html)

    def render_string(self, template_name, **kwargs):
        """使用给定的参数生成指定模板.

        我们返回生成的字节字符串(以utf8). 为了生成并写一个模板
        作为响应, 使用上面的render().
        """
        # If no template_path is specified, use the path of the calling file
        template_path = self.get_template_path()
        if not template_path:
            frame = sys._getframe(0)
            web_file = frame.f_code.co_filename
            while frame.f_code.co_filename == web_file:
                frame = frame.f_back
            template_path = os.path.dirname(frame.f_code.co_filename)
        with RequestHandler._template_loader_lock:
            if template_path not in RequestHandler._template_loaders:
                loader = self.create_template_loader(template_path)
                RequestHandler._template_loaders[template_path] = loader
            else:
                loader = RequestHandler._template_loaders[template_path]
        t = loader.load(template_name)
        namespace = self.get_template_namespace()
        namespace.update(kwargs)
        return t.generate(**namespace)

    def get_template_namespace(self):
        """返回一个字典被用做默认的模板命名空间.

        可以被子类复写来添加或修改值.

        这个方法的结果将与 `tornado.template` 模块中其他的默认值
        还有 `render` 或 `render_string` 的关键字参数相结合.
        """
        namespace = dict(
            handler=self,
            request=self.request,
            current_user=self.current_user,
            locale=self.locale,
            _=self.locale.translate,
            pgettext=self.locale.pgettext,
            static_url=self.static_url,
            xsrf_form_html=self.xsrf_form_html,
            reverse_url=self.reverse_url
        )
        namespace.update(self.ui)
        return namespace

    def create_template_loader(self, template_path):
        """返回给定路径的新模板装载器.

        可以被子类复写. 默认返回一个在给定路径上基于目录的装载器,
        使用应用程序的 ``autoescape`` 和 ``template_whitespace``
        设置. 如果应用设置中提供了一个 ``template_loader`` ,
        则使用它来替代.
        """
        settings = self.application.settings
        if "template_loader" in settings:
            return settings["template_loader"]
        kwargs = {}
        if "autoescape" in settings:
            # autoescape=None means "no escaping", so we have to be sure
            # to only pass this kwarg if the user asked for it.
            kwargs["autoescape"] = settings["autoescape"]
        if "template_whitespace" in settings:
            kwargs["whitespace"] = settings["template_whitespace"]
        return template.Loader(template_path, **kwargs)

    def flush(self, include_footers=False, callback=None):
        """将当前输出缓冲区写到网络.

        ``callback`` 参数, 如果给定, 可用于流控制: 它会在所有数据被写到
        socket后执行. 注意同一时间只能有一个flush callback停留; 如果另
        一个flush在前一个flush的callback运行之前发生, 那么前一个callback
        将会被丢弃.

        .. versionchanged:: 4.0
           现在如果没有给定callback, 会返回一个 `.Future` 对象.
        """
        chunk = b"".join(self._write_buffer)
        self._write_buffer = []
        if not self._headers_written:
            self._headers_written = True
            for transform in self._transforms:
                self._status_code, self._headers, chunk = \
                    transform.transform_first_chunk(
                        self._status_code, self._headers,
                        chunk, include_footers)
            # Ignore the chunk and only write the headers for HEAD requests
            if self.request.method == "HEAD":
                chunk = None

            # Finalize the cookie headers (which have been stored in a side
            # object so an outgoing cookie could be overwritten before it
            # is sent).
            if hasattr(self, "_new_cookie"):
                for cookie in self._new_cookie.values():
                    self.add_header("Set-Cookie", cookie.OutputString(None))

            start_line = httputil.ResponseStartLine('',
                                                    self._status_code,
                                                    self._reason)
            return self.request.connection.write_headers(
                start_line, self._headers, chunk, callback=callback)
        else:
            for transform in self._transforms:
                chunk = transform.transform_chunk(chunk, include_footers)
            # Ignore the chunk and only write the headers for HEAD requests
            if self.request.method != "HEAD":
                return self.request.connection.write(chunk, callback=callback)
            else:
                future = Future()
                future.set_result(None)
                return future

    def finish(self, chunk=None):
        """完成响应, 结束HTTP 请求."""
        if self._finished:
            raise RuntimeError("finish() called twice")

        if chunk is not None:
            self.write(chunk)

        # Automatically support ETags and add the Content-Length header if
        # we have not flushed any content yet.
        if not self._headers_written:
            if (self._status_code == 200 and
                self.request.method in ("GET", "HEAD") and
                    "Etag" not in self._headers):
                self.set_etag_header()
                if self.check_etag_header():
                    self._write_buffer = []
                    self.set_status(304)
            if self._status_code == 304:
                assert not self._write_buffer, "Cannot send body with 304"
                self._clear_headers_for_304()
            elif "Content-Length" not in self._headers:
                content_length = sum(len(part) for part in self._write_buffer)
                self.set_header("Content-Length", content_length)

        if hasattr(self.request, "connection"):
            # Now that the request is finished, clear the callback we
            # set on the HTTPConnection (which would otherwise prevent the
            # garbage collection of the RequestHandler when there
            # are keepalive connections)
            self.request.connection.set_close_callback(None)

        self.flush(include_footers=True)
        self.request.finish()
        self._log()
        self._finished = True
        self.on_finish()
        # Break up a reference cycle between this handler and the
        # _ui_module closures to allow for faster GC on CPython.
        self.ui = None

    def send_error(self, status_code=500, **kwargs):
        """给浏览器发送给定的HTTP 错误码.

        如果 `flush()` 已经被调用, 它是不可能发送错误的, 所以这个方法将终止
        响应. 如果输出已经被写但尚未flush, 它将被丢弃并被错误页代替.

        复写 `write_error()` 来自定义它返回的错误页. 额外的关键字参数将
        被传递给 `write_error`.
        """
        if self._headers_written:
            gen_log.error("Cannot send error response after headers written")
            if not self._finished:
                # If we get an error between writing headers and finishing,
                # we are unlikely to be able to finish due to a
                # Content-Length mismatch. Try anyway to release the
                # socket.
                try:
                    self.finish()
                except Exception:
                    gen_log.error("Failed to flush partial response",
                                  exc_info=True)
            return
        self.clear()

        reason = kwargs.get('reason')
        if 'exc_info' in kwargs:
            exception = kwargs['exc_info'][1]
            if isinstance(exception, HTTPError) and exception.reason:
                reason = exception.reason
        self.set_status(status_code, reason=reason)
        try:
            self.write_error(status_code, **kwargs)
        except Exception:
            app_log.error("Uncaught exception in write_error", exc_info=True)
        if not self._finished:
            self.finish()

    def write_error(self, status_code, **kwargs):
        """复写这个方法来实现自定义错误页.

        ``write_error`` 可能调用 `write`, `render`, `set_header`,等
        来产生一般的输出.

        如果错误是由未捕获的异常造成的(包括HTTPError), 三个一组的
        ``exc_info`` 将变成可用的通过 ``kwargs["exc_info"]``.
        注意这个异常可能不是"当前(current)" 目的或方法的异常就像
        ``sys.exc_info()`` 或 ``traceback.format_exc``.
        """
        if self.settings.get("serve_traceback") and "exc_info" in kwargs:
            # in debug mode, try to send a traceback
            self.set_header('Content-Type', 'text/plain')
            for line in traceback.format_exception(*kwargs["exc_info"]):
                self.write(line)
            self.finish()
        else:
            self.finish("<html><title>%(code)d: %(message)s</title>"
                        "<body>%(code)d: %(message)s</body></html>" % {
                            "code": status_code,
                            "message": self._reason,
                        })

    @property
    def locale(self):
        """返回当前session的位置.

        通过 `get_user_locale` 来确定, 你可以复写这个方法设置
        获取locale的条件, e.g., 记录在数据库中的用户偏好, 或
        `get_browser_locale`, 使用 ``Accept-Language`` 头部.

        .. versionchanged: 4.1
           添加setter属性.
        """
        if not hasattr(self, "_locale"):
            self._locale = self.get_user_locale()
            if not self._locale:
                self._locale = self.get_browser_locale()
                assert self._locale
        return self._locale

    @locale.setter
    def locale(self, value):
        self._locale = value

    def get_user_locale(self):
        """复写这个方法确定认证过的用户所在位置.

        如果返回了None , 我们退回选择 `get_browser_locale()`.

        这个方法应该返回一个 `tornado.locale.Locale` 对象,
        就像调用 ``tornado.locale.get("en")`` 得到的那样
        """
        return None

    def get_browser_locale(self, default="en_US"):
        """从 ``Accept-Language`` 头决定用户的位置.

        参考 http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.4
        """
        if "Accept-Language" in self.request.headers:
            languages = self.request.headers["Accept-Language"].split(",")
            locales = []
            for language in languages:
                parts = language.strip().split(";")
                if len(parts) > 1 and parts[1].startswith("q="):
                    try:
                        score = float(parts[1][2:])
                    except (ValueError, TypeError):
                        score = 0.0
                else:
                    score = 1.0
                locales.append((parts[0], score))
            if locales:
                locales.sort(key=lambda pair: pair[1], reverse=True)
                codes = [l[0] for l in locales]
                return locale.get(*codes)
        return locale.get(default)

    @property
    def current_user(self):
        """返回请求中被认证的用户.

        可以使用以下两者之一的方式来设置:

        * 子类可以复写 `get_current_user()`, 这将会在第一次访问
          ``self.current_user`` 时自动被调用.
          `get_current_user()` 在每次请求时只会被调用一次, 并为
          将来访问做缓存::

              def get_current_user(self):
                  user_cookie = self.get_secure_cookie("user")
                  if user_cookie:
                      return json.loads(user_cookie)
                  return None

        * 它可以被设置为一个普通的变量, 通常在来自被复写的 `prepare()`::

              @gen.coroutine
              def prepare(self):
                  user_id_cookie = self.get_secure_cookie("user_id")
                  if user_id_cookie:
                      self.current_user = yield load_user(user_id_cookie)

        注意 `prepare()` 可能是一个协程, 尽管 `get_current_user()`
        可能不是, 所以后面的形式是必要的如果加载用户需要异步操作.

        用户对象可以是任意application选择的类型.
        """
        if not hasattr(self, "_current_user"):
            self._current_user = self.get_current_user()
        return self._current_user

    @current_user.setter
    def current_user(self, value):
        self._current_user = value

    def get_current_user(self):
        """复写来实现获取当前用户, e.g., 从cookie得到.

        这个方法可能不是一个协程.
        """
        return None

    def get_login_url(self):
        """复写这个方法自定义基于请求的登陆URL.

        默认情况下, 我们使用application设置中的 ``login_url`` 值.
        """
        self.require_setting("login_url", "@tornado.web.authenticated")
        return self.application.settings["login_url"]

    def get_template_path(self):
        """可以复写给每个handler指定自定义模板路径.

        默认情况下, 我们使用应用设置中的 ``template_path`` . 返回
        None相对于调用文件来加载模板.
        """
        return self.application.settings.get("template_path")

    @property
    def xsrf_token(self):
        """当前用户/会话的XSRF-prevention token.

        为了防止伪造跨站请求, 我们设置一个 '_xsrf' cookie 并在所有POST
        请求中包含相同的 '_xsrf' 值作为一个参数. 如果这两个不匹配,
        我们会把这个提交当作潜在的伪造请求而拒绝掉.

        查看 http://en.wikipedia.org/wiki/Cross-site_request_forgery

        .. versionchanged:: 3.2.2
           该xsrf token现在已经在每个请求都有一个随机mask这使得它
           可以简洁的把token包含在页面中是安全的. 查看
           http://breachattack.com 浏览更多信息关于这个更改修复的
           问题. 旧(版本1)cookies 将被转换到版本2 当这个方法被调用
           除非 ``xsrf_cookie_version`` `Application` 被设置为1.

        .. versionchanged:: 4.3
           该 ``xsrf_cookie_kwargs`` `Application` 设置可能被用来
           补充额外的cookie 选项(将会直接传递给 `set_cookie`).
           例如, ``xsrf_cookie_kwargs=dict(httponly=True, secure=True)``
           将设置 ``secure`` 和 ``httponly`` 标志在 ``_xsrf`` cookie.
        """
        if not hasattr(self, "_xsrf_token"):
            version, token, timestamp = self._get_raw_xsrf_token()
            output_version = self.settings.get("xsrf_cookie_version", 2)
            cookie_kwargs = self.settings.get("xsrf_cookie_kwargs", {})
            if output_version == 1:
                self._xsrf_token = binascii.b2a_hex(token)
            elif output_version == 2:
                mask = os.urandom(4)
                self._xsrf_token = b"|".join([
                    b"2",
                    binascii.b2a_hex(mask),
                    binascii.b2a_hex(_websocket_mask(mask, token)),
                    utf8(str(int(timestamp)))])
            else:
                raise ValueError("unknown xsrf cookie version %d",
                                 output_version)
            if version is None:
                expires_days = 30 if self.current_user else None
                self.set_cookie("_xsrf", self._xsrf_token,
                                expires_days=expires_days,
                                **cookie_kwargs)
        return self._xsrf_token

    def _get_raw_xsrf_token(self):
        """读取或生成xsrf token 用它原本的格式.

        该raw_xsrf_token是一个tuple 包含:

        * version: 读到这个token的cookie的版本,或None如果我们在该请求
          中生成一个新token.
        * token: 原生的token数据; 随机(non-ascii) bytes.
        * timestamp: 该token生成的时间(对于版本1的cookie将不准确)
        """
        if not hasattr(self, '_raw_xsrf_token'):
            cookie = self.get_cookie("_xsrf")
            if cookie:
                version, token, timestamp = self._decode_xsrf_token(cookie)
            else:
                version, token, timestamp = None, None, None
            if token is None:
                version = None
                token = os.urandom(16)
                timestamp = time.time()
            self._raw_xsrf_token = (version, token, timestamp)
        return self._raw_xsrf_token

    def _decode_xsrf_token(self, cookie):
        """把_get_raw_xsrf_token返回的cookie字符串转换成元组形式.
        """

        try:
            m = _signed_value_version_re.match(utf8(cookie))

            if m:
                version = int(m.group(1))
                if version == 2:
                    _, mask, masked_token, timestamp = cookie.split("|")

                    mask = binascii.a2b_hex(utf8(mask))
                    token = _websocket_mask(
                        mask, binascii.a2b_hex(utf8(masked_token)))
                    timestamp = int(timestamp)
                    return version, token, timestamp
                else:
                    # Treat unknown versions as not present instead of failing.
                    raise Exception("Unknown xsrf cookie version")
            else:
                version = 1
                try:
                    token = binascii.a2b_hex(utf8(cookie))
                except (binascii.Error, TypeError):
                    token = utf8(cookie)
                # We don't have a usable timestamp in older versions.
                timestamp = int(time.time())
                return (version, token, timestamp)
        except Exception:
            # Catch exceptions and return nothing instead of failing.
            gen_log.debug("Uncaught exception in _decode_xsrf_token",
                          exc_info=True)
            return None, None, None

    def check_xsrf_cookie(self):
        """确认 ``_xsrf`` cookie 匹配 ``_xsrf`` 参数.

        为了预防cross-site请求伪造, 我们设置一个 ``_xsrf``
        cookie和包含相同值的一个non-cookie字段在所有
        ``POST`` 请求中. 如果这两个不匹配, 我们拒绝这个
        表单提交作为一个潜在的伪造请求.

        ``_xsrf`` 的值可以被设置为一个名为 ``_xsrf`` 的表单字段或
        在一个名为 ``X-XSRFToken`` 或 ``X-CSRFToken`` 的自定义
        HTTP头部(后者被接受为了兼容Django).

        查看 http://en.wikipedia.org/wiki/Cross-site_request_forgery

        发布1.1.1 之前, 这个检查会被忽略如果当前的HTTP头部是
        ``X-Requested-With: XMLHTTPRequest`` . 这个异常已被证明是
        不安全的并且已经被移除. 更多信息请查看
        http://www.djangoproject.com/weblog/2011/feb/08/security/
        http://weblog.rubyonrails.org/2011/2/8/csrf-protection-bypass-in-ruby-on-rails

        .. versionchanged:: 3.2.2
           添加cookie 2版本的支持. 支持版本1和2.
        """
        token = (self.get_argument("_xsrf", None) or
                 self.request.headers.get("X-Xsrftoken") or
                 self.request.headers.get("X-Csrftoken"))
        if not token:
            raise HTTPError(403, "'_xsrf' argument missing from POST")
        _, token, _ = self._decode_xsrf_token(token)
        _, expected_token, _ = self._get_raw_xsrf_token()
        if not _time_independent_equals(utf8(token), utf8(expected_token)):
            raise HTTPError(403, "XSRF cookie does not match POST argument")

    def xsrf_form_html(self):
        """一个将被包含在所有POST表单中的HTML ``<input/>`` 标签.

        它定义了我们在所有POST请求中为了预防伪造跨站请求所检查的
        ``_xsrf`` 的输入值. 如果你设置了 ``xsrf_cookies`` application设置,
        你必须包含这个HTML 在你所有的HTML表单.

        在一个模板中, 这个方法应该使用 ``{% module xsrf_form_html() %}``
        这种方式调用

        查看上面的 `check_xsrf_cookie()` 了解更多信息.
        """
        return '<input type="hidden" name="_xsrf" value="' + \
            escape.xhtml_escape(self.xsrf_token) + '"/>'

    def static_url(self, path, include_host=None, **kwargs):
        """为给定的相对路径的静态文件返回一个静态URL.

        这个方法需要你在你的应用中设置 ``static_path`` (既你
        静态文件的根目录).

        这个方法返回一个带有版本的url (默认情况下会添加
        ``?v=<signature>``), 这会允许静态文件被无限期缓存. 这可以被
        禁用通过传递 ``include_version=False`` (默认已经实现;
        其他静态文件的实现不需要支持这一点, 但它们可能支持其他选项).

        默认情况下这个方法返回当前host的相对URL, 但是如果
        ``include_host`` 为true则返回的将是绝对路径的URL.
        如果这个处理函数有一个 ``include_host`` 属性, 该值将被所有的
        `static_url` 调用默认使用, 而不需要传递 ``include_host``
        作为一个关键字参数.

        """
        self.require_setting("static_path", "static_url")
        get_url = self.settings.get("static_handler_class",
                                    StaticFileHandler).make_static_url

        if include_host is None:
            include_host = getattr(self, "include_host", False)

        if include_host:
            base = self.request.protocol + "://" + self.request.host
        else:
            base = ""

        return base + get_url(self.settings, path, **kwargs)

    def require_setting(self, name, feature="this feature"):
        """如果给定的app设置未定义则抛出一个异常."""
        if not self.application.settings.get(name):
            raise Exception("You must define the '%s' setting in your "
                            "application to use %s" % (name, feature))

    def reverse_url(self, name, *args):
        """ `Application.reverse_url` 的别名."""
        return self.application.reverse_url(name, *args)

    def compute_etag(self):
        """计算被用于这个请求的etag头.

        到目前为止默认使用输出内容的hash值.

        可以被复写来提供自定义的etag实现, 或者可以返回None来禁止
        tornado 默认的etag支持.
        """
        hasher = hashlib.sha1()
        for part in self._write_buffer:
            hasher.update(part)
        return '"%s"' % hasher.hexdigest()

    def set_etag_header(self):
        """设置响应的Etag头使用 ``self.compute_etag()`` 计算.

        注意: 如果 ``compute_etag()`` 返回 ``None`` 将不会设置头.

        这个方法在请求结束的时候自动调用.
        """
        etag = self.compute_etag()
        if etag is not None:
            self.set_header("Etag", etag)

    def check_etag_header(self):
        """针对请求的 ``If-None-Match`` 头检查 ``Etag`` 头.

        如果请求的ETag 匹配则返回 ``True`` 并将返回一个304. 例如::

            self.set_etag_header()
            if self.check_etag_header():
                self.set_status(304)
                return

        这个方法在请求结束的时候会被自动调用, 但也可以被更早的调用
        当复写了 `compute_etag` 并且想在请求完成之前先做一个
        ``If-None-Match`` 检查. ``Etag`` 头应该在这个方法被调用前设置
        (可以使用 `set_etag_header`).
        """
        computed_etag = utf8(self._headers.get("Etag", ""))
        # Find all weak and strong etag values from If-None-Match header
        # because RFC 7232 allows multiple etag values in a single header.
        etags = re.findall(
            br'\*|(?:W/)?"[^"]*"',
            utf8(self.request.headers.get("If-None-Match", ""))
        )
        if not computed_etag or not etags:
            return False

        match = False
        if etags[0] == b'*':
            match = True
        else:
            # Use a weak comparison when comparing entity-tags.
            val = lambda x: x[2:] if x.startswith(b'W/') else x
            for etag in etags:
                if val(etag) == val(computed_etag):
                    match = True
                    break
        return match

    def _stack_context_handle_exception(self, type, value, traceback):
        try:
            # For historical reasons _handle_request_exception only takes
            # the exception value instead of the full triple,
            # so re-raise the exception to ensure that it's in
            # sys.exc_info()
            raise_exc_info((type, value, traceback))
        except Exception:
            self._handle_request_exception(value)
        return True

    @gen.coroutine
    def _execute(self, transforms, *args, **kwargs):
        """使用给定的输出转换器执行这个请求."""
        self._transforms = transforms
        try:
            if self.request.method not in self.SUPPORTED_METHODS:
                raise HTTPError(405)
            self.path_args = [self.decode_argument(arg) for arg in args]
            self.path_kwargs = dict((k, self.decode_argument(v, name=k))
                                    for (k, v) in kwargs.items())
            # If XSRF cookies are turned on, reject form submissions without
            # the proper cookie
            if self.request.method not in ("GET", "HEAD", "OPTIONS") and \
                    self.application.settings.get("xsrf_cookies"):
                self.check_xsrf_cookie()

            result = self.prepare()
            if result is not None:
                result = yield result
            if self._prepared_future is not None:
                # Tell the Application we've finished with prepare()
                # and are ready for the body to arrive.
                self._prepared_future.set_result(None)
            if self._finished:
                return

            if _has_stream_request_body(self.__class__):
                # In streaming mode request.body is a Future that signals
                # the body has been completely received.  The Future has no
                # result; the data has been passed to self.data_received
                # instead.
                try:
                    yield self.request.body
                except iostream.StreamClosedError:
                    return

            method = getattr(self, self.request.method.lower())
            result = method(*self.path_args, **self.path_kwargs)
            if result is not None:
                result = yield result
            if self._auto_finish and not self._finished:
                self.finish()
        except Exception as e:
            try:
                self._handle_request_exception(e)
            except Exception:
                app_log.error("Exception in exception handler", exc_info=True)
            if (self._prepared_future is not None and
                    not self._prepared_future.done()):
                # In case we failed before setting _prepared_future, do it
                # now (to unblock the HTTP server).  Note that this is not
                # in a finally block to avoid GC issues prior to Python 3.4.
                self._prepared_future.set_result(None)

    def data_received(self, chunk):
        """实现这个方法来处理请求数据流.

        需要 `.stream_request_body` 装饰器.
        """
        raise NotImplementedError()

    def _log(self):
        """记录当前请求.

        可以说这是过时的因为这个功能已经被移动到了Application, 留在这里
        是为了兼容已经复写这个方法的现有app.
        """
        self.application.log_request(self)

    def _request_summary(self):
        return "%s %s (%s)" % (self.request.method, self.request.uri,
                               self.request.remote_ip)

    def _handle_request_exception(self, e):
        if isinstance(e, Finish):
            # Not an error; just finish the request without logging.
            if not self._finished:
                self.finish(*e.args)
            return
        try:
            self.log_exception(*sys.exc_info())
        except Exception:
            # An error here should still get a best-effort send_error()
            # to avoid leaking the connection.
            app_log.error("Error in exception logger", exc_info=True)
        if self._finished:
            # Extra errors after the request has been finished should
            # be logged, but there is no reason to continue to try and
            # send a response.
            return
        if isinstance(e, HTTPError):
            if e.status_code not in httputil.responses and not e.reason:
                gen_log.error("Bad HTTP status code: %d", e.status_code)
                self.send_error(500, exc_info=sys.exc_info())
            else:
                self.send_error(e.status_code, exc_info=sys.exc_info())
        else:
            self.send_error(500, exc_info=sys.exc_info())

    def log_exception(self, typ, value, tb):
        """复写来自定义未捕获异常的日志.

        默认情况下 `HTTPError` 的日志实例作为警告(warning)没有堆栈追踪(在
        ``tornado.general`` logger), 其他作为错误(error)的异常带有堆栈
        追踪(在 ``tornado.application`` logger).

        .. versionadded:: 3.1
        """
        if isinstance(value, HTTPError):
            if value.log_message:
                format = "%d %s: " + value.log_message
                args = ([value.status_code, self._request_summary()] +
                        list(value.args))
                gen_log.warning(format, *args)
        else:
            app_log.error("Uncaught exception %s\n%r", self._request_summary(),
                          self.request, exc_info=(typ, value, tb))

    def _ui_module(self, name, module):
        def render(*args, **kwargs):
            if not hasattr(self, "_active_modules"):
                self._active_modules = {}
            if name not in self._active_modules:
                self._active_modules[name] = module(self)
            rendered = self._active_modules[name].render(*args, **kwargs)
            return rendered
        return render

    def _ui_method(self, method):
        return lambda *args, **kwargs: method(self, *args, **kwargs)

    def _clear_headers_for_304(self):
        # 304 responses should not contain entity headers (defined in
        # http://www.w3.org/Protocols/rfc2616/rfc2616-sec7.html#sec7.1)
        # not explicitly allowed by
        # http://www.w3.org/Protocols/rfc2616/rfc2616-sec10.html#sec10.3.5
        headers = ["Allow", "Content-Encoding", "Content-Language",
                   "Content-Length", "Content-MD5", "Content-Range",
                   "Content-Type", "Last-Modified"]
        for h in headers:
            self.clear_header(h)


def asynchronous(method):
    """用这个包装请求处理方法如果它们是异步的.

    这个装饰器适用于回调式异步方法; 对于协程, 使用 ``@gen.coroutine``
    装饰器而没有 ``@asynchronous``. (这是合理的, 因为遗留原因使用两个
    装饰器一起来提供 ``@asynchronous`` 在第一个, 但是在这种情况下
    ``@asynchronous`` 将被忽略)

    这个装饰器应仅适用于 :ref:`HTTP verb
    methods <verbs>`; 它的行为是未定义的对于任何其他方法.
    这个装饰器不会 *使* 一个方法异步; 它告诉框架该方法 *是*
    异步(执行)的. 对于这个装饰器, 该方法必须(至少有时)异步的做一
    些事情这是有用的.

    如果给定了这个装饰器, 当方法返回的时候响应并没有结束.
    它是由请求处理程序调用 `self.finish() <RequestHandler.finish>`
    来结束该HTTP请求的. 没有这个装饰器, 请求会自动结束当
    ``get()`` 或 ``post()`` 方法返回时. 例如:

    .. testcode::

       class MyRequestHandler(RequestHandler):
           @asynchronous
           def get(self):
              http = httpclient.AsyncHTTPClient()
              http.fetch("http://friendfeed.com/", self._on_download)

           def _on_download(self, response):
              self.write("Downloaded!")
              self.finish()

    .. testoutput::
       :hide:

    .. versionchanged:: 3.1
       可以使用 ``@gen.coroutine`` 而不需 ``@asynchronous``.

    .. versionchanged:: 4.3 可以返回任何东西但 ``None`` 或者一个
       可yield的对象来自于被 ``@asynchronous`` 装饰的方法是错误的.
       这样的返回值之前是默认忽略的.
    """
    # Delay the IOLoop import because it's not available on app engine.
    from tornado.ioloop import IOLoop

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        self._auto_finish = False
        with stack_context.ExceptionStackContext(
                self._stack_context_handle_exception):
            result = method(self, *args, **kwargs)
            if result is not None:
                result = gen.convert_yielded(result)
                # If @asynchronous is used with @gen.coroutine, (but
                # not @gen.engine), we can automatically finish the
                # request when the future resolves.  Additionally,
                # the Future will swallow any exceptions so we need
                # to throw them back out to the stack context to finish
                # the request.
                def future_complete(f):
                    f.result()
                    if not self._finished:
                        self.finish()
                IOLoop.current().add_future(result, future_complete)
                # Once we have done this, hide the Future from our
                # caller (i.e. RequestHandler._when_complete), which
                # would otherwise set up its own callback and
                # exception handler (resulting in exceptions being
                # logged twice).
                return None
            return result
    return wrapper


def stream_request_body(cls):
    """适用于 `RequestHandler` 子类以开启流式body支持.

    这个装饰器意味着以下变化:

    * `.HTTPServerRequest.body` 变成了未定义, 并且body参数将不再被
      `RequestHandler.get_argument` 所包含.
    * `RequestHandler.prepare` 被调用当读到请求头而不是在整个请求体
      都被读到之后.
    * 子类必须定义一个方法 ``data_received(self, data):``, 这将被调
      用0次或多次当数据是可用状态时. 注意如果该请求的body是空的,
      ``data_received`` 可能不会被调用.
    * ``prepare`` 和 ``data_received`` 可能返回Futures对象(就像通过
      ``@gen.coroutine``, 在这种情况下下一个方法将不会被调用直到这些
      futures完成.
    * 常规的HTTP方法 (``post``, ``put``, 等)将在整个body被读取后被
      调用.

    在 ``data_received`` 和asynchronous之间有一个微妙的互动
    ``prepare``: ``data_received`` 的第一次调用可能出现在任何地方
    在调用 ``prepare`` 已经返回 *或 yielded*.
    """
    if not issubclass(cls, RequestHandler):
        raise TypeError("expected subclass of RequestHandler, got %r", cls)
    cls._stream_request_body = True
    return cls


def _has_stream_request_body(cls):
    if not issubclass(cls, RequestHandler):
        raise TypeError("expected subclass of RequestHandler, got %r", cls)
    return getattr(cls, '_stream_request_body', False)


def removeslash(method):
    """使用这个装饰器移除请求路径尾部的斜杠(slashes).

    例如, 使用了这个装饰器请求 ``/foo/`` 将被重定向到 ``/foo`` .
    你的请求处理映射应该使用正则表达式类似 ``r'/foo/*'``
    和使用装饰器相结合.
    """
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        if self.request.path.endswith("/"):
            if self.request.method in ("GET", "HEAD"):
                uri = self.request.path.rstrip("/")
                if uri:  # don't try to redirect '/' to ''
                    if self.request.query:
                        uri += "?" + self.request.query
                    self.redirect(uri, permanent=True)
                    return
            else:
                raise HTTPError(404)
        return method(self, *args, **kwargs)
    return wrapper


def addslash(method):
    """使用这个装饰器给请求路径中添加丢失的slash.

    例如, 使用了这个装饰器请求 ``/foo`` 将被重定向到 ``/foo/`` .
    你的请求处理映射应该使用正则表达式类似 ``r'/foo/?'``
    和使用装饰器相结合.
    """
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        if not self.request.path.endswith("/"):
            if self.request.method in ("GET", "HEAD"):
                uri = self.request.path + "/"
                if self.request.query:
                    uri += "?" + self.request.query
                self.redirect(uri, permanent=True)
                return
            raise HTTPError(404)
        return method(self, *args, **kwargs)
    return wrapper


class Application(httputil.HTTPServerConnectionDelegate):
    """组成一个web应用程序的请求处理程序的集合.

    该类的实例是可调用的并且可以被直接传递给HTTPServer为应用程序
    提供服务::

        application = web.Application([
            (r"/", MainPageHandler),
        ])
        http_server = httpserver.HTTPServer(application)
        http_server.listen(8080)
        ioloop.IOLoop.current().start()

    这个类的构造器带有一个列表包含 `URLSpec` 对象或
    (正则表达式, 请求类)元组. 当我们接收到请求, 我们按顺序迭代该列表
    并且实例化和请求路径相匹配的正则表达式所对应的第一个请求类.
    请求类可以被指定为一个类对象或一个(完全有资格的)名字.

    每个元组可以包含另外的部分, 只要符合 `URLSpec` 构造器参数的条件.
    (在Tornado 3.2之前, 只允许包含两个或三个元素的元组).

    一个字典可以作为该元组的第三个元素被传递, 它将被用作处理程序
    构造器的关键字参数和 `~RequestHandler.initialize` 方法.
    这种模式也被用于例子中的 `StaticFileHandler` (注意一个
    `StaticFileHandler` 可以被自动挂载连带下面的static_path设置)::

        application = web.Application([
            (r"/static/(.*)", web.StaticFileHandler, {"path": "/var/www"}),
        ])

    我们支持虚拟主机通过 `add_handlers` 方法, 该方法带有一个主机
    正则表达式作为第一个参数::

        application.add_handlers(r"www\.myhost\.com", [
            (r"/article/([0-9]+)", ArticleHandler),
        ])

    你可以提供静态文件服务通过传递 ``static_path`` 配置作为关键字
    参数. 我们将提供这些文件从 ``/static/`` URI (这是可配置的通过
    ``static_url_prefix`` 配置), 并且我们将提供 ``/favicon.ico``
    和 ``/robots.txt`` 从相同目录下. 一个 `StaticFileHandler` 的
    自定义子类可以被指定, 通过 ``static_handler_class`` 设置.

    """
    def __init__(self, handlers=None, default_host="", transforms=None,
                 **settings):
        if transforms is None:
            self.transforms = []
            if settings.get("compress_response") or settings.get("gzip"):
                self.transforms.append(GZipContentEncoding)
        else:
            self.transforms = transforms
        self.handlers = []
        self.named_handlers = {}
        self.default_host = default_host
        self.settings = settings
        self.ui_modules = {'linkify': _linkify,
                           'xsrf_form_html': _xsrf_form_html,
                           'Template': TemplateModule,
                           }
        self.ui_methods = {}
        self._load_ui_modules(settings.get("ui_modules", {}))
        self._load_ui_methods(settings.get("ui_methods", {}))
        if self.settings.get("static_path"):
            path = self.settings["static_path"]
            handlers = list(handlers or [])
            static_url_prefix = settings.get("static_url_prefix",
                                             "/static/")
            static_handler_class = settings.get("static_handler_class",
                                                StaticFileHandler)
            static_handler_args = settings.get("static_handler_args", {})
            static_handler_args['path'] = path
            for pattern in [re.escape(static_url_prefix) + r"(.*)",
                            r"/(favicon\.ico)", r"/(robots\.txt)"]:
                handlers.insert(0, (pattern, static_handler_class,
                                    static_handler_args))
        if handlers:
            self.add_handlers(".*$", handlers)

        if self.settings.get('debug'):
            self.settings.setdefault('autoreload', True)
            self.settings.setdefault('compiled_template_cache', False)
            self.settings.setdefault('static_hash_cache', False)
            self.settings.setdefault('serve_traceback', True)

        # Automatically reload modified modules
        if self.settings.get('autoreload'):
            from tornado import autoreload
            autoreload.start()

    def listen(self, port, address="", **kwargs):
        """为应用程序在给定端口上启动一个HTTP server.

        这是一个方便的别名用来创建一个 `.HTTPServer` 对象并调用它
        的listen方法. `HTTPServer.listen <.TCPServer.listen>`
        不支持传递关键字参数给 `.HTTPServer` 构造器. 对于高级用途
        (e.g. 多进程模式), 不要使用这个方法; 创建一个
        `.HTTPServer` 并直接调用它的
        `.TCPServer.bind`/`.TCPServer.start` 方法.

        注意在调用这个方法之后你仍然需要调用
        ``IOLoop.current().start()`` 来启动该服务.

        返回 `.HTTPServer` 对象.

        .. versionchanged:: 4.3
           现在返回 `.HTTPServer` 对象.
        """
        # import is here rather than top level because HTTPServer
        # is not importable on appengine
        from tornado.httpserver import HTTPServer
        server = HTTPServer(self, **kwargs)
        server.listen(port, address)
        return server

    def add_handlers(self, host_pattern, host_handlers):
        """添加给定的handler到我们的handler表.

        Host 模式将按照它们的添加顺序进行处理.
        所有匹配模式将被考虑.
        """
        if not host_pattern.endswith("$"):
            host_pattern += "$"
        handlers = []
        # The handlers with the wildcard host_pattern are a special
        # case - they're added in the constructor but should have lower
        # precedence than the more-precise handlers added later.
        # If a wildcard handler group exists, it should always be last
        # in the list, so insert new groups just before it.
        if self.handlers and self.handlers[-1][0].pattern == '.*$':
            self.handlers.insert(-1, (re.compile(host_pattern), handlers))
        else:
            self.handlers.append((re.compile(host_pattern), handlers))

        for spec in host_handlers:
            if isinstance(spec, (tuple, list)):
                assert len(spec) in (2, 3, 4)
                spec = URLSpec(*spec)
            handlers.append(spec)
            if spec.name:
                if spec.name in self.named_handlers:
                    app_log.warning(
                        "Multiple handlers named %s; replacing previous value",
                        spec.name)
                self.named_handlers[spec.name] = spec

    def add_transform(self, transform_class):
        self.transforms.append(transform_class)

    def _get_host_handlers(self, request):
        host = split_host_and_port(request.host.lower())[0]
        matches = []
        for pattern, handlers in self.handlers:
            if pattern.match(host):
                matches.extend(handlers)
        # Look for default host if not behind load balancer (for debugging)
        if not matches and "X-Real-Ip" not in request.headers:
            for pattern, handlers in self.handlers:
                if pattern.match(self.default_host):
                    matches.extend(handlers)
        return matches or None

    def _load_ui_methods(self, methods):
        if isinstance(methods, types.ModuleType):
            self._load_ui_methods(dict((n, getattr(methods, n))
                                       for n in dir(methods)))
        elif isinstance(methods, list):
            for m in methods:
                self._load_ui_methods(m)
        else:
            for name, fn in methods.items():
                if not name.startswith("_") and hasattr(fn, "__call__") \
                        and name[0].lower() == name[0]:
                    self.ui_methods[name] = fn

    def _load_ui_modules(self, modules):
        if isinstance(modules, types.ModuleType):
            self._load_ui_modules(dict((n, getattr(modules, n))
                                       for n in dir(modules)))
        elif isinstance(modules, list):
            for m in modules:
                self._load_ui_modules(m)
        else:
            assert isinstance(modules, dict)
            for name, cls in modules.items():
                try:
                    if issubclass(cls, UIModule):
                        self.ui_modules[name] = cls
                except TypeError:
                    pass

    def start_request(self, server_conn, request_conn):
        # Modern HTTPServer interface
        return _RequestDispatcher(self, request_conn)

    def __call__(self, request):
        # Legacy HTTPServer interface
        dispatcher = _RequestDispatcher(self, None)
        dispatcher.set_request(request)
        return dispatcher.execute()

    def reverse_url(self, name, *args):
        """返回名为 ``name`` 的handler的URL路径

        处理程序必须作为 `URLSpec` 添加到应用程序.

        捕获组的参数将在 `URLSpec` 的正则表达式被替换.
        如有必要它们将被转换成string, 编码成utf8,及
        网址转义(url-escaped).
        """
        if name in self.named_handlers:
            return self.named_handlers[name].reverse(*args)
        raise KeyError("%s not found in named urls" % name)

    def log_request(self, handler):
        """写一个完成的HTTP 请求到日志中.

        默认情况下会写到python 根(root)logger. 要改变这种行为
        无论是子类应用和复写这个方法, 或者传递一个函数到应用的
        设置字典中作为 ``log_function``.
        """
        if "log_function" in self.settings:
            self.settings["log_function"](handler)
            return
        if handler.get_status() < 400:
            log_method = access_log.info
        elif handler.get_status() < 500:
            log_method = access_log.warning
        else:
            log_method = access_log.error
        request_time = 1000.0 * handler.request.request_time()
        log_method("%d %s %.2fms", handler.get_status(),
                   handler._request_summary(), request_time)


class _RequestDispatcher(httputil.HTTPMessageDelegate):
    def __init__(self, application, connection):
        self.application = application
        self.connection = connection
        self.request = None
        self.chunks = []
        self.handler_class = None
        self.handler_kwargs = None
        self.path_args = []
        self.path_kwargs = {}

    def headers_received(self, start_line, headers):
        self.set_request(httputil.HTTPServerRequest(
            connection=self.connection, start_line=start_line,
            headers=headers))
        if self.stream_request_body:
            self.request.body = Future()
            return self.execute()

    def set_request(self, request):
        self.request = request
        self._find_handler()
        self.stream_request_body = _has_stream_request_body(self.handler_class)

    def _find_handler(self):
        # Identify the handler to use as soon as we have the request.
        # Save url path arguments for later.
        app = self.application
        handlers = app._get_host_handlers(self.request)
        if not handlers:
            self.handler_class = RedirectHandler
            self.handler_kwargs = dict(url="%s://%s/"
                                       % (self.request.protocol,
                                          app.default_host))
            return
        for spec in handlers:
            match = spec.regex.match(self.request.path)
            if match:
                self.handler_class = spec.handler_class
                self.handler_kwargs = spec.kwargs
                if spec.regex.groups:
                    # Pass matched groups to the handler.  Since
                    # match.groups() includes both named and
                    # unnamed groups, we want to use either groups
                    # or groupdict but not both.
                    if spec.regex.groupindex:
                        self.path_kwargs = dict(
                            (str(k), _unquote_or_none(v))
                            for (k, v) in match.groupdict().items())
                    else:
                        self.path_args = [_unquote_or_none(s)
                                          for s in match.groups()]
                return
        if app.settings.get('default_handler_class'):
            self.handler_class = app.settings['default_handler_class']
            self.handler_kwargs = app.settings.get(
                'default_handler_args', {})
        else:
            self.handler_class = ErrorHandler
            self.handler_kwargs = dict(status_code=404)

    def data_received(self, data):
        if self.stream_request_body:
            return self.handler.data_received(data)
        else:
            self.chunks.append(data)

    def finish(self):
        if self.stream_request_body:
            self.request.body.set_result(None)
        else:
            self.request.body = b''.join(self.chunks)
            self.request._parse_body()
            self.execute()

    def on_connection_close(self):
        if self.stream_request_body:
            self.handler.on_connection_close()
        else:
            self.chunks = None

    def execute(self):
        # If template cache is disabled (usually in the debug mode),
        # re-compile templates and reload static files on every
        # request so you don't need to restart to see changes
        if not self.application.settings.get("compiled_template_cache", True):
            with RequestHandler._template_loader_lock:
                for loader in RequestHandler._template_loaders.values():
                    loader.reset()
        if not self.application.settings.get('static_hash_cache', True):
            StaticFileHandler.reset()

        self.handler = self.handler_class(self.application, self.request,
                                          **self.handler_kwargs)
        transforms = [t(self.request) for t in self.application.transforms]

        if self.stream_request_body:
            self.handler._prepared_future = Future()
        # Note that if an exception escapes handler._execute it will be
        # trapped in the Future it returns (which we are ignoring here,
        # leaving it to be logged when the Future is GC'd).
        # However, that shouldn't happen because _execute has a blanket
        # except handler, and we cannot easily access the IOLoop here to
        # call add_future (because of the requirement to remain compatible
        # with WSGI)
        self.handler._execute(transforms, *self.path_args,
                              **self.path_kwargs)
        # If we are streaming the request body, then execute() is finished
        # when the handler has prepared to receive the body.  If not,
        # it doesn't matter when execute() finishes (so we return None)
        return self.handler._prepared_future


class HTTPError(Exception):
    """一个将会成为HTTP错误响应的异常.

    抛出一个 `HTTPError` 是一个更方便的选择比起调用
    `RequestHandler.send_error` 因为它自动结束当前的函数.

    为了自定义 `HTTPError` 的响应, 复写
    `RequestHandler.write_error`.

    :arg int status_code: HTTP状态码. 必须列在
        `httplib.responses <http.client.responses>` 之中除非给定了
        ``reason`` 关键字参数.
    :arg string log_message: 这个错误将会被写入日志的信息(除非该
        `Application` 是debug模式否则不会展示给用户). 可能含有
        ``%s``-风格的占位符, 它将填补剩余的位置参数.
    :arg string reason: 唯一的关键字参数. HTTP "reason" 短语
        将随着 ``status_code`` 传递给状态行. 通常从 ``status_code``,
        自动确定但可以使用一个非标准的数字代码.
    """
    def __init__(self, status_code=500, log_message=None, *args, **kwargs):
        self.status_code = status_code
        self.log_message = log_message
        self.args = args
        self.reason = kwargs.get('reason', None)
        if log_message and not args:
            self.log_message = log_message.replace('%', '%%')

    def __str__(self):
        message = "HTTP %d: %s" % (
            self.status_code,
            self.reason or httputil.responses.get(self.status_code, 'Unknown'))
        if self.log_message:
            return message + " (" + (self.log_message % self.args) + ")"
        else:
            return message


class Finish(Exception):
    """一个为了结束请求的异常但不会产生错误响应.

    当 `Finish` 被抛出在一个 `RequestHandler`, 该请求将会结束(调用
    `RequestHandler.finish` 如果该方法尚未被调用), 但是错误处理方法
    (包括 `RequestHandler.write_error`)将不会被调用.

    If `Finish()` was created with no arguments, the pending response
    will be sent as-is. If `Finish()` was given an argument, that
    argument will be passed to `RequestHandler.finish()`.

    This can be a more convenient way to implement custom error pages
    than overriding ``write_error`` (especially in library code)::

        if self.current_user is None:
            self.set_status(401)
            self.set_header('WWW-Authenticate', 'Basic realm="something"')
            raise Finish()

    .. versionchanged:: 4.3
       Arguments passed to ``Finish()`` will be passed on to
       `RequestHandler.finish`.
    """
    pass


class MissingArgumentError(HTTPError):
    """由 `RequestHandler.get_argument` 抛出的异常.

    这是 `HTTPError` 的一个子类, 所以如果它未捕获400响应码将被
    用来代替500(并且栈追踪不会被记录到日志).

    .. versionadded:: 3.1
    """
    def __init__(self, arg_name):
        super(MissingArgumentError, self).__init__(
            400, 'Missing argument %s' % arg_name)
        self.arg_name = arg_name


class ErrorHandler(RequestHandler):
    """为所有请求生成一个带有 ``status_code`` 的错误响应."""
    def initialize(self, status_code):
        self.set_status(status_code)

    def prepare(self):
        raise HTTPError(self._status_code)

    def check_xsrf_cookie(self):
        # POSTs to an ErrorHandler don't actually have side effects,
        # so we don't need to check the xsrf token.  This allows POSTs
        # to the wrong url to return a 404 instead of 403.
        pass


class RedirectHandler(RequestHandler):
    """将所有GET请求重定向到给定的URL.

    你需要为处理程序提供 ``url`` 关键字参数, e.g.::

        application = web.Application([
            (r"/oldpath", web.RedirectHandler, {"url": "/newpath"}),
        ])
    """
    def initialize(self, url, permanent=True):
        self._url = url
        self._permanent = permanent

    def get(self):
        self.redirect(self._url, permanent=self._permanent)


class StaticFileHandler(RequestHandler):
    """可以为一个目录提供静态内容服务的简单处理程序.

    A `StaticFileHandler` is configured automatically if you pass the
    ``static_path`` keyword argument to `Application`.  This handler
    can be customized with the ``static_url_prefix``, ``static_handler_class``,
    and ``static_handler_args`` settings.

    To map an additional path to this handler for a static data directory
    you would add a line to your application like::

        application = web.Application([
            (r"/content/(.*)", web.StaticFileHandler, {"path": "/var/www"}),
        ])

    The handler constructor requires a ``path`` argument, which specifies the
    local root directory of the content to be served.

    Note that a capture group in the regex is required to parse the value for
    the ``path`` argument to the get() method (different than the constructor
    argument above); see `URLSpec` for details.

    To serve a file like ``index.html`` automatically when a directory is
    requested, set ``static_handler_args=dict(default_filename="index.html")``
    in your application settings, or add ``default_filename`` as an initializer
    argument for your ``StaticFileHandler``.

    To maximize the effectiveness of browser caching, this class supports
    versioned urls (by default using the argument ``?v=``).  If a version
    is given, we instruct the browser to cache this file indefinitely.
    `make_static_url` (also available as `RequestHandler.static_url`) can
    be used to construct a versioned url.

    This handler is intended primarily for use in development and light-duty
    file serving; for heavy traffic it will be more efficient to use
    a dedicated static file server (such as nginx or Apache).  We support
    the HTTP ``Accept-Ranges`` mechanism to return partial content (because
    some browsers require this functionality to be present to seek in
    HTML5 audio or video).

    **Subclassing notes**

    This class is designed to be extensible by subclassing, but because
    of the way static urls are generated with class methods rather than
    instance methods, the inheritance patterns are somewhat unusual.
    Be sure to use the ``@classmethod`` decorator when overriding a
    class method.  Instance methods may use the attributes ``self.path``
    ``self.absolute_path``, and ``self.modified``.

    Subclasses should only override methods discussed in this section;
    overriding other methods is error-prone.  Overriding
    ``StaticFileHandler.get`` is particularly problematic due to the
    tight coupling with ``compute_etag`` and other methods.

    To change the way static urls are generated (e.g. to match the behavior
    of another server or CDN), override `make_static_url`, `parse_url_path`,
    `get_cache_time`, and/or `get_version`.

    To replace all interaction with the filesystem (e.g. to serve
    static content from a database), override `get_content`,
    `get_content_size`, `get_modified_time`, `get_absolute_path`, and
    `validate_absolute_path`.

    .. versionchanged:: 3.1
       Many of the methods for subclasses were added in Tornado 3.1.
    """
    CACHE_MAX_AGE = 86400 * 365 * 10  # 10 years

    _static_hashes = {}
    _lock = threading.Lock()  # protects _static_hashes

    def initialize(self, path, default_filename=None):
        self.root = path
        self.default_filename = default_filename

    @classmethod
    def reset(cls):
        with cls._lock:
            cls._static_hashes = {}

    def head(self, path):
        return self.get(path, include_body=False)

    @gen.coroutine
    def get(self, path, include_body=True):
        # Set up our path instance variables.
        self.path = self.parse_url_path(path)
        del path  # make sure we don't refer to path instead of self.path again
        absolute_path = self.get_absolute_path(self.root, self.path)
        self.absolute_path = self.validate_absolute_path(
            self.root, absolute_path)
        if self.absolute_path is None:
            return

        self.modified = self.get_modified_time()
        self.set_headers()

        if self.should_return_304():
            self.set_status(304)
            return

        request_range = None
        range_header = self.request.headers.get("Range")
        if range_header:
            # As per RFC 2616 14.16, if an invalid Range header is specified,
            # the request will be treated as if the header didn't exist.
            request_range = httputil._parse_request_range(range_header)

        size = self.get_content_size()
        if request_range:
            start, end = request_range
            if (start is not None and start >= size) or end == 0:
                # As per RFC 2616 14.35.1, a range is not satisfiable only: if
                # the first requested byte is equal to or greater than the
                # content, or when a suffix with length 0 is specified
                self.set_status(416)  # Range Not Satisfiable
                self.set_header("Content-Type", "text/plain")
                self.set_header("Content-Range", "bytes */%s" % (size, ))
                return
            if start is not None and start < 0:
                start += size
            if end is not None and end > size:
                # Clients sometimes blindly use a large range to limit their
                # download size; cap the endpoint at the actual file size.
                end = size
            # Note: only return HTTP 206 if less than the entire range has been
            # requested. Not only is this semantically correct, but Chrome
            # refuses to play audio if it gets an HTTP 206 in response to
            # ``Range: bytes=0-``.
            if size != (end or size) - (start or 0):
                self.set_status(206)  # Partial Content
                self.set_header("Content-Range",
                                httputil._get_content_range(start, end, size))
        else:
            start = end = None

        if start is not None and end is not None:
            content_length = end - start
        elif end is not None:
            content_length = end
        elif start is not None:
            content_length = size - start
        else:
            content_length = size
        self.set_header("Content-Length", content_length)

        if include_body:
            content = self.get_content(self.absolute_path, start, end)
            if isinstance(content, bytes):
                content = [content]
            for chunk in content:
                try:
                    self.write(chunk)
                    yield self.flush()
                except iostream.StreamClosedError:
                    return
        else:
            assert self.request.method == "HEAD"

    def compute_etag(self):
        """设置 ``Etag`` 头基于static url版本.

        这允许高效的针对缓存版本的 ``If-None-Match`` 检查,
        并发送正确的 ``Etag`` 给局部的响应(i.e. 相同的
        ``Etag`` 为完整的文件).

        .. versionadded:: 3.1
        """
        version_hash = self._get_cached_version(self.absolute_path)
        if not version_hash:
            return None
        return '"%s"' % (version_hash, )

    def set_headers(self):
        """设置响应的内容和缓存头.

        .. versionadded:: 3.1
        """
        self.set_header("Accept-Ranges", "bytes")
        self.set_etag_header()

        if self.modified is not None:
            self.set_header("Last-Modified", self.modified)

        content_type = self.get_content_type()
        if content_type:
            self.set_header("Content-Type", content_type)

        cache_time = self.get_cache_time(self.path, self.modified,
                                         content_type)
        if cache_time > 0:
            self.set_header("Expires", datetime.datetime.utcnow() +
                            datetime.timedelta(seconds=cache_time))
            self.set_header("Cache-Control", "max-age=" + str(cache_time))

        self.set_extra_headers(self.path)

    def should_return_304(self):
        """如果头部表明我们应该返回304则返回True.

        .. versionadded:: 3.1
        """
        if self.check_etag_header():
            return True

        # Check the If-Modified-Since, and don't send the result if the
        # content has not been modified
        ims_value = self.request.headers.get("If-Modified-Since")
        if ims_value is not None:
            date_tuple = email.utils.parsedate(ims_value)
            if date_tuple is not None:
                if_since = datetime.datetime(*date_tuple[:6])
                if if_since >= self.modified:
                    return True

        return False

    @classmethod
    def get_absolute_path(cls, root, path):
        """返回 ``path`` 相对于 ``root`` 的绝对路径.

        ``root`` 是这个 `StaticFileHandler` 配置的路径(在大多数情
        况下是 `Application` 的 ``static_path``设置).

        这个类方法可能在子类中被复写. 默认情况下它返回一个文件系统
        路径, 但其他字符串可以被使用, 只要它们是独特的并且被
        子类复写的 `get_content` 理解.

        .. versionadded:: 3.1
        """
        abspath = os.path.abspath(os.path.join(root, path))
        return abspath

    def validate_absolute_path(self, root, absolute_path):
        """验证并返回绝对路径.

        ``root`` 是 `StaticFileHandler` 配置的路径,并且
        ``path`` 是 `get_absolute_path` 的结果.

        这是一个实例方法在请求过程中被调用, 所以它可能抛出
        `HTTPError` 或者使用类似 `RequestHandler.redirect`
        (返回None在重定向到停止进一步处理之后) 这种方法.
        如果丢失文件将会生成404错误.

        这个方法可能在返回路径之前修改它, 但是注意任何这样的
        修改将不会被 `make_static_url` 理解.

        在实例方法, 这个方法的结果对 ``self.absolute_path``
        是可用的.

        .. versionadded:: 3.1
        """
        # os.path.abspath strips a trailing /.
        # We must add it back to `root` so that we only match files
        # in a directory named `root` instead of files starting with
        # that prefix.
        root = os.path.abspath(root)
        if not root.endswith(os.path.sep):
            # abspath always removes a trailing slash, except when
            # root is '/'. This is an unusual case, but several projects
            # have independently discovered this technique to disable
            # Tornado's path validation and (hopefully) do their own,
            # so we need to support it.
            root += os.path.sep
        # The trailing slash also needs to be temporarily added back
        # the requested path so a request to root/ will match.
        if not (absolute_path + os.path.sep).startswith(root):
            raise HTTPError(403, "%s is not in root static directory",
                            self.path)
        if (os.path.isdir(absolute_path) and
                self.default_filename is not None):
            # need to look at the request.path here for when path is empty
            # but there is some prefix to the path that was already
            # trimmed by the routing
            if not self.request.path.endswith("/"):
                self.redirect(self.request.path + "/", permanent=True)
                return
            absolute_path = os.path.join(absolute_path, self.default_filename)
        if not os.path.exists(absolute_path):
            raise HTTPError(404)
        if not os.path.isfile(absolute_path):
            raise HTTPError(403, "%s is not a file", self.path)
        return absolute_path

    @classmethod
    def get_content(cls, abspath, start=None, end=None):
        """Retrieve the content of the requested resource which is located
        at the given absolute path.

        This class method may be overridden by subclasses.  Note that its
        signature is different from other overridable class methods
        (no ``settings`` argument); this is deliberate to ensure that
        ``abspath`` is able to stand on its own as a cache key.

        This method should either return a byte string or an iterator
        of byte strings.  The latter is preferred for large files
        as it helps reduce memory fragmentation.

        .. versionadded:: 3.1
        """
        with open(abspath, "rb") as file:
            if start is not None:
                file.seek(start)
            if end is not None:
                remaining = end - (start or 0)
            else:
                remaining = None
            while True:
                chunk_size = 64 * 1024
                if remaining is not None and remaining < chunk_size:
                    chunk_size = remaining
                chunk = file.read(chunk_size)
                if chunk:
                    if remaining is not None:
                        remaining -= len(chunk)
                    yield chunk
                else:
                    if remaining is not None:
                        assert remaining == 0
                    return

    @classmethod
    def get_content_version(cls, abspath):
        """返回给定路径资源的一个版本字符串.

        这个类方法可以被子类复写. 默认的实现是对文件内容的hash.

        .. versionadded:: 3.1
        """
        data = cls.get_content(abspath)
        hasher = hashlib.md5()
        if isinstance(data, bytes):
            hasher.update(data)
        else:
            for chunk in data:
                hasher.update(chunk)
        return hasher.hexdigest()

    def _stat(self):
        if not hasattr(self, '_stat_result'):
            self._stat_result = os.stat(self.absolute_path)
        return self._stat_result

    def get_content_size(self):
        """检索给定路径中资源的总大小.

        这个方法可以被子类复写.

        .. versionadded:: 3.1

        .. versionchanged:: 4.0
           这个方法总是被调用, 而不是仅在部分结果被请求时.
        """
        stat_result = self._stat()
        return stat_result[stat.ST_SIZE]

    def get_modified_time(self):
        """返回 ``self.absolute_path`` 的最后修改时间.

        可以被子类复写. 应当返回一个 `~datetime.datetime`
        对象或None.

        .. versionadded:: 3.1
        """
        stat_result = self._stat()
        modified = datetime.datetime.utcfromtimestamp(
            stat_result[stat.ST_MTIME])
        return modified

    def get_content_type(self):
        """返回这个请求使用的 ``Content-Type`` 头.

        .. versionadded:: 3.1
        """
        mime_type, encoding = mimetypes.guess_type(self.absolute_path)
        # per RFC 6713, use the appropriate type for a gzip compressed file
        if encoding == "gzip":
            return "application/gzip"
        # As of 2015-07-21 there is no bzip2 encoding defined at
        # http://www.iana.org/assignments/media-types/media-types.xhtml
        # So for that (and any other encoding), use octet-stream.
        elif encoding is not None:
            return "application/octet-stream"
        elif mime_type is not None:
            return mime_type
        # if mime_type not detected, use application/octet-stream
        else:
            return "application/octet-stream"

    def set_extra_headers(self, path):
        """为了子类给响应添加额外的头部"""
        pass

    def get_cache_time(self, path, modified, mime_type):
        """复写来自定义缓存控制行为.

        返回一个正的秒数作为结果可缓存的时间的量或者返回0标记资源
        可以被缓存一个未指定的时间段(受浏览器自身的影响).

        默认情况下带有 ``v`` 请求参数的资源返回的缓存过期时间是10年.
        """
        return self.CACHE_MAX_AGE if "v" in self.request.arguments else 0

    @classmethod
    def make_static_url(cls, settings, path, include_version=True):
        """为给定路径构造一个的有版本的url.

        这个方法可以在子类中被复写(但是注意他是一个类方法而不是一个
        实例方法). 子类只需实现签名
        ``make_static_url(cls, settings, path)``; 其他关键字参数可
        以通过 `~RequestHandler.static_url` 传递, 但这不是标准.

        ``settings`` 是 `Application.settings` 字典.  ``path``
        是被请求的静态路径. 返回的url应该是相对于当前host的.

        ``include_version`` 决定生成的URL是否应该包含含有给定
        ``path`` 相对应文件的hash版本查询字符串.

        """
        url = settings.get('static_url_prefix', '/static/') + path
        if not include_version:
            return url

        version_hash = cls.get_version(settings, path)
        if not version_hash:
            return url

        return '%s?v=%s' % (url, version_hash)

    def parse_url_path(self, url_path):
        """将静态URL路径转换成文件系统路径.

        ``url_path`` 是由去掉 ``static_url_prefix`` 的URL组成.
        返回值应该是相对于 ``static_path`` 的文件系统路径.

        这是逆 `make_static_url` .
        """
        if os.path.sep != "/":
            url_path = url_path.replace("/", os.path.sep)
        return url_path

    @classmethod
    def get_version(cls, settings, path):
        """生成用于静态URL的版本字符串.

        ``settings`` 是 `Application.settings` 字典并且 ``path``
        是请求资源在文件系统中的相对位置. 返回值应该是一个字符串
        或 ``None`` 如果没有版本可以被确定.

        .. versionchanged:: 3.1
           这个方法之前建议在子类中复写; `get_content_version`
           现在是首选因为它允许基类来处理结果的缓存.
        """
        abs_path = cls.get_absolute_path(settings['static_path'], path)
        return cls._get_cached_version(abs_path)

    @classmethod
    def _get_cached_version(cls, abs_path):
        with cls._lock:
            hashes = cls._static_hashes
            if abs_path not in hashes:
                try:
                    hashes[abs_path] = cls.get_content_version(abs_path)
                except Exception:
                    gen_log.error("Could not open static file %r", abs_path)
                    hashes[abs_path] = None
            hsh = hashes.get(abs_path)
            if hsh:
                return hsh
        return None


class FallbackHandler(RequestHandler):
    """A `RequestHandler` that wraps another HTTP server callback.

    The fallback is a callable object that accepts an
    `~.httputil.HTTPServerRequest`, such as an `Application` or
    `tornado.wsgi.WSGIContainer`.  This is most useful to use both
    Tornado ``RequestHandlers`` and WSGI in the same server.  Typical
    usage::

        wsgi_app = tornado.wsgi.WSGIContainer(
            django.core.handlers.wsgi.WSGIHandler())
        application = tornado.web.Application([
            (r"/foo", FooHandler),
            (r".*", FallbackHandler, dict(fallback=wsgi_app),
        ])
    """
    def initialize(self, fallback):
        self.fallback = fallback

    def prepare(self):
        self.fallback(self.request)
        self._finished = True


class OutputTransform(object):
    """A transform modifies the result of an HTTP request (e.g., GZip encoding)

    Applications are not expected to create their own OutputTransforms
    or interact with them directly; the framework chooses which transforms
    (if any) to apply.
    """
    def __init__(self, request):
        pass

    def transform_first_chunk(self, status_code, headers, chunk, finishing):
        return status_code, headers, chunk

    def transform_chunk(self, chunk, finishing):
        return chunk


class GZipContentEncoding(OutputTransform):
    """Applies the gzip content encoding to the response.

    See http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.11

    .. versionchanged:: 4.0
        Now compresses all mime types beginning with ``text/``, instead
        of just a whitelist. (the whitelist is still used for certain
        non-text mime types).
    """
    # Whitelist of compressible mime types (in addition to any types
    # beginning with "text/").
    CONTENT_TYPES = set(["application/javascript", "application/x-javascript",
                         "application/xml", "application/atom+xml",
                         "application/json", "application/xhtml+xml"])
    # Python's GzipFile defaults to level 9, while most other gzip
    # tools (including gzip itself) default to 6, which is probably a
    # better CPU/size tradeoff.
    GZIP_LEVEL = 6
    # Responses that are too short are unlikely to benefit from gzipping
    # after considering the "Content-Encoding: gzip" header and the header
    # inside the gzip encoding.
    # Note that responses written in multiple chunks will be compressed
    # regardless of size.
    MIN_LENGTH = 1024

    def __init__(self, request):
        self._gzipping = "gzip" in request.headers.get("Accept-Encoding", "")

    def _compressible_type(self, ctype):
        return ctype.startswith('text/') or ctype in self.CONTENT_TYPES

    def transform_first_chunk(self, status_code, headers, chunk, finishing):
        if 'Vary' in headers:
            headers['Vary'] += b', Accept-Encoding'
        else:
            headers['Vary'] = b'Accept-Encoding'
        if self._gzipping:
            ctype = _unicode(headers.get("Content-Type", "")).split(";")[0]
            self._gzipping = self._compressible_type(ctype) and \
                (not finishing or len(chunk) >= self.MIN_LENGTH) and \
                ("Content-Encoding" not in headers)
        if self._gzipping:
            headers["Content-Encoding"] = "gzip"
            self._gzip_value = BytesIO()
            self._gzip_file = gzip.GzipFile(mode="w", fileobj=self._gzip_value,
                                            compresslevel=self.GZIP_LEVEL)
            chunk = self.transform_chunk(chunk, finishing)
            if "Content-Length" in headers:
                # The original content length is no longer correct.
                # If this is the last (and only) chunk, we can set the new
                # content-length; otherwise we remove it and fall back to
                # chunked encoding.
                if finishing:
                    headers["Content-Length"] = str(len(chunk))
                else:
                    del headers["Content-Length"]
        return status_code, headers, chunk

    def transform_chunk(self, chunk, finishing):
        if self._gzipping:
            self._gzip_file.write(chunk)
            if finishing:
                self._gzip_file.close()
            else:
                self._gzip_file.flush()
            chunk = self._gzip_value.getvalue()
            self._gzip_value.truncate(0)
            self._gzip_value.seek(0)
        return chunk


def authenticated(method):
    """Decorate methods with this to require that the user be logged in.

    If the user is not logged in, they will be redirected to the configured
    `login url <RequestHandler.get_login_url>`.

    If you configure a login url with a query parameter, Tornado will
    assume you know what you're doing and use it as-is.  If not, it
    will add a `next` parameter so the login page knows where to send
    you once you're logged in.
    """
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        if not self.current_user:
            if self.request.method in ("GET", "HEAD"):
                url = self.get_login_url()
                if "?" not in url:
                    if urlparse.urlsplit(url).scheme:
                        # if login url is absolute, make next absolute too
                        next_url = self.request.full_url()
                    else:
                        next_url = self.request.uri
                    url += "?" + urlencode(dict(next=next_url))
                self.redirect(url)
                return
            raise HTTPError(403)
        return method(self, *args, **kwargs)
    return wrapper


class UIModule(object):
    """A re-usable, modular UI unit on a page.

    UI modules often execute additional queries, and they can include
    additional CSS and JavaScript that will be included in the output
    page, which is automatically inserted on page render.

    Subclasses of UIModule must override the `render` method.
    """
    def __init__(self, handler):
        self.handler = handler
        self.request = handler.request
        self.ui = handler.ui
        self.locale = handler.locale

    @property
    def current_user(self):
        return self.handler.current_user

    def render(self, *args, **kwargs):
        """Override in subclasses to return this module's output."""
        raise NotImplementedError()

    def embedded_javascript(self):
        """Override to return a JavaScript string
        to be embedded in the page."""
        return None

    def javascript_files(self):
        """Override to return a list of JavaScript files needed by this module.

        If the return values are relative paths, they will be passed to
        `RequestHandler.static_url`; otherwise they will be used as-is.
        """
        return None

    def embedded_css(self):
        """Override to return a CSS string
        that will be embedded in the page."""
        return None

    def css_files(self):
        """Override to returns a list of CSS files required by this module.

        If the return values are relative paths, they will be passed to
        `RequestHandler.static_url`; otherwise they will be used as-is.
        """
        return None

    def html_head(self):
        """Override to return an HTML string that will be put in the <head/>
        element.
        """
        return None

    def html_body(self):
        """Override to return an HTML string that will be put at the end of
        the <body/> element.
        """
        return None

    def render_string(self, path, **kwargs):
        """Renders a template and returns it as a string."""
        return self.handler.render_string(path, **kwargs)


class _linkify(UIModule):
    def render(self, text, **kwargs):
        return escape.linkify(text, **kwargs)


class _xsrf_form_html(UIModule):
    def render(self):
        return self.handler.xsrf_form_html()


class TemplateModule(UIModule):
    """UIModule 简便的渲染给定的模板.

    {% module Template("foo.html") %} is similar to {% include "foo.html" %},
    but the module version gets its own namespace (with kwargs passed to
    Template()) instead of inheriting the outer template's namespace.

    Templates rendered through this module also get access to UIModule's
    automatic javascript/css features.  Simply call set_resources
    inside the template and give it keyword arguments corresponding to
    the methods on UIModule: {{ set_resources(js_files=static_url("my.js")) }}
    Note that these resources are output once per template file, not once
    per instantiation of the template, so they must not depend on
    any arguments to the template.
    """
    def __init__(self, handler):
        super(TemplateModule, self).__init__(handler)
        # keep resources in both a list and a dict to preserve order
        self._resource_list = []
        self._resource_dict = {}

    def render(self, path, **kwargs):
        def set_resources(**kwargs):
            if path not in self._resource_dict:
                self._resource_list.append(kwargs)
                self._resource_dict[path] = kwargs
            else:
                if self._resource_dict[path] != kwargs:
                    raise ValueError("set_resources called with different "
                                     "resources for the same template")
            return ""
        return self.render_string(path, set_resources=set_resources,
                                  **kwargs)

    def _get_resources(self, key):
        return (r[key] for r in self._resource_list if key in r)

    def embedded_javascript(self):
        return "\n".join(self._get_resources("embedded_javascript"))

    def javascript_files(self):
        result = []
        for f in self._get_resources("javascript_files"):
            if isinstance(f, (unicode_type, bytes)):
                result.append(f)
            else:
                result.extend(f)
        return result

    def embedded_css(self):
        return "\n".join(self._get_resources("embedded_css"))

    def css_files(self):
        result = []
        for f in self._get_resources("css_files"):
            if isinstance(f, (unicode_type, bytes)):
                result.append(f)
            else:
                result.extend(f)
        return result

    def html_head(self):
        return "".join(self._get_resources("html_head"))

    def html_body(self):
        return "".join(self._get_resources("html_body"))


class _UIModuleNamespace(object):
    """Lazy namespace which creates UIModule proxies bound to a handler."""
    def __init__(self, handler, ui_modules):
        self.handler = handler
        self.ui_modules = ui_modules

    def __getitem__(self, key):
        return self.handler._ui_module(key, self.ui_modules[key])

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as e:
            raise AttributeError(str(e))


class URLSpec(object):
    """Specifies mappings between URLs and handlers."""
    def __init__(self, pattern, handler, kwargs=None, name=None):
        """Parameters:

        * ``pattern``: Regular expression to be matched.  Any groups
          in the regex will be passed in to the handler's get/post/etc
          methods as arguments.

        * ``handler``: `RequestHandler` subclass to be invoked.

        * ``kwargs`` (optional): A dictionary of additional arguments
          to be passed to the handler's constructor.

        * ``name`` (optional): A name for this handler.  Used by
          `Application.reverse_url`.
        """
        if not pattern.endswith('$'):
            pattern += '$'
        self.regex = re.compile(pattern)
        assert len(self.regex.groupindex) in (0, self.regex.groups), \
            ("groups in url regexes must either be all named or all "
             "positional: %r" % self.regex.pattern)

        if isinstance(handler, str):
            # import the Module and instantiate the class
            # Must be a fully qualified name (module.ClassName)
            handler = import_object(handler)

        self.handler_class = handler
        self.kwargs = kwargs or {}
        self.name = name
        self._path, self._group_count = self._find_groups()

    def __repr__(self):
        return '%s(%r, %s, kwargs=%r, name=%r)' % \
            (self.__class__.__name__, self.regex.pattern,
             self.handler_class, self.kwargs, self.name)

    def _find_groups(self):
        """返回一个基于url的元组(reverse string, group count).

        例如: 给定一个url 模式 /([0-9]{4})/([a-z-]+)/, 这个方法
        将会返回('/%s/%s/', 2).
        """
        pattern = self.regex.pattern
        if pattern.startswith('^'):
            pattern = pattern[1:]
        if pattern.endswith('$'):
            pattern = pattern[:-1]

        if self.regex.groups != pattern.count('('):
            # The pattern is too complicated for our simplistic matching,
            # so we can't support reversing it.
            return (None, None)

        pieces = []
        for fragment in pattern.split('('):
            if ')' in fragment:
                paren_loc = fragment.index(')')
                if paren_loc >= 0:
                    pieces.append('%s' + fragment[paren_loc + 1:])
            else:
                pieces.append(fragment)

        return (''.join(pieces), self.regex.groups)

    def reverse(self, *args):
        assert self._path is not None, \
            "Cannot reverse url regex " + self.regex.pattern
        assert len(args) == self._group_count, "required number of arguments "\
            "not found"
        if not len(args):
            return self._path
        converted_args = []
        for a in args:
            if not isinstance(a, (unicode_type, bytes)):
                a = str(a)
            converted_args.append(escape.url_escape(utf8(a), plus=False))
        return self._path % tuple(converted_args)

url = URLSpec


if hasattr(hmac, 'compare_digest'):  # python 3.3
    _time_independent_equals = hmac.compare_digest
else:
    def _time_independent_equals(a, b):
        if len(a) != len(b):
            return False
        result = 0
        if isinstance(a[0], int):  # python3 byte strings
            for x, y in zip(a, b):
                result |= x ^ y
        else:  # python2
            for x, y in zip(a, b):
                result |= ord(x) ^ ord(y)
        return result == 0


def create_signed_value(secret, name, value, version=None, clock=None,
                        key_version=None):
    if version is None:
        version = DEFAULT_SIGNED_VALUE_VERSION
    if clock is None:
        clock = time.time

    timestamp = utf8(str(int(clock())))
    value = base64.b64encode(utf8(value))
    if version == 1:
        signature = _create_signature_v1(secret, name, value, timestamp)
        value = b"|".join([value, timestamp, signature])
        return value
    elif version == 2:
        # The v2 format consists of a version number and a series of
        # length-prefixed fields "%d:%s", the last of which is a
        # signature, all separated by pipes.  All numbers are in
        # decimal format with no leading zeros.  The signature is an
        # HMAC-SHA256 of the whole string up to that point, including
        # the final pipe.
        #
        # The fields are:
        # - format version (i.e. 2; no length prefix)
        # - key version (integer, default is 0)
        # - timestamp (integer seconds since epoch)
        # - name (not encoded; assumed to be ~alphanumeric)
        # - value (base64-encoded)
        # - signature (hex-encoded; no length prefix)
        def format_field(s):
            return utf8("%d:" % len(s)) + utf8(s)
        to_sign = b"|".join([
            b"2",
            format_field(str(key_version or 0)),
            format_field(timestamp),
            format_field(name),
            format_field(value),
            b''])

        if isinstance(secret, dict):
            assert key_version is not None, 'Key version must be set when sign key dict is used'
            assert version >= 2, 'Version must be at least 2 for key version support'
            secret = secret[key_version]

        signature = _create_signature_v2(secret, to_sign)
        return to_sign + signature
    else:
        raise ValueError("Unsupported version %d" % version)

# A leading version number in decimal
# with no leading zeros, followed by a pipe.
_signed_value_version_re = re.compile(br"^([1-9][0-9]*)\|(.*)$")


def _get_version(value):
    # Figures out what version value is.  Version 1 did not include an
    # explicit version field and started with arbitrary base64 data,
    # which makes this tricky.
    m = _signed_value_version_re.match(value)
    if m is None:
        version = 1
    else:
        try:
            version = int(m.group(1))
            if version > 999:
                # Certain payloads from the version-less v1 format may
                # be parsed as valid integers.  Due to base64 padding
                # restrictions, this can only happen for numbers whose
                # length is a multiple of 4, so we can treat all
                # numbers up to 999 as versions, and for the rest we
                # fall back to v1 format.
                version = 1
        except ValueError:
            version = 1
    return version


def decode_signed_value(secret, name, value, max_age_days=31,
                        clock=None, min_version=None):
    if clock is None:
        clock = time.time
    if min_version is None:
        min_version = DEFAULT_SIGNED_VALUE_MIN_VERSION
    if min_version > 2:
        raise ValueError("Unsupported min_version %d" % min_version)
    if not value:
        return None

    value = utf8(value)
    version = _get_version(value)

    if version < min_version:
        return None
    if version == 1:
        return _decode_signed_value_v1(secret, name, value,
                                       max_age_days, clock)
    elif version == 2:
        return _decode_signed_value_v2(secret, name, value,
                                       max_age_days, clock)
    else:
        return None


def _decode_signed_value_v1(secret, name, value, max_age_days, clock):
    parts = utf8(value).split(b"|")
    if len(parts) != 3:
        return None
    signature = _create_signature_v1(secret, name, parts[0], parts[1])
    if not _time_independent_equals(parts[2], signature):
        gen_log.warning("Invalid cookie signature %r", value)
        return None
    timestamp = int(parts[1])
    if timestamp < clock() - max_age_days * 86400:
        gen_log.warning("Expired cookie %r", value)
        return None
    if timestamp > clock() + 31 * 86400:
        # _cookie_signature does not hash a delimiter between the
        # parts of the cookie, so an attacker could transfer trailing
        # digits from the payload to the timestamp without altering the
        # signature.  For backwards compatibility, sanity-check timestamp
        # here instead of modifying _cookie_signature.
        gen_log.warning("Cookie timestamp in future; possible tampering %r",
                        value)
        return None
    if parts[1].startswith(b"0"):
        gen_log.warning("Tampered cookie %r", value)
        return None
    try:
        return base64.b64decode(parts[0])
    except Exception:
        return None


def _decode_fields_v2(value):
    def _consume_field(s):
        length, _, rest = s.partition(b':')
        n = int(length)
        field_value = rest[:n]
        # In python 3, indexing bytes returns small integers; we must
        # use a slice to get a byte string as in python 2.
        if rest[n:n + 1] != b'|':
            raise ValueError("malformed v2 signed value field")
        rest = rest[n + 1:]
        return field_value, rest

    rest = value[2:]  # remove version number
    key_version, rest = _consume_field(rest)
    timestamp, rest = _consume_field(rest)
    name_field, rest = _consume_field(rest)
    value_field, passed_sig = _consume_field(rest)
    return int(key_version), timestamp, name_field, value_field, passed_sig


def _decode_signed_value_v2(secret, name, value, max_age_days, clock):
    try:
        key_version, timestamp, name_field, value_field, passed_sig = _decode_fields_v2(value)
    except ValueError:
        return None
    signed_string = value[:-len(passed_sig)]

    if isinstance(secret, dict):
        try:
            secret = secret[key_version]
        except KeyError:
            return None

    expected_sig = _create_signature_v2(secret, signed_string)
    if not _time_independent_equals(passed_sig, expected_sig):
        return None
    if name_field != utf8(name):
        return None
    timestamp = int(timestamp)
    if timestamp < clock() - max_age_days * 86400:
        # The signature has expired.
        return None
    try:
        return base64.b64decode(value_field)
    except Exception:
        return None


def get_signature_key_version(value):
    value = utf8(value)
    version = _get_version(value)
    if version < 2:
        return None
    try:
        key_version, _, _, _, _ = _decode_fields_v2(value)
    except ValueError:
        return None

    return key_version


def _create_signature_v1(secret, *parts):
    hash = hmac.new(utf8(secret), digestmod=hashlib.sha1)
    for part in parts:
        hash.update(utf8(part))
    return utf8(hash.hexdigest())


def _create_signature_v2(secret, s):
    hash = hmac.new(utf8(secret), digestmod=hashlib.sha256)
    hash.update(utf8(s))
    return utf8(hash.hexdigest())


def _unquote_or_none(s):
    """None-safe wrapper around url_unescape to handle unamteched optional
    groups correctly.

    Note that args are passed as bytes so the handler can decide what
    encoding to use.
    """
    if s is None:
        return s
    return escape.url_unescape(s, encoding=None, plus=False)
