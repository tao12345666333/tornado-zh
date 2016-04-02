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

"""一个简单的模板系统, 将模板编译成Python代码.

基本用法如下::

    t = template.Template("<html>{{ myvalue }}</html>")
    print t.generate(myvalue="XXX")

`Loader` 是一个从根目录加载模板并缓存编译过的模板的类::

    loader = template.Loader("/home/btaylor")
    print loader.load("test.html").generate(myvalue="XXX")

我们编译所有模板至原生的Python. 错误报告是目前... uh,
很有趣. 模板语法如下::

    ### base.html
    <html>
      <head>
        <title>{% block title %}Default title{% end %}</title>
      </head>
      <body>
        <ul>
          {% for student in students %}
            {% block student %}
              <li>{{ escape(student.name) }}</li>
            {% end %}
          {% end %}
        </ul>
      </body>
    </html>

    ### bold.html
    {% extends "base.html" %}

    {% block title %}A bolder title{% end %}

    {% block student %}
      <li><span style="bold">{{ escape(student.name) }}</span></li>
    {% end %}

与大多数其他模板系统不同, 我们没有在你的语句中可包含的表达式上放置任何约束.
``if`` 和 ``for`` 语句块完全翻译成了Python, 所以你可以写复杂的表达式例如::

   {% for student in [p for p in people if p.student and p.age > 23] %}
     <li>{{ escape(student.name) }}</li>
   {% end %}

直接翻译成Python意味着你可以很简单的在表达式中使用函数, 就像在上面例子中的
``escape()`` 函数. 你可以把函数传递到你的模板中就像其他任何变量一样(在一个
`.RequestHandler` 中, 复写 `.RequestHandler.get_template_namespace`)::

   ### Python code
   def add(x, y):
      return x + y
   template.execute(add=add)

   ### The template
   {{ add(1, 2) }}

默认情况下我们提供了 `escape() <.xhtml_escape>`, `.url_escape()`,
`.json_encode()`, 和 `.squeeze()` 函数给所有模板.

典型的应用程序不会手动创建 `Template` 或 `Loader` 实例, 而是使用
`tornado.web.RequestHandler` 中的 `~.RequestHandler.render` 和
`~.RequestHandler.render_string` 方法, 这些方法自动的基于
``template_path`` `.Application` 设置加载模板.

以 ``_tt_`` 为前缀命名的变量是模板系统保留的, 不应该被应用程序的
代码使用.

语法参考
----------------

模板表达式被双花括号包围: ``{{ ... }}``. 内容可以是任何python表达式,
会根据当前自动转义(autoescape)设置被转义并且插入到输出. 其他模板指令
使用 ``{% %}``. 这些标签可以被转义作为 ``{{!`` 和 ``{%!`` 如果你需要
在输出中包含一个原义的 ``{{`` 或 ``{%`` .

为了注释掉一段让它从输出中省略, 使用 ``{# ... #}`` 包住它.

``{% apply *function* %}...{% end %}``
    在 ``apply`` 和 ``end`` 之间应用一个函数到所有模板代码的输出::

        {% apply linkify %}{{name}} said: {{message}}{% end %}

    注意作为一个实现细节使用块会执行嵌套函数, 因此可能产生奇怪的
    相互作用, 包括通过 ``{% set %}`` 设置的变量, 或者在循环中使用
    ``{% break %}`` 或 ``{% continue %}`` .

``{% autoescape *function* %}``
    为当前文件设置自动转义(autoescape)模式. 这不会影响其他文件, 即使
    是那些通过 ``{% include %}`` 引用的文件. 注意自动转义也可以全局
    设置, 在 `.Application` 或 `Loader` 中.::

        {% autoescape xhtml_escape %}
        {% autoescape None %}

``{% block *name* %}...{% end %}``
    标明了一个已命名的, 可以使用 ``{% extends %}`` 被替换的块.
    在父模板中的块将会被子模板中同名块的内容替换.::

        <!-- base.html -->
        <title>{% block title %}Default title{% end %}</title>

        <!-- mypage.html -->
        {% extends "base.html" %}
        {% block title %}My page title{% end %}

``{% comment ... %}``
    一个将会从模板的输出中移除的注释. 注意这里没有 ``{% end %}`` 标签;
    该注释从 ``comment`` 这个词开始到 ``%}`` 标签关闭.

``{% extends *filename* %}``
    从另一个模板继承. 使用 ``extends`` 的模板应该包含一个或多个
    ``block`` 标签以替换父模板中的内容. 子模板内任何不包含在一个
    ``block`` 标签中的内容都将被忽略. 例如, 参见 ``{% block %}`` 标签.

``{% for *var* in *expr* %}...{% end %}``
    和python的 ``for`` 语句一样.  ``{% break %}`` 和
    ``{% continue %}`` 可以用在循环里.

``{% from *x* import *y* %}``
    和python的 ``import`` 语句一样.

``{% if *condition* %}...{% elif *condition* %}...{% else %}...{% end %}``
    条件语句 - 输出第一个条件为true 的部分.  ( ``elif`` 和 ``else`` 部分是
    可选的)

``{% import *module* %}``
    和python的 ``import`` 语句一样.

``{% include *filename* %}``
    包含另一个模板文件. 被包含的文件可以看到所有局部变量就像它被直接
    复制到了该 ``include`` 指令的位置( ``{% autoescape %}`` 指令是一
    个异常). 替代的, ``{% module Template(filename, **kwargs) %}``
    可能被用来包含另外的有独立命名空间的模板.

``{% module *expr* %}``
    渲染一个 `~tornado.web.UIModule`. 该 ``UIModule`` 的输出没有
    转义::

        {% module Template("foo.html", arg=42) %}

    ``UIModules`` 是 `tornado.web.RequestHandler` 类(尤其是它的
    ``render`` 方法)的一个方法, 并且当模板系统在其他上下文中使用
    时, 它将不工作.

``{% raw *expr* %}``
    输出给定表达式的结果并且不会转义.

``{% set *x* = *y* %}``
    设置一个局部变量.

``{% try %}...{% except %}...{% else %}...{% finally %}...{% end %}``
    和python的 ``try`` 语句一样.

``{% while *condition* %}... {% end %}``
    和python的 ``while`` 语句一样. ``{% break %}`` 和
    ``{% continue %}`` 可以用在循环里.

``{% whitespace *mode* %}``
    为当前文件的剩余部分设置空白模式(whitespace mode)
    (或直到下一个 ``{% whitespace %}`` 指令). 参见
    `filter_whitespace` 查看可用参数. Tornado 4.3中新增.
"""

from __future__ import absolute_import, division, print_function, with_statement

import datetime
import linecache
import os.path
import posixpath
import re
import threading

from tornado import escape
from tornado.log import app_log
from tornado.util import ObjectDict, exec_in, unicode_type

try:
    from cStringIO import StringIO  # py2
except ImportError:
    from io import StringIO  # py3

_DEFAULT_AUTOESCAPE = "xhtml_escape"
_UNSET = object()


def filter_whitespace(mode, text):
    """根据 ``mode`` 转换空白到 ``text`` .

    可用的模式有:

    * ``all``: 返回所有未更改的空白.
    * ``single``: 压缩连串的空白用一个空白字符代替, 保留换行符.
    * ``oneline``: 压缩所有空白到一个空格字符, 在这个过程中移除所有换行符.

    .. versionadded:: 4.3
    """
    if mode == 'all':
        return text
    elif mode == 'single':
        text = re.sub(r"([\t ]+)", " ", text)
        text = re.sub(r"(\s*\n\s*)", "\n", text)
        return text
    elif mode == 'oneline':
        return re.sub(r"(\s+)", " ", text)
    else:
        raise Exception("invalid whitespace mode %s" % mode)


class Template(object):
    """编译模板.

    我们从给定的template_string编译到Python. 你可以使用generate()
    用变量生成模板.
    """
    # note that the constructor's signature is not extracted with
    # autodoc because _UNSET looks like garbage.  When changing
    # this signature update website/sphinx/template.rst too.
    def __init__(self, template_string, name="<string>", loader=None,
                 compress_whitespace=_UNSET, autoescape=_UNSET,
                 whitespace=None):
        """构造一个模板.

        :arg str template_string: 模板文件的内容.
        :arg str name: 被加载的模板文件名(用于错误信息).
        :arg tornado.template.BaseLoader loader: `~tornado.template.BaseLoader`
            负责该模板, 用于解决 ``{% include %}`` 和 ``{% extend %}`` 指令.
        :arg bool compress_whitespace: 自从Tornado 4.3过时了.
            如果为true, 相当于 ``whitespace="single"`` ,
            如果为false, 相当于 ``whitespace="all"`` .
        :arg str autoescape: 在模板命名空间中的函数名, 默认情况下为 ``None``
            以禁用转义.
        :arg str whitespace: 一个指定处理whitespace 的字符串; 参见
            `filter_whitespace` 了解可选项.

        .. versionchanged:: 4.3
           增加 ``whitespace`` 参数; 弃用 ``compress_whitespace``.
        """
        self.name = escape.native_str(name)

        if compress_whitespace is not _UNSET:
            # Convert deprecated compress_whitespace (bool) to whitespace (str).
            if whitespace is not None:
                raise Exception("cannot set both whitespace and compress_whitespace")
            whitespace = "single" if compress_whitespace else "all"
        if whitespace is None:
            if loader and loader.whitespace:
                whitespace = loader.whitespace
            else:
                # Whitespace defaults by filename.
                if name.endswith(".html") or name.endswith(".js"):
                    whitespace = "single"
                else:
                    whitespace = "all"
        # Validate the whitespace setting.
        filter_whitespace(whitespace, '')

        if autoescape is not _UNSET:
            self.autoescape = autoescape
        elif loader:
            self.autoescape = loader.autoescape
        else:
            self.autoescape = _DEFAULT_AUTOESCAPE

        self.namespace = loader.namespace if loader else {}
        reader = _TemplateReader(name, escape.native_str(template_string),
                                 whitespace)
        self.file = _File(self, _parse(reader, self))
        self.code = self._generate_python(loader)
        self.loader = loader
        try:
            # Under python2.5, the fake filename used here must match
            # the module name used in __name__ below.
            # The dont_inherit flag prevents template.py's future imports
            # from being applied to the generated code.
            self.compiled = compile(
                escape.to_unicode(self.code),
                "%s.generated.py" % self.name.replace('.', '_'),
                "exec", dont_inherit=True)
        except Exception:
            formatted_code = _format_code(self.code).rstrip()
            app_log.error("%s code:\n%s", self.name, formatted_code)
            raise

    def generate(self, **kwargs):
        """用给定参数生成此模板."""
        namespace = {
            "escape": escape.xhtml_escape,
            "xhtml_escape": escape.xhtml_escape,
            "url_escape": escape.url_escape,
            "json_encode": escape.json_encode,
            "squeeze": escape.squeeze,
            "linkify": escape.linkify,
            "datetime": datetime,
            "_tt_utf8": escape.utf8,  # for internal use
            "_tt_string_types": (unicode_type, bytes),
            # __name__ and __loader__ allow the traceback mechanism to find
            # the generated source code.
            "__name__": self.name.replace('.', '_'),
            "__loader__": ObjectDict(get_source=lambda name: self.code),
        }
        namespace.update(self.namespace)
        namespace.update(kwargs)
        exec_in(self.compiled, namespace)
        execute = namespace["_tt_execute"]
        # Clear the traceback module's cache of source data now that
        # we've generated a new template (mainly for this module's
        # unittests, where different tests reuse the same name).
        linecache.clearcache()
        return execute()

    def _generate_python(self, loader):
        buffer = StringIO()
        try:
            # named_blocks maps from names to _NamedBlock objects
            named_blocks = {}
            ancestors = self._get_ancestors(loader)
            ancestors.reverse()
            for ancestor in ancestors:
                ancestor.find_named_blocks(loader, named_blocks)
            writer = _CodeWriter(buffer, named_blocks, loader,
                                 ancestors[0].template)
            ancestors[0].generate(writer)
            return buffer.getvalue()
        finally:
            buffer.close()

    def _get_ancestors(self, loader):
        ancestors = [self.file]
        for chunk in self.file.body.chunks:
            if isinstance(chunk, _ExtendsBlock):
                if not loader:
                    raise ParseError("{% extends %} block found, but no "
                                     "template loader")
                template = loader.load(chunk.name, self.name)
                ancestors.extend(template._get_ancestors(loader))
        return ancestors


class BaseLoader(object):
    """模板加载器的基类.

    你必须使用一个模板加载器来使用模板的构造器例如 ``{% extends %}``
    和 ``{% include %}``. 加载器在所有模板首次加载之后进行缓存.
    """
    def __init__(self, autoescape=_DEFAULT_AUTOESCAPE, namespace=None,
                 whitespace=None):
        """构造一个模板加载器.

        :arg str autoescape: 在模板命名空间中的函数名, 例如 "xhtml_escape",
            或默认情况下为 ``None`` 来禁用自动转义.
        :arg dict namespace: 一个被加入默认模板命名空间中的字典或 ``None``.
        :arg str whitespace: 一个指定模板中whitespace默认行为的字符串;
            参见 `filter_whitespace` 查看可选项. 默认是 "single" 对于
            ".html" 和 ".js" 文件的结束, "all" 是为了其他文件.

        .. versionchanged:: 4.3
           添加 ``whitespace`` 参数.
        """
        self.autoescape = autoescape
        self.namespace = namespace or {}
        self.whitespace = whitespace
        self.templates = {}
        # self.lock protects self.templates.  It's a reentrant lock
        # because templates may load other templates via `include` or
        # `extends`.  Note that thanks to the GIL this code would be safe
        # even without the lock, but could lead to wasted work as multiple
        # threads tried to compile the same template simultaneously.
        self.lock = threading.RLock()

    def reset(self):
        """重置已编译模板的缓存."""
        with self.lock:
            self.templates = {}

    def resolve_path(self, name, parent_path=None):
        """转化一个可能相对的路径为绝对路径(内部使用)."""
        raise NotImplementedError()

    def load(self, name, parent_path=None):
        """加载一个模板."""
        name = self.resolve_path(name, parent_path=parent_path)
        with self.lock:
            if name not in self.templates:
                self.templates[name] = self._create_template(name)
            return self.templates[name]

    def _create_template(self, name):
        raise NotImplementedError()


class Loader(BaseLoader):
    """一个从单一根文件夹加载的模板加载器.
    """
    def __init__(self, root_directory, **kwargs):
        super(Loader, self).__init__(**kwargs)
        self.root = os.path.abspath(root_directory)

    def resolve_path(self, name, parent_path=None):
        if parent_path and not parent_path.startswith("<") and \
            not parent_path.startswith("/") and \
                not name.startswith("/"):
            current_path = os.path.join(self.root, parent_path)
            file_dir = os.path.dirname(os.path.abspath(current_path))
            relative_path = os.path.abspath(os.path.join(file_dir, name))
            if relative_path.startswith(self.root):
                name = relative_path[len(self.root) + 1:]
        return name

    def _create_template(self, name):
        path = os.path.join(self.root, name)
        with open(path, "rb") as f:
            template = Template(f.read(), name=name, loader=self)
            return template


class DictLoader(BaseLoader):
    """一个从字典加载的模板加载器."""
    def __init__(self, dict, **kwargs):
        super(DictLoader, self).__init__(**kwargs)
        self.dict = dict

    def resolve_path(self, name, parent_path=None):
        if parent_path and not parent_path.startswith("<") and \
            not parent_path.startswith("/") and \
                not name.startswith("/"):
            file_dir = posixpath.dirname(parent_path)
            name = posixpath.normpath(posixpath.join(file_dir, name))
        return name

    def _create_template(self, name):
        return Template(self.dict[name], name=name, loader=self)


class _Node(object):
    def each_child(self):
        return ()

    def generate(self, writer):
        raise NotImplementedError()

    def find_named_blocks(self, loader, named_blocks):
        for child in self.each_child():
            child.find_named_blocks(loader, named_blocks)


class _File(_Node):
    def __init__(self, template, body):
        self.template = template
        self.body = body
        self.line = 0

    def generate(self, writer):
        writer.write_line("def _tt_execute():", self.line)
        with writer.indent():
            writer.write_line("_tt_buffer = []", self.line)
            writer.write_line("_tt_append = _tt_buffer.append", self.line)
            self.body.generate(writer)
            writer.write_line("return _tt_utf8('').join(_tt_buffer)", self.line)

    def each_child(self):
        return (self.body,)


class _ChunkList(_Node):
    def __init__(self, chunks):
        self.chunks = chunks

    def generate(self, writer):
        for chunk in self.chunks:
            chunk.generate(writer)

    def each_child(self):
        return self.chunks


class _NamedBlock(_Node):
    def __init__(self, name, body, template, line):
        self.name = name
        self.body = body
        self.template = template
        self.line = line

    def each_child(self):
        return (self.body,)

    def generate(self, writer):
        block = writer.named_blocks[self.name]
        with writer.include(block.template, self.line):
            block.body.generate(writer)

    def find_named_blocks(self, loader, named_blocks):
        named_blocks[self.name] = self
        _Node.find_named_blocks(self, loader, named_blocks)


class _ExtendsBlock(_Node):
    def __init__(self, name):
        self.name = name


class _IncludeBlock(_Node):
    def __init__(self, name, reader, line):
        self.name = name
        self.template_name = reader.name
        self.line = line

    def find_named_blocks(self, loader, named_blocks):
        included = loader.load(self.name, self.template_name)
        included.file.find_named_blocks(loader, named_blocks)

    def generate(self, writer):
        included = writer.loader.load(self.name, self.template_name)
        with writer.include(included, self.line):
            included.file.body.generate(writer)


class _ApplyBlock(_Node):
    def __init__(self, method, line, body=None):
        self.method = method
        self.line = line
        self.body = body

    def each_child(self):
        return (self.body,)

    def generate(self, writer):
        method_name = "_tt_apply%d" % writer.apply_counter
        writer.apply_counter += 1
        writer.write_line("def %s():" % method_name, self.line)
        with writer.indent():
            writer.write_line("_tt_buffer = []", self.line)
            writer.write_line("_tt_append = _tt_buffer.append", self.line)
            self.body.generate(writer)
            writer.write_line("return _tt_utf8('').join(_tt_buffer)", self.line)
        writer.write_line("_tt_append(_tt_utf8(%s(%s())))" % (
            self.method, method_name), self.line)


class _ControlBlock(_Node):
    def __init__(self, statement, line, body=None):
        self.statement = statement
        self.line = line
        self.body = body

    def each_child(self):
        return (self.body,)

    def generate(self, writer):
        writer.write_line("%s:" % self.statement, self.line)
        with writer.indent():
            self.body.generate(writer)
            # Just in case the body was empty
            writer.write_line("pass", self.line)


class _IntermediateControlBlock(_Node):
    def __init__(self, statement, line):
        self.statement = statement
        self.line = line

    def generate(self, writer):
        # In case the previous block was empty
        writer.write_line("pass", self.line)
        writer.write_line("%s:" % self.statement, self.line, writer.indent_size() - 1)


class _Statement(_Node):
    def __init__(self, statement, line):
        self.statement = statement
        self.line = line

    def generate(self, writer):
        writer.write_line(self.statement, self.line)


class _Expression(_Node):
    def __init__(self, expression, line, raw=False):
        self.expression = expression
        self.line = line
        self.raw = raw

    def generate(self, writer):
        writer.write_line("_tt_tmp = %s" % self.expression, self.line)
        writer.write_line("if isinstance(_tt_tmp, _tt_string_types):"
                          " _tt_tmp = _tt_utf8(_tt_tmp)", self.line)
        writer.write_line("else: _tt_tmp = _tt_utf8(str(_tt_tmp))", self.line)
        if not self.raw and writer.current_template.autoescape is not None:
            # In python3 functions like xhtml_escape return unicode,
            # so we have to convert to utf8 again.
            writer.write_line("_tt_tmp = _tt_utf8(%s(_tt_tmp))" %
                              writer.current_template.autoescape, self.line)
        writer.write_line("_tt_append(_tt_tmp)", self.line)


class _Module(_Expression):
    def __init__(self, expression, line):
        super(_Module, self).__init__("_tt_modules." + expression, line,
                                      raw=True)


class _Text(_Node):
    def __init__(self, value, line, whitespace):
        self.value = value
        self.line = line
        self.whitespace = whitespace

    def generate(self, writer):
        value = self.value

        # Compress whitespace if requested, with a crude heuristic to avoid
        # altering preformatted whitespace.
        if "<pre>" not in value:
            value = filter_whitespace(self.whitespace, value)

        if value:
            writer.write_line('_tt_append(%r)' % escape.utf8(value), self.line)


class ParseError(Exception):
    """抛出模板的语法错误.

    ``ParseError`` 实例有 ``filename`` 和 ``lineno`` 属性指出错误所在位置.

    .. versionchanged:: 4.3
       添加 ``filename`` 和 ``lineno`` 属性.
    """
    def __init__(self, message, filename, lineno):
        self.message = message
        # The names "filename" and "lineno" are chosen for consistency
        # with python SyntaxError.
        self.filename = filename
        self.lineno = lineno

    def __str__(self):
        return '%s at %s:%d' % (self.message, self.filename, self.lineno)


class _CodeWriter(object):
    def __init__(self, file, named_blocks, loader, current_template):
        self.file = file
        self.named_blocks = named_blocks
        self.loader = loader
        self.current_template = current_template
        self.apply_counter = 0
        self.include_stack = []
        self._indent = 0

    def indent_size(self):
        return self._indent

    def indent(self):
        class Indenter(object):
            def __enter__(_):
                self._indent += 1
                return self

            def __exit__(_, *args):
                assert self._indent > 0
                self._indent -= 1

        return Indenter()

    def include(self, template, line):
        self.include_stack.append((self.current_template, line))
        self.current_template = template

        class IncludeTemplate(object):
            def __enter__(_):
                return self

            def __exit__(_, *args):
                self.current_template = self.include_stack.pop()[0]

        return IncludeTemplate()

    def write_line(self, line, line_number, indent=None):
        if indent is None:
            indent = self._indent
        line_comment = '  # %s:%d' % (self.current_template.name, line_number)
        if self.include_stack:
            ancestors = ["%s:%d" % (tmpl.name, lineno)
                         for (tmpl, lineno) in self.include_stack]
            line_comment += ' (via %s)' % ', '.join(reversed(ancestors))
        print("    " * indent + line + line_comment, file=self.file)


class _TemplateReader(object):
    def __init__(self, name, text, whitespace):
        self.name = name
        self.text = text
        self.whitespace = whitespace
        self.line = 1
        self.pos = 0

    def find(self, needle, start=0, end=None):
        assert start >= 0, start
        pos = self.pos
        start += pos
        if end is None:
            index = self.text.find(needle, start)
        else:
            end += pos
            assert end >= start
            index = self.text.find(needle, start, end)
        if index != -1:
            index -= pos
        return index

    def consume(self, count=None):
        if count is None:
            count = len(self.text) - self.pos
        newpos = self.pos + count
        self.line += self.text.count("\n", self.pos, newpos)
        s = self.text[self.pos:newpos]
        self.pos = newpos
        return s

    def remaining(self):
        return len(self.text) - self.pos

    def __len__(self):
        return self.remaining()

    def __getitem__(self, key):
        if type(key) is slice:
            size = len(self)
            start, stop, step = key.indices(size)
            if start is None:
                start = self.pos
            else:
                start += self.pos
            if stop is not None:
                stop += self.pos
            return self.text[slice(start, stop, step)]
        elif key < 0:
            return self.text[key]
        else:
            return self.text[self.pos + key]

    def __str__(self):
        return self.text[self.pos:]

    def raise_parse_error(self, msg):
        raise ParseError(msg, self.name, self.line)


def _format_code(code):
    lines = code.splitlines()
    format = "%%%dd  %%s\n" % len(repr(len(lines) + 1))
    return "".join([format % (i + 1, line) for (i, line) in enumerate(lines)])


def _parse(reader, template, in_block=None, in_loop=None):
    body = _ChunkList([])
    while True:
        # Find next template directive
        curly = 0
        while True:
            curly = reader.find("{", curly)
            if curly == -1 or curly + 1 == reader.remaining():
                # EOF
                if in_block:
                    reader.raise_parse_error(
                        "Missing {%% end %%} block for %s" % in_block)
                body.chunks.append(_Text(reader.consume(), reader.line,
                                         reader.whitespace))
                return body
            # If the first curly brace is not the start of a special token,
            # start searching from the character after it
            if reader[curly + 1] not in ("{", "%", "#"):
                curly += 1
                continue
            # When there are more than 2 curlies in a row, use the
            # innermost ones.  This is useful when generating languages
            # like latex where curlies are also meaningful
            if (curly + 2 < reader.remaining() and
                    reader[curly + 1] == '{' and reader[curly + 2] == '{'):
                curly += 1
                continue
            break

        # Append any text before the special token
        if curly > 0:
            cons = reader.consume(curly)
            body.chunks.append(_Text(cons, reader.line,
                                     reader.whitespace))

        start_brace = reader.consume(2)
        line = reader.line

        # Template directives may be escaped as "{{!" or "{%!".
        # In this case output the braces and consume the "!".
        # This is especially useful in conjunction with jquery templates,
        # which also use double braces.
        if reader.remaining() and reader[0] == "!":
            reader.consume(1)
            body.chunks.append(_Text(start_brace, line,
                                     reader.whitespace))
            continue

        # Comment
        if start_brace == "{#":
            end = reader.find("#}")
            if end == -1:
                reader.raise_parse_error("Missing end comment #}")
            contents = reader.consume(end).strip()
            reader.consume(2)
            continue

        # Expression
        if start_brace == "{{":
            end = reader.find("}}")
            if end == -1:
                reader.raise_parse_error("Missing end expression }}")
            contents = reader.consume(end).strip()
            reader.consume(2)
            if not contents:
                reader.raise_parse_error("Empty expression")
            body.chunks.append(_Expression(contents, line))
            continue

        # Block
        assert start_brace == "{%", start_brace
        end = reader.find("%}")
        if end == -1:
            reader.raise_parse_error("Missing end block %}")
        contents = reader.consume(end).strip()
        reader.consume(2)
        if not contents:
            reader.raise_parse_error("Empty block tag ({% %})")

        operator, space, suffix = contents.partition(" ")
        suffix = suffix.strip()

        # Intermediate ("else", "elif", etc) blocks
        intermediate_blocks = {
            "else": set(["if", "for", "while", "try"]),
            "elif": set(["if"]),
            "except": set(["try"]),
            "finally": set(["try"]),
        }
        allowed_parents = intermediate_blocks.get(operator)
        if allowed_parents is not None:
            if not in_block:
                reader.raise_parse_error("%s outside %s block" %
                                         (operator, allowed_parents))
            if in_block not in allowed_parents:
                reader.raise_parse_error(
                    "%s block cannot be attached to %s block" %
                    (operator, in_block))
            body.chunks.append(_IntermediateControlBlock(contents, line))
            continue

        # End tag
        elif operator == "end":
            if not in_block:
                reader.raise_parse_error("Extra {% end %} block")
            return body

        elif operator in ("extends", "include", "set", "import", "from",
                          "comment", "autoescape", "whitespace", "raw",
                          "module"):
            if operator == "comment":
                continue
            if operator == "extends":
                suffix = suffix.strip('"').strip("'")
                if not suffix:
                    reader.raise_parse_error("extends missing file path")
                block = _ExtendsBlock(suffix)
            elif operator in ("import", "from"):
                if not suffix:
                    reader.raise_parse_error("import missing statement")
                block = _Statement(contents, line)
            elif operator == "include":
                suffix = suffix.strip('"').strip("'")
                if not suffix:
                    reader.raise_parse_error("include missing file path")
                block = _IncludeBlock(suffix, reader, line)
            elif operator == "set":
                if not suffix:
                    reader.raise_parse_error("set missing statement")
                block = _Statement(suffix, line)
            elif operator == "autoescape":
                fn = suffix.strip()
                if fn == "None":
                    fn = None
                template.autoescape = fn
                continue
            elif operator == "whitespace":
                mode = suffix.strip()
                # Validate the selected mode
                filter_whitespace(mode, '')
                reader.whitespace = mode
                continue
            elif operator == "raw":
                block = _Expression(suffix, line, raw=True)
            elif operator == "module":
                block = _Module(suffix, line)
            body.chunks.append(block)
            continue

        elif operator in ("apply", "block", "try", "if", "for", "while"):
            # parse inner body recursively
            if operator in ("for", "while"):
                block_body = _parse(reader, template, operator, operator)
            elif operator == "apply":
                # apply creates a nested function so syntactically it's not
                # in the loop.
                block_body = _parse(reader, template, operator, None)
            else:
                block_body = _parse(reader, template, operator, in_loop)

            if operator == "apply":
                if not suffix:
                    reader.raise_parse_error("apply missing method name")
                block = _ApplyBlock(suffix, line, block_body)
            elif operator == "block":
                if not suffix:
                    reader.raise_parse_error("block missing name")
                block = _NamedBlock(suffix, block_body, template, line)
            else:
                block = _ControlBlock(contents, line, block_body)
            body.chunks.append(block)
            continue

        elif operator in ("break", "continue"):
            if not in_loop:
                reader.raise_parse_error("%s outside %s block" %
                                         (operator, set(["for", "while"])))
            body.chunks.append(_Statement(contents, line))
            continue

        else:
            reader.raise_parse_error("unknown operator: %r" % operator)
