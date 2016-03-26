``tornado.web`` --- ``RequestHandler`` 和 ``Application`` 类
==================================================================

.. testsetup::

   from tornado.web import *

.. automodule:: tornado.web

   Request handlers
   ----------------
   .. autoclass:: RequestHandler

   Entry points
   ^^^^^^^^^^^^

   .. automethod:: RequestHandler.initialize
   .. automethod:: RequestHandler.prepare
   .. automethod:: RequestHandler.on_finish

   .. _verbs:

   执行后面任何的方法 (统称为HTTP 动词(verb) 方法) 来处理相应的HTTP方法.
   这些方法可以通过使用下面的装饰器: `.gen.coroutine`, `.return_future`,
   或 `asynchronous` 变成异步.

   为了支持不再列表中的方法, 可以复写类变量 ``SUPPORTED_METHODS``::

     class WebDAVHandler(RequestHandler):
         SUPPORTED_METHODS = RequestHandler.SUPPORTED_METHODS + ('PROPFIND',)

         def propfind(self):
             pass

   .. automethod:: RequestHandler.get
   .. automethod:: RequestHandler.head
   .. automethod:: RequestHandler.post
   .. automethod:: RequestHandler.delete
   .. automethod:: RequestHandler.patch
   .. automethod:: RequestHandler.put
   .. automethod:: RequestHandler.options

   Input
   ^^^^^

   .. automethod:: RequestHandler.get_argument
   .. automethod:: RequestHandler.get_arguments
   .. automethod:: RequestHandler.get_query_argument
   .. automethod:: RequestHandler.get_query_arguments
   .. automethod:: RequestHandler.get_body_argument
   .. automethod:: RequestHandler.get_body_arguments
   .. automethod:: RequestHandler.decode_argument
   .. attribute:: RequestHandler.request

      `tornado.httputil.HTTPServerRequest` 对象包含附加的
      请求参数包括e.g. 头部和body数据.

   .. attribute:: RequestHandler.path_args
   .. attribute:: RequestHandler.path_kwargs

      ``path_args`` 和 ``path_kwargs`` 属性包含传递给
      :ref:`HTTP verb methods <verbs>` 的位置和关键字参数.
      这些属性被设置, 在这些方法被调用之前, 所以这些值
      在 `prepare` 之间是可用的.

   Output
   ^^^^^^

   .. automethod:: RequestHandler.set_status
   .. automethod:: RequestHandler.set_header
   .. automethod:: RequestHandler.add_header
   .. automethod:: RequestHandler.clear_header
   .. automethod:: RequestHandler.set_default_headers
   .. automethod:: RequestHandler.write
   .. automethod:: RequestHandler.flush
   .. automethod:: RequestHandler.finish
   .. automethod:: RequestHandler.render
   .. automethod:: RequestHandler.render_string
   .. automethod:: RequestHandler.get_template_namespace
   .. automethod:: RequestHandler.redirect
   .. automethod:: RequestHandler.send_error
   .. automethod:: RequestHandler.write_error
   .. automethod:: RequestHandler.clear
   .. automethod:: RequestHandler.data_received


   Cookies
   ^^^^^^^

   .. autoattribute:: RequestHandler.cookies
   .. automethod:: RequestHandler.get_cookie
   .. automethod:: RequestHandler.set_cookie
   .. automethod:: RequestHandler.clear_cookie
   .. automethod:: RequestHandler.clear_all_cookies
   .. automethod:: RequestHandler.get_secure_cookie
   .. automethod:: RequestHandler.get_secure_cookie_key_version
   .. automethod:: RequestHandler.set_secure_cookie
   .. automethod:: RequestHandler.create_signed_value
   .. autodata:: MIN_SUPPORTED_SIGNED_VALUE_VERSION
   .. autodata:: MAX_SUPPORTED_SIGNED_VALUE_VERSION
   .. autodata:: DEFAULT_SIGNED_VALUE_VERSION
   .. autodata:: DEFAULT_SIGNED_VALUE_MIN_VERSION

   Other
   ^^^^^

   .. attribute:: RequestHandler.application

      为请求提供服务的 `Application` 对象

   .. automethod:: RequestHandler.check_etag_header
   .. automethod:: RequestHandler.check_xsrf_cookie
   .. automethod:: RequestHandler.compute_etag
   .. automethod:: RequestHandler.create_template_loader
   .. autoattribute:: RequestHandler.current_user
   .. automethod:: RequestHandler.get_browser_locale
   .. automethod:: RequestHandler.get_current_user
   .. automethod:: RequestHandler.get_login_url
   .. automethod:: RequestHandler.get_status
   .. automethod:: RequestHandler.get_template_path
   .. automethod:: RequestHandler.get_user_locale
   .. autoattribute:: RequestHandler.locale
   .. automethod:: RequestHandler.log_exception
   .. automethod:: RequestHandler.on_connection_close
   .. automethod:: RequestHandler.require_setting
   .. automethod:: RequestHandler.reverse_url
   .. automethod:: RequestHandler.set_etag_header
   .. autoattribute:: RequestHandler.settings
   .. automethod:: RequestHandler.static_url
   .. automethod:: RequestHandler.xsrf_form_html
   .. autoattribute:: RequestHandler.xsrf_token



   应用程序配置
   -----------------------------
   .. autoclass:: Application
      :members:

      .. attribute:: settings

         传递给构造器的附加关键字参数保存在 `settings` 字典中,
         并经常在文档中被称为"application settings". Settings被用于
         自定义Tornado的很多方面(虽然在一些情况下, 更丰富的定制可能
         是通过在 `RequestHandler` 的子类中复写方法). 一些应用程序
         也喜欢使用 `settings` 字典作为使一些处理程序可以使用应用
         程序的特定设置的方法, 而无需使用全局变量. Tornado中使用的
         Setting描述如下.

         一般设置(General settings):

         * ``autoreload``: 如果为 ``True``, 服务进程将会在任意资源文件
           改变的时候重启, 正如 :ref:`debug-mode` 中描述的那样.
           这个选项是Tornado 3.2中新增的; 在这之前这个功能是由
           ``debug`` 设置控制的.
         * ``debug``: 一些调试模式设置的速记, 正如 :ref:`debug-mode`
           中描述的那样. ``debug=True`` 设置等同于 ``autoreload=True``,
           ``compiled_template_cache=False``,
           ``static_hash_cache=False``, ``serve_traceback=True``.
         * ``default_handler_class`` 和 ``default_handler_args``:
           如果没有发现其他匹配则会使用这个处理程序; 使用这个来实现自
           定义404页面(Tornado 3.2新增).
         * ``compress_response``: 如果为 ``True``, 以文本格式的响应
           将被自动压缩. Tornado 4.0新增.
         * ``gzip``: 不推荐使用的 ``compress_response`` 别名自从
           Tornado 4.0.
         * ``log_function``: 这个函数将在每次请求结束的时候调用以记录
           结果(有一次参数, 该 `RequestHandler` 对象). 默认实现是写入
           `logging` 模块的根logger. 也可以通过复写
           `Application.log_request` 自定义.
         * ``serve_traceback``: 如果为true, 默认的错误页将包含错误信息
           的回溯. 这个选项是在Tornado 3.2中新增的; 在此之前这个功能
           由 ``debug`` 设置控制.
         * ``ui_modules`` 和 ``ui_methods``: 可以被设置为 `UIModule`
           或UI methods 的映射提供给模板. 可以被设置为一个模块, 字典,
           或一个模块的列表和/或字典. 参见 :ref:`ui-modules` 了解更多
           细节.

         认证和安全设置(Authentication and security settings):

         * ``cookie_secret``: 被 `RequestHandler.get_secure_cookie`
           使用, `.set_secure_cookie` 用来给cookies签名.
         * ``key_version``: 被requestHandler `.set_secure_cookie`
           使用一个特殊的key给cookie签名当 ``cookie_secret`` 是一个
           key字典.
         * ``login_url``: `authenticated` 装饰器将会重定向到这个url
           如果该用户没有登陆. 更多自定义特性可以通过复写
           `RequestHandler.get_login_url` 实现
         * ``xsrf_cookies``: 如果true, :ref:`xsrf` 将被开启.
         * ``xsrf_cookie_version``: 控制由该server产生的新XSRF
           cookie的版本. 一般应在默认情况下(这将是最高支持的版本),
           但是可以被暂时设置为一个较低的值, 在版本切换之间.
           在Tornado 3.2.2 中新增, 这里引入了XSRF cookie 版本2.
         * ``xsrf_cookie_kwargs``: 可设置为额外的参数字典传递给
           `.RequestHandler.set_cookie` 为该XSRF cookie.
         * ``twitter_consumer_key``, ``twitter_consumer_secret``,
           ``friendfeed_consumer_key``, ``friendfeed_consumer_secret``,
           ``google_consumer_key``, ``google_consumer_secret``,
           ``facebook_api_key``, ``facebook_secret``:  在
           `tornado.auth` 模块中使用来验证各种APIs.

         Template settings:

         * ``autoescape``: Controls automatic escaping for templates.
           May be set to ``None`` to disable escaping, or to the *name*
           of a function that all output should be passed through.
           Defaults to ``"xhtml_escape"``.  Can be changed on a per-template
           basis with the ``{% autoescape %}`` directive.
         * ``compiled_template_cache``: Default is ``True``; if ``False``
           templates will be recompiled on every request.  This option
           is new in Tornado 3.2; previously this functionality was controlled
           by the ``debug`` setting.
         * ``template_path``: Directory containing template files.  Can be
           further customized by overriding `RequestHandler.get_template_path`
         * ``template_loader``: Assign to an instance of
           `tornado.template.BaseLoader` to customize template loading.
           If this setting is used the ``template_path`` and ``autoescape``
           settings are ignored.  Can be further customized by overriding
           `RequestHandler.create_template_loader`.
         * ``template_whitespace``: Controls handling of whitespace in
           templates; see `tornado.template.filter_whitespace` for allowed
           values. New in Tornado 4.3.

         Static file settings:

         * ``static_hash_cache``: Default is ``True``; if ``False``
           static urls will be recomputed on every request.  This option
           is new in Tornado 3.2; previously this functionality was controlled
           by the ``debug`` setting.
         * ``static_path``: Directory from which static files will be
           served.
         * ``static_url_prefix``:  Url prefix for static files,
           defaults to ``"/static/"``.
         * ``static_handler_class``, ``static_handler_args``: May be set to
           use a different handler for static files instead of the default
           `tornado.web.StaticFileHandler`.  ``static_handler_args``, if set,
           should be a dictionary of keyword arguments to be passed to the
           handler's ``initialize`` method.

   .. autoclass:: URLSpec

      The ``URLSpec`` class is also available under the name ``tornado.web.url``.

   Decorators
   ----------
   .. autofunction:: asynchronous
   .. autofunction:: authenticated
   .. autofunction:: addslash
   .. autofunction:: removeslash
   .. autofunction:: stream_request_body

   Everything else
   ---------------
   .. autoexception:: HTTPError
   .. autoexception:: Finish
   .. autoexception:: MissingArgumentError
   .. autoclass:: UIModule
      :members:

   .. autoclass:: ErrorHandler
   .. autoclass:: FallbackHandler
   .. autoclass:: RedirectHandler
   .. autoclass:: StaticFileHandler
      :members:
