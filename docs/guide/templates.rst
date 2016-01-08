模板和UI
================

.. testsetup::

   import tornado.web

Tornado 包含一个简单,快速并灵活的模板语言. 本节介绍了语言以及相
关的问题,比如国际化.

Tornado 也可以使用其他的Python模板语言, 虽然没有准备把这些系统整合
到 `.RequestHandler.render` 里面. 而是简单的将模板转成字符串并传递
给 `.RequestHandler.write`

配置模板
~~~~~~~~~~~~~~~~~~~~~

默认情况下, Tornado会在和当前 ``.py`` 文件相同的目录查找关联的模板
文件. 如果想把你的模板文件放在不同的目录中, 可以使用
``template_path`` `Application setting
<.Application.settings>` (或复写 `.RequestHandler.get_template_path`
如果你不同的处理函数有不同的模板路径).

为了从非文件系统位置加载模板, 实例化子类 `tornado.template.BaseLoader`
并为其在应用设置(application setting)中配置
``template_loader`` .

默认情况下编译出来的模板会被缓存; 为了关掉这个缓存也为了使(对目标的)
修改在重新加载后总是可见, 使用应用设置(application settings)中的
``compiled_template_cache=False`` 或 ``debug=True``.


模板语法
~~~~~~~~~~~~~~~

一个Tornado模板仅仅是用一些标记把Python控制序列和表达式嵌入
HTML(或者任意其他文本格式)的文件中::

    <html>
       <head>
          <title>{{ title }}</title>
       </head>
       <body>
         <ul>
           {% for item in items %}
             <li>{{ escape(item) }}</li>
           {% end %}
         </ul>
       </body>
     </html>

如果你把这个目标保存为"template.html"并且把它放在你Python文件的
相同目录下, 你可以使用下面的代码渲染它:

.. testcode::

    class MainHandler(tornado.web.RequestHandler):
        def get(self):
            items = ["Item 1", "Item 2", "Item 3"]
            self.render("template.html", title="My title", items=items)

.. testoutput::
   :hide:

Tornado模板支持 *控制语句(control statements)* 和 *表达式(expressions)*.
控制语句被包在 ``{%`` 和 ``%}`` 中间, e.g.,
``{% if len(items) > 2 %}``. 表达式被包在 ``{{`` 和
``}}`` 之间, e.g., ``{{ items[0] }}``.

控制语句或多或少都和Python语句类似. 我们支持 ``if``, ``for``,
``while``, 和 ``try``, 这些都必须使用 ``{% end %}`` 来标识结束. 我们也
支持 *模板继承(template inheritance)* 使用 ``extends`` 和 ``block``
标签声明, 这些内容的详细信息都可以在 `tornado.template` 中看到.

表达式可以是任意的Python表达式, 包括函数调用. 模板代码会在包含以下对象
和函数的命名空间中执行 (注意这个列表适用于使用 `.RequestHandler.render`
和 `~.RequestHandler.render_string` 渲染模板的情况. 如果你直接在
`.RequestHandler` 之外使用 `tornado.template` 模块, 下面这些很多都不存
在).

- ``escape``: `tornado.escape.xhtml_escape` 的别名
- ``xhtml_escape``: `tornado.escape.xhtml_escape` 的别名
- ``url_escape``: `tornado.escape.url_escape` 的别名
- ``json_encode``: `tornado.escape.json_encode` 的别名
- ``squeeze``: `tornado.escape.squeeze` 的别名
- ``linkify``: `tornado.escape.linkify` 的别名
- ``datetime``: Python `datetime` 模块
- ``handler``: 当前的 `.RequestHandler` 对象
- ``request``: `handler.request <.HTTPServerRequest>` 的别名
- ``current_user``: `handler.current_user
  <.RequestHandler.current_user>` 的别名
- ``locale``: `handler.locale <.Locale>` 的别名
- ``_``: `handler.locale.translate <.Locale.translate>` 的别名
- ``static_url``: `handler.static_url <.RequestHandler.static_url>` 的别名
- ``xsrf_form_html``: `handler.xsrf_form_html
  <.RequestHandler.xsrf_form_html>` 的别名
- ``reverse_url``: `.Application.reverse_url` 的别名
- 所有从 ``ui_methods`` 和 ``ui_modules``
  ``Application`` 设置的条目
- 任何传递给 `~.RequestHandler.render` 或
  `~.RequestHandler.render_string` 的关键字参数

当你正在构建一个真正的应用, 你可能想要使用Tornado模板的所有特性,
尤其是目标继承. 阅读所有关于这些特性的介绍在 `tornado.template`
部分 (一些特性, 包括 ``UIModules`` 是在 `tornado.web` 模块中实现的)

在引擎下, Tornado模板被直接转换为Python. 包含在你模板中的表达式会
逐字的复制到一个代表你模板的Python函数中. 我们不会试图阻止模板语言
中的任何东西; 我们明确的创造一个高度灵活的模板系统, 而不是有严格限制
的模板系统. 因此, 如果你在模板表达式中随意填充(代码), 当你执行它的时
候你也会得到各种随机错误.

所有模板输出默认都会使用 `tornado.escape.xhtml_escape` 函数转义.
这个行为可以通过传递 ``autoescape=None`` 给 `.Application` 或者
`.tornado.template.Loader` 构造器来全局改变, 对于一个模板文件可以使
用 ``{% autoescape None %}`` 指令, 对于一个单一表达式可以使用
 ``{% raw ...%}`` 来代替 ``{{ ... }}`` . 此外, 在每个地方一个可选的
 转义函数名可以被用来代替 ``None``.

注意, 虽然Tornado的自动转义在预防XSS漏洞上是有帮助的, 但是它并不能
胜任所有的情况. 在某一位置出现的表达式, 例如Javascript 或 CSS, 可能需
要另外的转义. 此外, 要么是必须注意总是在可能包含不可信内容的HTML中
使用双引号和 `.xhtml_escape` , 要么必须在属性中使用单独的转义函数
(参见 e.g. http://wonko.com/post/html-escaping)

国际化
~~~~~~~~~~~~~~~~~~~~

The locale of the current user (whether they are logged in or not) is
always available as ``self.locale`` in the request handler and as
``locale`` in templates. The name of the locale (e.g., ``en_US``) is
available as ``locale.name``, and you can translate strings with the
`.Locale.translate` method. Templates also have the global function
call ``_()`` available for string translation. The translate function
has two forms::

    _("Translate this string")

which translates the string directly based on the current locale, and::

    _("A person liked this", "%(num)d people liked this",
      len(people)) % {"num": len(people)}

which translates a string that can be singular or plural based on the
value of the third argument. In the example above, a translation of the
first string will be returned if ``len(people)`` is ``1``, or a
translation of the second string will be returned otherwise.

The most common pattern for translations is to use Python named
placeholders for variables (the ``%(num)d`` in the example above) since
placeholders can move around on translation.

Here is a properly internationalized template::

    <html>
       <head>
          <title>FriendFeed - {{ _("Sign in") }}</title>
       </head>
       <body>
         <form action="{{ request.path }}" method="post">
           <div>{{ _("Username") }} <input type="text" name="username"/></div>
           <div>{{ _("Password") }} <input type="password" name="password"/></div>
           <div><input type="submit" value="{{ _("Sign in") }}"/></div>
           {% module xsrf_form_html() %}
         </form>
       </body>
     </html>

By default, we detect the user's locale using the ``Accept-Language``
header sent by the user's browser. We choose ``en_US`` if we can't find
an appropriate ``Accept-Language`` value. If you let user's set their
locale as a preference, you can override this default locale selection
by overriding `.RequestHandler.get_user_locale`:

.. testcode::

    class BaseHandler(tornado.web.RequestHandler):
        def get_current_user(self):
            user_id = self.get_secure_cookie("user")
            if not user_id: return None
            return self.backend.get_user_by_id(user_id)

        def get_user_locale(self):
            if "locale" not in self.current_user.prefs:
                # Use the Accept-Language header
                return None
            return self.current_user.prefs["locale"]

.. testoutput::
   :hide:

If ``get_user_locale`` returns ``None``, we fall back on the
``Accept-Language`` header.

The `tornado.locale` module supports loading translations in two
formats: the ``.mo`` format used by `gettext` and related tools, and a
simple ``.csv`` format.  An application will generally call either
`tornado.locale.load_translations` or
`tornado.locale.load_gettext_translations` once at startup; see those
methods for more details on the supported formats..

You can get the list of supported locales in your application with
`tornado.locale.get_supported_locales()`. The user's locale is chosen
to be the closest match based on the supported locales. For example, if
the user's locale is ``es_GT``, and the ``es`` locale is supported,
``self.locale`` will be ``es`` for that request. We fall back on
``en_US`` if no close match can be found.

.. _ui-modules:

UI modules
~~~~~~~~~~

Tornado supports *UI modules* to make it easy to support standard,
reusable UI widgets across your application. UI modules are like special
function calls to render components of your page, and they can come
packaged with their own CSS and JavaScript.

For example, if you are implementing a blog, and you want to have blog
entries appear on both the blog home page and on each blog entry page,
you can make an ``Entry`` module to render them on both pages. First,
create a Python module for your UI modules, e.g., ``uimodules.py``::

    class Entry(tornado.web.UIModule):
        def render(self, entry, show_comments=False):
            return self.render_string(
                "module-entry.html", entry=entry, show_comments=show_comments)

Tell Tornado to use ``uimodules.py`` using the ``ui_modules`` setting in
your application::

    from . import uimodules

    class HomeHandler(tornado.web.RequestHandler):
        def get(self):
            entries = self.db.query("SELECT * FROM entries ORDER BY date DESC")
            self.render("home.html", entries=entries)

    class EntryHandler(tornado.web.RequestHandler):
        def get(self, entry_id):
            entry = self.db.get("SELECT * FROM entries WHERE id = %s", entry_id)
            if not entry: raise tornado.web.HTTPError(404)
            self.render("entry.html", entry=entry)

    settings = {
        "ui_modules": uimodules,
    }
    application = tornado.web.Application([
        (r"/", HomeHandler),
        (r"/entry/([0-9]+)", EntryHandler),
    ], **settings)

Within a template, you can call a module with the ``{% module %}``
statement.  For example, you could call the ``Entry`` module from both
``home.html``::

    {% for entry in entries %}
      {% module Entry(entry) %}
    {% end %}

and ``entry.html``::

    {% module Entry(entry, show_comments=True) %}

Modules can include custom CSS and JavaScript functions by overriding
the ``embedded_css``, ``embedded_javascript``, ``javascript_files``, or
``css_files`` methods::

    class Entry(tornado.web.UIModule):
        def embedded_css(self):
            return ".entry { margin-bottom: 1em; }"

        def render(self, entry, show_comments=False):
            return self.render_string(
                "module-entry.html", show_comments=show_comments)

Module CSS and JavaScript will be included once no matter how many times
a module is used on a page. CSS is always included in the ``<head>`` of
the page, and JavaScript is always included just before the ``</body>``
tag at the end of the page.

When additional Python code is not required, a template file itself may
be used as a module. For example, the preceding example could be
rewritten to put the following in ``module-entry.html``::

    {{ set_resources(embedded_css=".entry { margin-bottom: 1em; }") }}
    <!-- more template html... -->

This revised template module would be invoked with::

    {% module Template("module-entry.html", show_comments=True) %}

The ``set_resources`` function is only available in templates invoked
via ``{% module Template(...) %}``. Unlike the ``{% include ... %}``
directive, template modules have a distinct namespace from their
containing template - they can only see the global template namespace
and their own keyword arguments.
