#!/usr/bin/env python
# -*- coding: utf-8 -*-
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

"""生成本地化字符串的翻译方法.

要加载区域设置并生成一个翻译后的字符串::

    user_locale = tornado.locale.get("es_LA")
    print user_locale.translate("Sign out")

`tornado.locale.get()` 返回最匹配的语言环境, 不一定是你请求的特定的语言
环境. 你可以用额外的参数来支持多元化给 `~Locale.translate()`, e.g.::

    people = [...]
    message = user_locale.translate(
        "%(list)s is online", "%(list)s are online", len(people))
    print message % {"list": user_locale.list(people)}

如果 ``len(people) == 1`` 则选择第一个字符串, 否则选择第二个字符串.

应用程序应该调用 `load_translations` (它使用一个简单的CSV 格式) 或
`load_gettext_translations` (它通过使用 `gettext` 和相关工具支持
``.mo`` 格式) 其中之一.  如果没有方法被调用, `Locale.translate`
方法将会直接的返回原本的字符串.
"""

from __future__ import absolute_import, division, print_function, with_statement

import codecs
import csv
import datetime
from io import BytesIO
import numbers
import os
import re

from tornado import escape
from tornado.log import gen_log
from tornado.util import u

from tornado._locale_data import LOCALE_NAMES

_default_locale = "en_US"
_translations = {}
_supported_locales = frozenset([_default_locale])
_use_gettext = False
CONTEXT_SEPARATOR = "\x04"


def get(*locale_codes):
    """返回给定区域代码的最近匹配.

    我们按顺序遍历所有给定的区域代码. 如果我们有一个确定的或模糊的匹配
    代码(e.g., "en" 匹配 "en_US"), 则我们返回该区域. 否则我们移动到列表
    中的下一个代码.

    默认情况下我们返回 ``en_US`` 如果没有发现任何对指定区域的翻译.
    你可以改变默认区域通过 `set_default_locale()`.
    """
    return Locale.get_closest(*locale_codes)


def set_default_locale(code):
    """设置默认区域.

    默认语言环境被假定为用于系统中所有的字符串的语言. 从磁盘加载的翻译
    是从默认的语言环境到目标区域的映射. 因此, 你不需要为默认的语言环境
    创建翻译文件.
    """
    global _default_locale
    global _supported_locales
    _default_locale = code
    _supported_locales = frozenset(list(_translations.keys()) + [_default_locale])


def load_translations(directory, encoding=None):
    """从目录中的CSV 文件加载翻译.

    翻译是带有任意的Python 风格指定的占位符的字符串(e.g., ``My name is %(name)s``)
    及其相关翻译.

    该目录应该有以下形式的翻译文件 ``LOCALE.csv``, e.g. ``es_GT.csv``.
    该CSV 文件应该有两列或三列: 字符串, 翻译, 和可选的多个指标. 复数的指标
    应该是"plural" 或 "singular" 其中之一. 一个给定的字符串可以同时有单数和
    复数形式. 例如 ``%(name)s liked this`` 可能有一个不同的动词组合, 这取决于
    %(name)s 是一个名字还是一个名字列表. 在CSV文件里应该有两个针对于该字符串
    的行, 一个用指示器指示"singular" (奇数), 一个指示"plural" (复数).
    对于没有动词的字符串，将改变翻译, 简单的使用"unknown" 或空字符串
    (或者不包括在所有列中的).

    这个文件默认使用 `csv` 模块的"excel"进行读操作. 这种格式在逗号后面不
    应该包含空格.

    如果没有给定 ``encoding`` 参数, 如果该文件包含一个
    byte-order marker (BOM), 编码格式将会自动检测(在UTF-8 和UTF-16
    之间), 如果没有BOM将默认为UTF-8.

    例如翻译 ``es_LA.csv``::

        "I love you","Te amo"
        "%(name)s liked this","A %(name)s les gustó esto","plural"
        "%(name)s liked this","A %(name)s le gustó esto","singular"

    .. versionchanged:: 4.3
       添加 ``encoding`` 参数. 添加对BOM-based 的编码检测, UTF-16,
       和 UTF-8-with-BOM.
    """
    global _translations
    global _supported_locales
    _translations = {}
    for path in os.listdir(directory):
        if not path.endswith(".csv"):
            continue
        locale, extension = path.split(".")
        if not re.match("[a-z]+(_[A-Z]+)?$", locale):
            gen_log.error("Unrecognized locale %r (path: %s)", locale,
                          os.path.join(directory, path))
            continue
        full_path = os.path.join(directory, path)
        if encoding is None:
            # Try to autodetect encoding based on the BOM.
            with open(full_path, 'rb') as f:
                data = f.read(len(codecs.BOM_UTF16_LE))
            if data in (codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE):
                encoding = 'utf-16'
            else:
                # utf-8-sig is "utf-8 with optional BOM". It's discouraged
                # in most cases but is common with CSV files because Excel
                # cannot read utf-8 files without a BOM.
                encoding = 'utf-8-sig'
        try:
            # python 3: csv.reader requires a file open in text mode.
            # Force utf8 to avoid dependence on $LANG environment variable.
            f = open(full_path, "r", encoding=encoding)
        except TypeError:
            # python 2: csv can only handle byte strings (in ascii-compatible
            # encodings), which we decode below. Transcode everything into
            # utf8 before passing it to csv.reader.
            f = BytesIO()
            with codecs.open(full_path, "r", encoding=encoding) as infile:
                f.write(escape.utf8(infile.read()))
            f.seek(0)
        _translations[locale] = {}
        for i, row in enumerate(csv.reader(f)):
            if not row or len(row) < 2:
                continue
            row = [escape.to_unicode(c).strip() for c in row]
            english, translation = row[:2]
            if len(row) > 2:
                plural = row[2] or "unknown"
            else:
                plural = "unknown"
            if plural not in ("plural", "singular", "unknown"):
                gen_log.error("Unrecognized plural indicator %r in %s line %d",
                              plural, path, i + 1)
                continue
            _translations[locale].setdefault(plural, {})[english] = translation
        f.close()
    _supported_locales = frozenset(list(_translations.keys()) + [_default_locale])
    gen_log.debug("Supported locales: %s", sorted(_supported_locales))


def load_gettext_translations(directory, domain):
    """从 `gettext` 的区域树加载翻译

    区域树和系统的 ``/usr/share/locale`` 很类似, 例如::

        {directory}/{lang}/LC_MESSAGES/{domain}.mo

    让你的应用程序翻译有三步是必须的:

    1. 生成POT翻译文件::

        xgettext --language=Python --keyword=_:1,2 -d mydomain file1.py file2.html etc

    2. 合并现有的 POT 文件::

        msgmerge old.po mydomain.po > new.po

    3. 编译::

        msgfmt mydomain.po -o {directory}/pt_BR/LC_MESSAGES/mydomain.mo
    """
    import gettext
    global _translations
    global _supported_locales
    global _use_gettext
    _translations = {}
    for lang in os.listdir(directory):
        if lang.startswith('.'):
            continue  # skip .svn, etc
        if os.path.isfile(os.path.join(directory, lang)):
            continue
        try:
            os.stat(os.path.join(directory, lang, "LC_MESSAGES", domain + ".mo"))
            _translations[lang] = gettext.translation(domain, directory,
                                                      languages=[lang])
        except Exception as e:
            gen_log.error("Cannot load translation for '%s': %s", lang, str(e))
            continue
    _supported_locales = frozenset(list(_translations.keys()) + [_default_locale])
    _use_gettext = True
    gen_log.debug("Supported locales: %s", sorted(_supported_locales))


def get_supported_locales():
    """返回所有支持的语言代码列表."""
    return _supported_locales


class Locale(object):
    """对象代表一个区域.

    在调用 `load_translations` 或 `load_gettext_translations` 之后,
    调用 `get` 或 `get_closest` 以得到一个Locale对象.
    """
    @classmethod
    def get_closest(cls, *locale_codes):
        """返回给定区域代码的最近匹配."""
        for code in locale_codes:
            if not code:
                continue
            code = code.replace("-", "_")
            parts = code.split("_")
            if len(parts) > 2:
                continue
            elif len(parts) == 2:
                code = parts[0].lower() + "_" + parts[1].upper()
            if code in _supported_locales:
                return cls.get(code)
            if parts[0].lower() in _supported_locales:
                return cls.get(parts[0].lower())
        return cls.get(_default_locale)

    @classmethod
    def get(cls, code):
        """返回给定区域代码的Locale.

        如果这个方法不支持, 我们将抛出一个异常.
        """
        if not hasattr(cls, "_cache"):
            cls._cache = {}
        if code not in cls._cache:
            assert code in _supported_locales
            translations = _translations.get(code, None)
            if translations is None:
                locale = CSVLocale(code, {})
            elif _use_gettext:
                locale = GettextLocale(code, translations)
            else:
                locale = CSVLocale(code, translations)
            cls._cache[code] = locale
        return cls._cache[code]

    def __init__(self, code, translations):
        self.code = code
        self.name = LOCALE_NAMES.get(code, {}).get("name", u("Unknown"))
        self.rtl = False
        for prefix in ["fa", "ar", "he"]:
            if self.code.startswith(prefix):
                self.rtl = True
                break
        self.translations = translations

        # Initialize strings for date formatting
        _ = self.translate
        self._months = [
            _("January"), _("February"), _("March"), _("April"),
            _("May"), _("June"), _("July"), _("August"),
            _("September"), _("October"), _("November"), _("December")]
        self._weekdays = [
            _("Monday"), _("Tuesday"), _("Wednesday"), _("Thursday"),
            _("Friday"), _("Saturday"), _("Sunday")]

    def translate(self, message, plural_message=None, count=None):
        """返回给定信息在当前区域环境下的翻译.

        如果给定了 ``plural_message`` , 你也必须有提供 ``count``.
        当 ``count != 1`` 时, 我们返回 ``plural_message`` 并且当
        ``count == 1`` 时, 我们返回给定消息的单数形式.
        """
        raise NotImplementedError()

    def pgettext(self, context, message, plural_message=None, count=None):
        raise NotImplementedError()

    def format_date(self, date, gmt_offset=0, relative=True, shorter=False,
                    full_format=False):
        """格式化给定的日期(应该是GMT时间).

        默认情况下, 我们返回一个相对时间(e.g., "2 minutes ago"). 你
        可以返回一个绝对日期字符串通过 ``relative=False`` 参数.

        你可以强制使用一个完整的格式化日期("July 10, 1980") 通过
        ``full_format=True`` 参数.

        这个方法主要用于过去的日期. 对于将来的日期, 我们退回到
        全格式.
        """
        if isinstance(date, numbers.Real):
            date = datetime.datetime.utcfromtimestamp(date)
        now = datetime.datetime.utcnow()
        if date > now:
            if relative and (date - now).seconds < 60:
                # Due to click skew, things are some things slightly
                # in the future. Round timestamps in the immediate
                # future down to now in relative mode.
                date = now
            else:
                # Otherwise, future dates always use the full format.
                full_format = True
        local_date = date - datetime.timedelta(minutes=gmt_offset)
        local_now = now - datetime.timedelta(minutes=gmt_offset)
        local_yesterday = local_now - datetime.timedelta(hours=24)
        difference = now - date
        seconds = difference.seconds
        days = difference.days

        _ = self.translate
        format = None
        if not full_format:
            if relative and days == 0:
                if seconds < 50:
                    return _("1 second ago", "%(seconds)d seconds ago",
                             seconds) % {"seconds": seconds}

                if seconds < 50 * 60:
                    minutes = round(seconds / 60.0)
                    return _("1 minute ago", "%(minutes)d minutes ago",
                             minutes) % {"minutes": minutes}

                hours = round(seconds / (60.0 * 60))
                return _("1 hour ago", "%(hours)d hours ago",
                         hours) % {"hours": hours}

            if days == 0:
                format = _("%(time)s")
            elif days == 1 and local_date.day == local_yesterday.day and \
                    relative:
                format = _("yesterday") if shorter else \
                    _("yesterday at %(time)s")
            elif days < 5:
                format = _("%(weekday)s") if shorter else \
                    _("%(weekday)s at %(time)s")
            elif days < 334:  # 11mo, since confusing for same month last year
                format = _("%(month_name)s %(day)s") if shorter else \
                    _("%(month_name)s %(day)s at %(time)s")

        if format is None:
            format = _("%(month_name)s %(day)s, %(year)s") if shorter else \
                _("%(month_name)s %(day)s, %(year)s at %(time)s")

        tfhour_clock = self.code not in ("en", "en_US", "zh_CN")
        if tfhour_clock:
            str_time = "%d:%02d" % (local_date.hour, local_date.minute)
        elif self.code == "zh_CN":
            str_time = "%s%d:%02d" % (
                (u('\u4e0a\u5348'), u('\u4e0b\u5348'))[local_date.hour >= 12],
                local_date.hour % 12 or 12, local_date.minute)
        else:
            str_time = "%d:%02d %s" % (
                local_date.hour % 12 or 12, local_date.minute,
                ("am", "pm")[local_date.hour >= 12])

        return format % {
            "month_name": self._months[local_date.month - 1],
            "weekday": self._weekdays[local_date.weekday()],
            "day": str(local_date.day),
            "year": str(local_date.year),
            "time": str_time
        }

    def format_day(self, date, gmt_offset=0, dow=True):
        """将给定日期格式化为一周的某一天.

        例如: "Monday, January 22". 你可以移除星期几通过
        ``dow=False``.
        """
        local_date = date - datetime.timedelta(minutes=gmt_offset)
        _ = self.translate
        if dow:
            return _("%(weekday)s, %(month_name)s %(day)s") % {
                "month_name": self._months[local_date.month - 1],
                "weekday": self._weekdays[local_date.weekday()],
                "day": str(local_date.day),
            }
        else:
            return _("%(month_name)s %(day)s") % {
                "month_name": self._months[local_date.month - 1],
                "day": str(local_date.day),
            }

    def list(self, parts):
        """Returns a comma-separated list for the given list of parts.

        The format is, e.g., "A, B and C", "A and B" or just "A" for lists
        of size 1.
        """
        _ = self.translate
        if len(parts) == 0:
            return ""
        if len(parts) == 1:
            return parts[0]
        comma = u(' \u0648 ') if self.code.startswith("fa") else u(", ")
        return _("%(commas)s and %(last)s") % {
            "commas": comma.join(parts[:-1]),
            "last": parts[len(parts) - 1],
        }

    def friendly_number(self, value):
        """Returns a comma-separated number for the given integer."""
        if self.code not in ("en", "en_US"):
            return str(value)
        value = str(value)
        parts = []
        while value:
            parts.append(value[-3:])
            value = value[:-3]
        return ",".join(reversed(parts))


class CSVLocale(Locale):
    """区域设置使用tornado 的CSV翻译格式."""
    def translate(self, message, plural_message=None, count=None):
        if plural_message is not None:
            assert count is not None
            if count != 1:
                message = plural_message
                message_dict = self.translations.get("plural", {})
            else:
                message_dict = self.translations.get("singular", {})
        else:
            message_dict = self.translations.get("unknown", {})
        return message_dict.get(message, message)

    def pgettext(self, context, message, plural_message=None, count=None):
        if self.translations:
            gen_log.warning('pgettext is not supported by CSVLocale')
        return self.translate(message, plural_message, count)


class GettextLocale(Locale):
    """Locale implementation using the `gettext` module."""
    def __init__(self, code, translations):
        try:
            # python 2
            self.ngettext = translations.ungettext
            self.gettext = translations.ugettext
        except AttributeError:
            # python 3
            self.ngettext = translations.ngettext
            self.gettext = translations.gettext
        # self.gettext must exist before __init__ is called, since it
        # calls into self.translate
        super(GettextLocale, self).__init__(code, translations)

    def translate(self, message, plural_message=None, count=None):
        if plural_message is not None:
            assert count is not None
            return self.ngettext(message, plural_message, count)
        else:
            return self.gettext(message)

    def pgettext(self, context, message, plural_message=None, count=None):
        """Allows to set context for translation, accepts plural forms.

        Usage example::

            pgettext("law", "right")
            pgettext("good", "right")

        Plural message example::

            pgettext("organization", "club", "clubs", len(clubs))
            pgettext("stick", "club", "clubs", len(clubs))

        To generate POT file with context, add following options to step 1
        of `load_gettext_translations` sequence::

            xgettext [basic options] --keyword=pgettext:1c,2 --keyword=pgettext:1c,2,3

        .. versionadded:: 4.2
        """
        if plural_message is not None:
            assert count is not None
            msgs_with_ctxt = ("%s%s%s" % (context, CONTEXT_SEPARATOR, message),
                              "%s%s%s" % (context, CONTEXT_SEPARATOR, plural_message),
                              count)
            result = self.ngettext(*msgs_with_ctxt)
            if CONTEXT_SEPARATOR in result:
                # Translation not found
                result = self.ngettext(message, plural_message, count)
            return result
        else:
            msg_with_ctxt = "%s%s%s" % (context, CONTEXT_SEPARATOR, message)
            result = self.gettext(msg_with_ctxt)
            if CONTEXT_SEPARATOR in result:
                # Translation not found
                result = message
            return result
