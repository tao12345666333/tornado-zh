.. currentmodule:: tornado.web

.. testsetup::

   import tornado.web

Tornado web应用的结构
======================================

通常一个Tornado web应用包括一个或者多个 `.RequestHandler` 子类,
一个可以将收到的请求路由到对应handler的 `.Application` 对象,和
一个启动服务的 ``main()`` 函数.

一个最小的"hello world"例子就像下面这样:

.. testcode::

    import tornado.ioloop
    import tornado.web

    class MainHandler(tornado.web.RequestHandler):
        def get(self):
            self.write("Hello, world")

    def make_app():
        return tornado.web.Application([
            (r"/", MainHandler),
        ])

    if __name__ == "__main__":
        app = make_app()
        app.listen(8888)
        tornado.ioloop.IOLoop.current().start()

.. testoutput::
   :hide:

``Application`` 对象
~~~~~~~~~~~~~~~~~~~~~~~~~~

`.Application` 对象是负责全局配置的, 包括映射请求转发给处理程序的路由
表.

路由表是 `.URLSpec` 对象(或元组)的列表, 其中每个都包含(至少)一个正则
表达式和一个处理类. 顺序问题; 第一个匹配的规则会被使用. 如果正则表达
式包含捕获组, 这些组会被作为 *路径参数* 传递给处理函数的HTTP方法.
如果一个字典作为 `.URLSpec` 的第三个参数被传递, 它会作为 *初始参数*
传递给 `.RequestHandler.initialize`.  最后 `.URLSpec` 可能有一个名字
, 这将允许它被 `.RequestHandler.reverse_url` 使用.

例如, 在这个片段中根URL ``/`` 映射到了
``MainHandler`` , 像 ``/story/`` 后跟着一个数字这种形式的URL被映射到了
``StoryHandler``.  这个数字被传递(作为字符串)给
``StoryHandler.get``.

::

    class MainHandler(RequestHandler):
        def get(self):
            self.write('<a href="%s">link to story 1</a>' %
                       self.reverse_url("story", "1"))

    class StoryHandler(RequestHandler):
        def initialize(self, db):
            self.db = db

        def get(self, story_id):
            self.write("this is story %s" % story_id)

    app = Application([
        url(r"/", MainHandler),
        url(r"/story/([0-9]+)", StoryHandler, dict(db=db), name="story")
        ])

`.Application` 构造函数有很多关键字参数可以用于自定义应用程序的行为
和使用某些特性(或者功能); 完整列表请查看 `.Application.settings` .

 ``RequestHandler`` 子类
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Tornado web 应用程序的大部分工作是在 `.RequestHandler` 子类下完成的.
处理子类的主入口点是一个命名为处理HTTP方法的函数: ``get()``,
``post()``, 等等. 每个处理程序可以定义一个或者多个这种方法来处理不同
的HTTP动作. 如上所述, 这些方法将被匹配路由规则的捕获组对应的参数调用.

在处理程序中, 调用方法如 `.RequestHandler.render` 或者
`.RequestHandler.write` 产生一个响应.  ``render()`` 通过名字加载一个
`.Template` 并使用给定的参数渲染它. ``write()`` 被用于非模板基础的输
出; 它接受字符串, 字节, 和字典(字典会被编码成JSON).

在 `.RequestHandler` 中的很多方法的设计是为了在子类中复写和在整个应用
中使用. 常用的方法是定义一个 ``BaseHandler`` 类, 复写一些方法例如
`~.RequestHandler.write_error` 和 `~.RequestHandler.get_current_user`
然后子类继承使用你自己的 ``BaseHandler`` 而不是 `.RequestHandler`
在你所有具体的处理程序中.

处理输入请求
~~~~~~~~~~~~~~~~~~~~~~

处理请求的程序(request handler)可以使用 ``self.request`` 访问代表当
前请求的对象. 通过
`~tornado.httputil.HTTPServerRequest` 的类定义查看完整的属性列表.

使用HTML表单格式请求的数据会被解析并且可以在一些方法中使用, 例如
`~.RequestHandler.get_query_argument` 和
`~.RequestHandler.get_body_argument`.

.. testcode::

    class MyFormHandler(tornado.web.RequestHandler):
        def get(self):
            self.write('<html><body><form action="/myform" method="POST">'
                       '<input type="text" name="message">'
                       '<input type="submit" value="Submit">'
                       '</form></body></html>')

        def post(self):
            self.set_header("Content-Type", "text/plain")
            self.write("You wrote " + self.get_body_argument("message"))

.. testoutput::
   :hide:

由于HTLM表单编码不确定一个标签的参数是单一值还是一个列表,
`.RequestHandler` 有明确的方法来允许应用程序表明是否它期望接收一个列表.
对于列表, 使用
`~.RequestHandler.get_query_arguments` 和
`~.RequestHandler.get_body_arguments` 而不是它们的单数形式.

通过一个表单上传的文件可以使用 ``self.request.files``,
它遍历名字(HTML 标签 ``<input type="file">`` 的name)到一个文件列表.
每个文件都是一个字典的形式
``{"filename":..., "content_type":..., "body":...}``.  ``files``
对象是当前唯一的如果文件上传是通过一个表单包装
(i.e. a ``multipart/form-data`` Content-Type); 如果没用这种格式,
原生上传的数据可以调用 ``self.request.body`` 使用.
默认上传的文件是完全缓存在内存中的; 如果你需要处理占用内存太大的文件
可以看看 `.stream_request_body` 类装饰器.

由于HTML表单编码格式的怪异 (e.g. 在单数和复数参数的含糊不清), Tornado
不会试图统一表单参数和其他输入类型的参数. 特别是, 我们不解析JSON请求体.
应用程序希望使用JSON代替表单编码可以复写 `~.RequestHandler.prepare`
来解析它们的请求::

    def prepare(self):
        if self.request.headers["Content-Type"].startswith("application/json"):
            self.json_args = json.loads(self.request.body)
        else:
            self.json_args = None

复写RequestHandler的方法
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

除了 ``get()``/``post()``/等, 在 `.RequestHandler` 中的某些其他方法
被设计成了在必要的时候让子类重写. 在每个请求中, 会发生下面的调用序
列:

1. 在每次请求时生成一个新的 `.RequestHandler` 对象
2. `~.RequestHandler.initialize()` 被 `.Application` 配置中的初始化
   参数被调用. ``initialize``  通常应该只保存成员变量传递的参数;
   它不可能产生任何输出或者调用方法, 例如
   `~.RequestHandler.send_error`.
3. `~.RequestHandler.prepare()` 被调用. 这在你所有处理子类共享的基
   类中是最有用的, 无论是使用哪种HTTP方法, ``prepare`` 都会被调用.
   ``prepare`` 可能会产生输出; 如果它调用 `~.RequestHandler.finish`
   (或者 ``redirect``, 等), 处理会在这里结束.
4. 其中一种HTTP方法被调用: ``get()``, ``post()``, ``put()``,
   等. 如果URL的正则表达式包含捕获组, 它们会被作为参数传递给这个方
   法.
5. 当请求结束, `~.RequestHandler.on_finish()` 方法被调用. 对于同步
   处理程序会在 ``get()`` (等)后立即返回; 对于异步处理程序,会在调用
   `~.RequestHandler.finish()` 后返回.

所有这样设计被用来复写的方法被记录在了 `.RequestHandler` 的文档中.
其中最常用的一些被复写的方法包括:

- `~.RequestHandler.write_error` -
  输出对错误页面使用的HTML.
- `~.RequestHandler.on_connection_close` - 当客户端断开时被调用;
  应用程序可以检测这种情况,并中断后续处理. 注意这不能保证一个关闭
  的连接及时被发现.
- `~.RequestHandler.get_current_user` - 参考 :ref:`user-authentication`
- `~.RequestHandler.get_user_locale` - 返回 `.Locale` 对象给当前
  用户使用
- `~.RequestHandler.set_default_headers` - 可以被用来设置额外的响应
  头(例如自定义的 ``Server`` 头)

Error Handling
~~~~~~~~~~~~~~

If a handler raises an exception, Tornado will call
`.RequestHandler.write_error` to generate an error page.
`tornado.web.HTTPError` can be used to generate a specified status
code; all other exceptions return a 500 status.

The default error page includes a stack trace in debug mode and a
one-line description of the error (e.g. "500: Internal Server Error")
otherwise.  To produce a custom error page, override
`RequestHandler.write_error` (probably in a base class shared by all
your handlers).  This method may produce output normally via
methods such as `~RequestHandler.write` and `~RequestHandler.render`.
If the error was caused by an exception, an ``exc_info`` triple will
be passed as a keyword argument (note that this exception is not
guaranteed to be the current exception in `sys.exc_info`, so
``write_error`` must use e.g.  `traceback.format_exception` instead of
`traceback.format_exc`).

It is also possible to generate an error page from regular handler
methods instead of ``write_error`` by calling
`~.RequestHandler.set_status`, writing a response, and returning.
The special exception `tornado.web.Finish` may be raised to terminate
the handler without calling ``write_error`` in situations where simply
returning is not convenient.

For 404 errors, use the ``default_handler_class`` `Application setting
<.Application.settings>`.  This handler should override
`~.RequestHandler.prepare` instead of a more specific method like
``get()`` so it works with any HTTP method.  It should produce its
error page as described above: either by raising a ``HTTPError(404)``
and overriding ``write_error``, or calling ``self.set_status(404)``
and producing the response directly in ``prepare()``.

Redirection
~~~~~~~~~~~

There are two main ways you can redirect requests in Tornado:
`.RequestHandler.redirect` and with the `.RedirectHandler`.

You can use ``self.redirect()`` within a `.RequestHandler` method to
redirect users elsewhere. There is also an optional parameter
``permanent`` which you can use to indicate that the redirection is
considered permanent.  The default value of ``permanent`` is
``False``, which generates a ``302 Found`` HTTP response code and is
appropriate for things like redirecting users after successful
``POST`` requests.  If ``permanent`` is true, the ``301 Moved
Permanently`` HTTP response code is used, which is useful for
e.g. redirecting to a canonical URL for a page in an SEO-friendly
manner.

`.RedirectHandler` lets you configure redirects directly in your
`.Application` routing table.  For example, to configure a single
static redirect::

    app = tornado.web.Application([
        url(r"/app", tornado.web.RedirectHandler,
            dict(url="http://itunes.apple.com/my-app-id")),
        ])

`.RedirectHandler` also supports regular expression substitutions.
The following rule redirects all requests beginning with ``/pictures/``
to the prefix ``/photos/`` instead::

    app = tornado.web.Application([
        url(r"/photos/(.*)", MyPhotoHandler),
        url(r"/pictures/(.*)", tornado.web.RedirectHandler,
            dict(url=r"/photos/\1")),
        ])

Unlike `.RequestHandler.redirect`, `.RedirectHandler` uses permanent
redirects by default.  This is because the routing table does not change
at runtime and is presumed to be permanent, while redirects found in
handlers are likely to be the result of other logic that may change.
To send a temporary redirect with a `.RedirectHandler`, add
``permanent=False`` to the `.RedirectHandler` initialization arguments.

Asynchronous handlers
~~~~~~~~~~~~~~~~~~~~~

Tornado handlers are synchronous by default: when the
``get()``/``post()`` method returns, the request is considered
finished and the response is sent.  Since all other requests are
blocked while one handler is running, any long-running handler should
be made asynchronous so it can call its slow operations in a
non-blocking way.  This topic is covered in more detail in
:doc:`async`; this section is about the particulars of
asynchronous techniques in `.RequestHandler` subclasses.

The simplest way to make a handler asynchronous is to use the
`.coroutine` decorator.  This allows you to perform non-blocking I/O
with the ``yield`` keyword, and no response will be sent until the
coroutine has returned.  See :doc:`coroutines` for more details.

In some cases, coroutines may be less convenient than a
callback-oriented style, in which case the `.tornado.web.asynchronous`
decorator can be used instead.  When this decorator is used the response
is not automatically sent; instead the request will be kept open until
some callback calls `.RequestHandler.finish`.  It is up to the application
to ensure that this method is called, or else the user's browser will
simply hang.

Here is an example that makes a call to the FriendFeed API using
Tornado's built-in `.AsyncHTTPClient`:

.. testcode::

    class MainHandler(tornado.web.RequestHandler):
        @tornado.web.asynchronous
        def get(self):
            http = tornado.httpclient.AsyncHTTPClient()
            http.fetch("http://friendfeed-api.com/v2/feed/bret",
                       callback=self.on_response)

        def on_response(self, response):
            if response.error: raise tornado.web.HTTPError(500)
            json = tornado.escape.json_decode(response.body)
            self.write("Fetched " + str(len(json["entries"])) + " entries "
                       "from the FriendFeed API")
            self.finish()

.. testoutput::
   :hide:

When ``get()`` returns, the request has not finished. When the HTTP
client eventually calls ``on_response()``, the request is still open,
and the response is finally flushed to the client with the call to
``self.finish()``.

For comparison, here is the same example using a coroutine:

.. testcode::

    class MainHandler(tornado.web.RequestHandler):
        @tornado.gen.coroutine
        def get(self):
            http = tornado.httpclient.AsyncHTTPClient()
            response = yield http.fetch("http://friendfeed-api.com/v2/feed/bret")
            json = tornado.escape.json_decode(response.body)
            self.write("Fetched " + str(len(json["entries"])) + " entries "
                       "from the FriendFeed API")

.. testoutput::
   :hide:

For a more advanced asynchronous example, take a look at the `chat
example application
<https://github.com/tornadoweb/tornado/tree/stable/demos/chat>`_, which
implements an AJAX chat room using `long polling
<http://en.wikipedia.org/wiki/Push_technology#Long_polling>`_.  Users
of long polling may want to override ``on_connection_close()`` to
clean up after the client closes the connection (but see that method's
docstring for caveats).
