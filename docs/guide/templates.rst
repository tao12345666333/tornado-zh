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
``{% raw ...%}`` 来代替 ``{{ ... }}``. 此外, 在每个地方一个可选的
转义函数名可以被用来代替 ``None``.

注意, 虽然Tornado的自动转义在预防XSS漏洞上是有帮助的, 但是它并不能
胜任所有的情况. 在某一位置出现的表达式, 例如Javascript 或 CSS, 可能需
要另外的转义. 此外, 要么是必须注意总是在可能包含不可信内容的HTML中
使用双引号和 `.xhtml_escape` , 要么必须在属性中使用单独的转义函数
(参见 e.g. http://wonko.com/post/html-escaping)

国际化
~~~~~~~~~~~~~~~~~~~~

当前用户的区域设置(无论他们是否登录)总是可以通过在请求处理程序中
使用 ``self.locale`` 或者在模板中使用 ``locale`` 进行访问. 区域的名字
(e.g., ``en_US``) 可以通过 ``locale.name`` 获得, 你可以翻译字符串
通过 `.Locale.translate` 方法. 模板也有一个叫做 ``_()`` 全局函数
用来进行字符串翻译. 翻译函数有两种形式::

    _("Translate this string")

是直接根据当前的区域设置进行翻译, 还有::

    _("A person liked this", "%(num)d people liked this",
      len(people)) % {"num": len(people)}

是可以根据第三个参数的值来翻译字符串单复数的. 在上面的例子中,
如果 ``len(people)`` 是 ``1``, 那么第一句翻译将被返回, 其他情况
第二句的翻译将会返回.

翻译最通用的模式四使用Python命名占位符变量(上面例子中的
``%(num)d`` ) 因为占位符可以在翻译时变化.

这是一个正确的国际化模板::

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

默认情况下, 我们通过用户的浏览器发送的 ``Accept-Language`` 头来发现
用户的区域设置. 如果我们没有发现恰当的 ``Accept-Language`` 值, 我们
会使用 ``en_US`` . 如果你让用户进行自己偏爱的区域设置, 你可以通过复
写 `.RequestHandler.get_user_locale` 来覆盖默认选择的区域:

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

如果 ``get_user_locale`` 返回 ``None``, 那我们(继续)依靠
``Accept-Language`` 头(进行判断).

`tornado.locale` 模块支持两种形式加载翻译: 一种是用 `gettext`
和相关的工具的 ``.mo`` 格式, 还有一种是简单的 ``.csv`` 格式.
应用程序在启动时通常会调用一次 `tornado.locale.load_translations`
或者 `tornado.locale.load_gettext_translations` 其中之一; 查看
这些方法来获取更多有关支持格式的详细信息..

你可以使用 `tornado.locale.get_supported_locales()` 得到你的应用
所支持的区域(设置)列表. 用户的区域是从被支持的区域中选择距离最近
的匹配得到的. 例如, 如果用户的区域是 ``es_GT``, 同时 ``es`` 区域
是被支持的, 请求中的 ``self.locale`` 将会设置为 ``es`` . 如果找不
到距离最近的匹配项, 我们将会使用 ``en_US`` .

.. _ui-modules:

UI 模块
~~~~~~~~~~

Tornado支持 *UI modules* 使它易于支持标准, 在你的应用程序中复用
UI组件. UI模块像是特殊的函数调用来渲染你的页面上的组件并且它们可
以包装自己的CSS和JavaScript.

例如, 如果你实现一个博客, 并且你想要有博客入口出现在首页和每篇博
客页, 你可以实现一个 ``Entry`` 模块来在这些页面上渲染它们. 首先,
为你的UI模块新建一个Python模块, e.g., ``uimodules.py``::

    class Entry(tornado.web.UIModule):
        def render(self, entry, show_comments=False):
            return self.render_string(
                "module-entry.html", entry=entry, show_comments=show_comments)

在你的应用设置中, 使用 ``ui_modules`` 配置, 告诉Tornado使用
``uimodules.py`` ::

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

在一个模板中, 你可以使用 ``{% module %}`` 语法调用一个模块. 例如,
你可以调用 ``Entry`` 模块从 ``home.html``::

    {% for entry in entries %}
      {% module Entry(entry) %}
    {% end %}

和 ``entry.html``::

    {% module Entry(entry, show_comments=True) %}

模块可以包含自定义的CSS和JavaScript函数, 通过复写 ``embedded_css``,
``embedded_javascript``, ``javascript_files``, 或 ``css_files``
方法::

    class Entry(tornado.web.UIModule):
        def embedded_css(self):
            return ".entry { margin-bottom: 1em; }"

        def render(self, entry, show_comments=False):
            return self.render_string(
                "module-entry.html", show_comments=show_comments)

模块CSS和JavaScript将被加载(或包含)一次, 无论模块在一个页面上被使
用多少次. CSS总是包含在页面的 ``<head>`` 标签中, JavaScript 总是被
包含在页面最底部的 ``</body>`` 标签之前.

当不需要额外的Python代码时, 一个模板文件本身可以作为一个模块. 例如,
先前的例子可以重写到下面的 ``module-entry.html``::

    {{ set_resources(embedded_css=".entry { margin-bottom: 1em; }") }}
    <!-- more template html... -->

这个被修改过的模块模块可以被引用::

    {% module Template("module-entry.html", show_comments=True) %}

``set_resources`` 函数只能在模板中通过 ``{% module Template(...) %}``
才可用. 不像 ``{% include ... %}`` 指令, 模板模块有一个明确的命名空间
它们的包含模板-它们只能看到全局模板命名空间和它们自己的关键字参数.
