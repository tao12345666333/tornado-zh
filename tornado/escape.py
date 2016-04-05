#!/usr/bin/env python
# coding: utf-8
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

"""HTML, JSON, URLs, 和其他(格式)的转义/非转义方法.

也包含一些其他的各种字符串操作函数.
"""

from __future__ import absolute_import, division, print_function, with_statement

import re
import sys

from tornado.util import unicode_type, basestring_type, u

try:
    from urllib.parse import parse_qs as _parse_qs  # py3
except ImportError:
    from urlparse import parse_qs as _parse_qs  # Python 2.6+

try:
    import htmlentitydefs  # py2
except ImportError:
    import html.entities as htmlentitydefs  # py3

try:
    import urllib.parse as urllib_parse  # py3
except ImportError:
    import urllib as urllib_parse  # py2

import json

try:
    unichr
except NameError:
    unichr = chr

_XHTML_ESCAPE_RE = re.compile('[&<>"\']')
_XHTML_ESCAPE_DICT = {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;',
                      '\'': '&#39;'}


def xhtml_escape(value):
    """转义一个字符串使它在HTML 或XML 中有效.

    转义这些字符 ``<``, ``>``, ``"``, ``'``, 和 ``&``.
    当属性值使用转义字符串必须用引号括起来.

    .. versionchanged:: 3.2

       添加了单引号到转义字符串列表.
    """
    return _XHTML_ESCAPE_RE.sub(lambda match: _XHTML_ESCAPE_DICT[match.group(0)],
                                to_basestring(value))


def xhtml_unescape(value):
    """反转义一个已经XML转义过的字符串."""
    return re.sub(r"&(#?)(\w+?);", _convert_entity, _unicode(value))


# The fact that json_encode wraps json.dumps is an implementation detail.
# Please see https://github.com/tornadoweb/tornado/pull/706
# before sending a pull request that adds **kwargs to this function.
def json_encode(value):
    """将给定的Python 对象进行JSON 编码."""
    # JSON permits but does not require forward slashes to be escaped.
    # This is useful when json data is emitted in a <script> tag
    # in HTML, as it prevents </script> tags from prematurely terminating
    # the javascript.  Some json libraries do this escaping by default,
    # although python's standard library does not, so we do it here.
    # http://stackoverflow.com/questions/1580647/json-why-are-forward-slashes-escaped
    return json.dumps(value).replace("</", "<\\/")


def json_decode(value):
    """返回给定JSON 字符串的Python 对象."""
    return json.loads(to_basestring(value))


def squeeze(value):
    """使用单个空格代替所有空格字符组成的序列."""
    return re.sub(r"[\x00-\x20]+", " ", value).strip()


def url_escape(value, plus=True):
    """返回一个给定值的URL 编码版本.

    如果 ``plus`` 为true (默认值), 空格将被表示为"+"而不是"%20".
    这是适当的为查询字符串, 但不是一个URL路径组件. 注意此默认设置
    和Python的urllib 模块是相反的.

    .. versionadded:: 3.1
        该 ``plus`` 参数
    """
    quote = urllib_parse.quote_plus if plus else urllib_parse.quote
    return quote(utf8(value))


# python 3 changed things around enough that we need two separate
# implementations of url_unescape.  We also need our own implementation
# of parse_qs since python 3's version insists on decoding everything.
if sys.version_info[0] < 3:
    def url_unescape(value, encoding='utf-8', plus=True):
        """解码来自于URL 的给定值.

        该参数可以是一个字节或unicode 字符串.

        如果encoding 是None , 该结果将会是一个字节串. 否则, 该结果会是
        指定编码的unicode 字符串.

        如果 ``plus`` 是true (默认值), 加号将被解释为空格(文字加号必须被
        表示为"%2B"). 这是适用于查询字符串和form-encoded 的值, 但不是URL
        的路径组件. 注意该默认设置和Python 的urllib 模块是相反的.

        .. versionadded:: 3.1
           该 ``plus`` 参数
        """
        unquote = (urllib_parse.unquote_plus if plus else urllib_parse.unquote)
        if encoding is None:
            return unquote(utf8(value))
        else:
            return unicode_type(unquote(utf8(value)), encoding)

    parse_qs_bytes = _parse_qs
else:
    def url_unescape(value, encoding='utf-8', plus=True):
        """解码来自于URL 的给定值.

        该参数可以是一个字节或unicode 字符串.

        如果encoding 是None , 该结果将会是一个字节串. 否则, 该结果会是
        指定编码的unicode 字符串.

        如果 ``plus`` 是true (默认值), 加号将被解释为空格(文字加号必须被
        表示为"%2B"). 这是适用于查询字符串和form-encoded 的值, 但不是URL
        的路径组件. 注意该默认设置和Python 的urllib 模块是相反的.

        .. versionadded:: 3.1
           该 ``plus`` 参数
        """
        if encoding is None:
            if plus:
                # unquote_to_bytes doesn't have a _plus variant
                value = to_basestring(value).replace('+', ' ')
            return urllib_parse.unquote_to_bytes(value)
        else:
            unquote = (urllib_parse.unquote_plus if plus
                       else urllib_parse.unquote)
            return unquote(to_basestring(value), encoding=encoding)

    def parse_qs_bytes(qs, keep_blank_values=False, strict_parsing=False):
        """Parses a query string like urlparse.parse_qs, but returns the
        values as byte strings.

        Keys still become type str (interpreted as latin1 in python3!)
        because it's too painful to keep them as byte strings in
        python3 and in practice they're nearly always ascii anyway.
        """
        # This is gross, but python3 doesn't give us another way.
        # Latin1 is the universal donor of character encodings.
        result = _parse_qs(qs, keep_blank_values, strict_parsing,
                           encoding='latin1', errors='strict')
        encoded = {}
        for k, v in result.items():
            encoded[k] = [i.encode('latin1') for i in v]
        return encoded


_UTF8_TYPES = (bytes, type(None))


def utf8(value):
    """将字符串参数转换为字节字符串.

    如果该参数已经是一个字节字符串或None, 则原样返回.
    否则它必须是一个unicode 字符串并且被编码成utf8.
    """
    if isinstance(value, _UTF8_TYPES):
        return value
    if not isinstance(value, unicode_type):
        raise TypeError(
            "Expected bytes, unicode, or None; got %r" % type(value)
        )
    return value.encode("utf-8")

_TO_UNICODE_TYPES = (unicode_type, type(None))


def to_unicode(value):
    """将字符串参数转换为unicode 字符串.

    如果该参数已经是一个unicode 字符串或None, 则原样返回.
    否则它必须是一个字节字符串并且被解码成utf8.
    """
    if isinstance(value, _TO_UNICODE_TYPES):
        return value
    if not isinstance(value, bytes):
        raise TypeError(
            "Expected bytes, unicode, or None; got %r" % type(value)
        )
    return value.decode("utf-8")

# to_unicode was previously named _unicode not because it was private,
# but to avoid conflicts with the built-in unicode() function/type
_unicode = to_unicode

# When dealing with the standard library across python 2 and 3 it is
# sometimes useful to have a direct conversion to the native string type
if str is unicode_type:
    native_str = to_unicode
else:
    native_str = utf8

_BASESTRING_TYPES = (basestring_type, type(None))


def to_basestring(value):
    """将字符串参数转换为basestring 的子类.

    在python2 中, 字节字符串和unicode 字符串几乎是可以互换的,
    所以函数处理一个用户提供的参数与ascii 字符串常量相结合,
    可以使用和应该返回用户提供的类型. 在python3 中, 这两个类型
    不可以互换, 所以这个方法必须转换字节字符串为unicode 字符串.
    """
    if isinstance(value, _BASESTRING_TYPES):
        return value
    if not isinstance(value, bytes):
        raise TypeError(
            "Expected bytes, unicode, or None; got %r" % type(value)
        )
    return value.decode("utf-8")


def recursive_unicode(obj):
    """伴随一个简单的数据结构, 转换字节字符串为unicode 字符串.

    支持列表, 元组, 和字典.
    """
    if isinstance(obj, dict):
        return dict((recursive_unicode(k), recursive_unicode(v)) for (k, v) in obj.items())
    elif isinstance(obj, list):
        return list(recursive_unicode(i) for i in obj)
    elif isinstance(obj, tuple):
        return tuple(recursive_unicode(i) for i in obj)
    elif isinstance(obj, bytes):
        return to_unicode(obj)
    else:
        return obj

# I originally used the regex from
# http://daringfireball.net/2010/07/improved_regex_for_matching_urls
# but it gets all exponential on certain patterns (such as too many trailing
# dots), causing the regex matcher to never return.
# This regex should avoid those problems.
# Use to_unicode instead of tornado.util.u - we don't want backslashes getting
# processed as escapes.
_URL_RE = re.compile(to_unicode(r"""\b((?:([\w-]+):(/{1,3})|www[.])(?:(?:(?:[^\s&()]|&amp;|&quot;)*(?:[^!"#$%&'()*+,.:;<=>?@\[\]^`{|}~\s]))|(?:\((?:[^\s&()]|&amp;|&quot;)*\)))+)"""))


def linkify(text, shorten=False, extra_params="",
            require_protocol=False, permitted_protocols=["http", "https"]):
    """转换纯文本为带有链接的HTML.

    例如: ``linkify("Hello http://tornadoweb.org!")`` 将返回
    ``Hello <a href="http://tornadoweb.org">http://tornadoweb.org</a>!``

    参数:

    * ``shorten``: 长url 将被缩短展示.

    * ``extra_params``: 额外的文本中的链接标签, 或一个可调用的
        带有该链接作为一个参数并返回该额外的文本.
        e.g. ``linkify(text, extra_params='rel="nofollow" class="external"')``,
        或::

            def extra_params_cb(url):
                if url.startswith("http://example.com"):
                    return 'class="internal"'
                else:
                    return 'class="external" rel="nofollow"'
            linkify(text, extra_params=extra_params_cb)

    * ``require_protocol``: 只有链接url 包括一个协议. 如果这是False,
        例如www.facebook.com 这样的url 也将被linkified.

    * ``permitted_protocols``: 协议的列表(或集合)应该被linkified,
        e.g. ``linkify(text, permitted_protocols=["http", "ftp",
        "mailto"])``. 这是非常不安全的, 包括协议, 比如 ``javascript``.
    """
    if extra_params and not callable(extra_params):
        extra_params = " " + extra_params.strip()

    def make_link(m):
        url = m.group(1)
        proto = m.group(2)
        if require_protocol and not proto:
            return url  # not protocol, no linkify

        if proto and proto not in permitted_protocols:
            return url  # bad protocol, no linkify

        href = m.group(1)
        if not proto:
            href = "http://" + href   # no proto specified, use http

        if callable(extra_params):
            params = " " + extra_params(href).strip()
        else:
            params = extra_params

        # clip long urls. max_len is just an approximation
        max_len = 30
        if shorten and len(url) > max_len:
            before_clip = url
            if proto:
                proto_len = len(proto) + 1 + len(m.group(3) or "")  # +1 for :
            else:
                proto_len = 0

            parts = url[proto_len:].split("/")
            if len(parts) > 1:
                # Grab the whole host part plus the first bit of the path
                # The path is usually not that interesting once shortened
                # (no more slug, etc), so it really just provides a little
                # extra indication of shortening.
                url = url[:proto_len] + parts[0] + "/" + \
                    parts[1][:8].split('?')[0].split('.')[0]

            if len(url) > max_len * 1.5:  # still too long
                url = url[:max_len]

            if url != before_clip:
                amp = url.rfind('&')
                # avoid splitting html char entities
                if amp > max_len - 5:
                    url = url[:amp]
                url += "..."

                if len(url) >= len(before_clip):
                    url = before_clip
                else:
                    # full url is visible on mouse-over (for those who don't
                    # have a status bar, such as Safari by default)
                    params += ' title="%s"' % href

        return u('<a href="%s"%s>%s</a>') % (href, params, url)

    # First HTML-escape so that our strings are all safe.
    # The regex is modified to avoid character entites other than &amp; so
    # that we won't pick up &quot;, etc.
    text = _unicode(xhtml_escape(text))
    return _URL_RE.sub(make_link, text)


def _convert_entity(m):
    if m.group(1) == "#":
        try:
            if m.group(2)[:1].lower() == 'x':
                return unichr(int(m.group(2)[1:], 16))
            else:
                return unichr(int(m.group(2)))
        except ValueError:
            return "&#%s;" % m.group(2)
    try:
        return _HTML_UNICODE_MAP[m.group(2)]
    except KeyError:
        return "&%s;" % m.group(2)


def _build_unicode_map():
    unicode_map = {}
    for name, value in htmlentitydefs.name2codepoint.items():
        unicode_map[name] = unichr(value)
    return unicode_map

_HTML_UNICODE_MAP = _build_unicode_map()
