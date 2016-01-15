认证和安全
===========================

.. testsetup::

   import tornado.web

Cookies 和 secure cookies
~~~~~~~~~~~~~~~~~~~~~~~~~~

你可以在用户浏览器中通过 ``set_cookie`` 方法设置 cookie:

.. testcode::

    class MainHandler(tornado.web.RequestHandler):
        def get(self):
            if not self.get_cookie("mycookie"):
                self.set_cookie("mycookie", "myvalue")
                self.write("Your cookie was not set yet!")
            else:
                self.write("Your cookie was set!")

.. testoutput::
   :hide:

普通的cookie并不安全, 可以通过客户端修改. 如果你需要通过设置cookie,
例如来识别当前登录的用户, 就需要给你的cookie签名防止伪造. Tornado
支持通过 `~.RequestHandler.set_secure_cookie` 和
`~.RequestHandler.get_secure_cookie` 方法对cookie签名. 想要使用这
些方法, 你需要在你创建应用的时候, 指定一个名为 ``cookie_secret``
的密钥. 你可以在应用的设置中以关键字参数的形式传递给应用程序:

.. testcode::

    application = tornado.web.Application([
        (r"/", MainHandler),
    ], cookie_secret="__TODO:_GENERATE_YOUR_OWN_RANDOM_VALUE_HERE__")

.. testoutput::
   :hide:

签名后的cookie除了时间戳和一个
`HMAC <http://en.wikipedia.org/wiki/HMAC>`_ 签名还包含编码
后的cookie值. 如果cookie过期或者签名不匹配, ``get_secure_cookie``
将返回 ``None`` 就像没有设置cookie一样. 上面例子的安全版本:

.. testcode::

    class MainHandler(tornado.web.RequestHandler):
        def get(self):
            if not self.get_secure_cookie("mycookie"):
                self.set_secure_cookie("mycookie", "myvalue")
                self.write("Your cookie was not set yet!")
            else:
                self.write("Your cookie was set!")

.. testoutput::
   :hide:

Tornado的安全cookie保证完整性但是不保证机密性. 也就是说, cookie不能被修改
但是它的内容对用户是可见的. 密钥 ``cookie_secret`` 是一个对称的key, 而且必
须保密--任何获得这个key的人都可以伪造出自己签名的cookie.

默认情况下, Tornado的安全cookie过期时间是30天. 可以给 ``set_secure_cookie``
使用 ``expires_days`` 关键字参数 *同时* ``get_secure_cookie`` 设置
``max_age_days`` 参数也可以达到效果. 这两个值分别通过这样(设置)你就可以达
到如下的效果, 例如大多数情况下有30天有效期的cookie, 但是对某些敏感操作(例
如修改账单信息)你可以使用一个较小的 ``max_age_days`` .

Tornado也支持多签名密钥, 使签名密钥轮换. ``cookie_secret`` 然后必须是一个
以整数key版本作为key, 以相对应的密钥作为值的字典. 当前使用的签名键
必须是 应用设置中 ``key_version`` 的集合. 不过字典中的其他key都允许做
cookie签名验证, 如果当前key版本在cookie集合中.为了实现cookie更新, 可以通过
`~.RequestHandler.get_secure_cookie_key_version` 查询当前key版本.

.. _user-authentication:

用户认证
~~~~~~~~~~~~~~~~~~~

当前已经通过认证的用户在每个请求处理函数中都可以通过
`self.current_user <.RequestHandler.current_user>` 得到, 在每个模板中
可以使用 ``current_user`` 获得. 默认情况下, ``current_user`` 是
``None``.

为了在你的应用程序中实现用户认证, 你需要在你的请求处理函数中复写
``get_current_user()`` 方法来判断当前用户, 比如可以基于cookie的值.
这里有一个例子, 这个例子允许用户简单的通过一个保存在cookie中的特殊昵称
登录到应用程序中:

.. testcode::

    class BaseHandler(tornado.web.RequestHandler):
        def get_current_user(self):
            return self.get_secure_cookie("user")

    class MainHandler(BaseHandler):
        def get(self):
            if not self.current_user:
                self.redirect("/login")
                return
            name = tornado.escape.xhtml_escape(self.current_user)
            self.write("Hello, " + name)

    class LoginHandler(BaseHandler):
        def get(self):
            self.write('<html><body><form action="/login" method="post">'
                       'Name: <input type="text" name="name">'
                       '<input type="submit" value="Sign in">'
                       '</form></body></html>')

        def post(self):
            self.set_secure_cookie("user", self.get_argument("name"))
            self.redirect("/")

    application = tornado.web.Application([
        (r"/", MainHandler),
        (r"/login", LoginHandler),
    ], cookie_secret="__TODO:_GENERATE_YOUR_OWN_RANDOM_VALUE_HERE__")

.. testoutput::
   :hide:

你可以使用 `Python
装饰器(decorator) <http://www.python.org/dev/peps/pep-0318/>`_
`tornado.web.authenticated` 要求用户登录. 如果请求方法带有这个装饰器
并且用户没有登录, 用户将会被重定向到 ``login_url`` (另一个应用设置).
上面的例子可以被重写:

.. testcode::

    class MainHandler(BaseHandler):
        @tornado.web.authenticated
        def get(self):
            name = tornado.escape.xhtml_escape(self.current_user)
            self.write("Hello, " + name)

    settings = {
        "cookie_secret": "__TODO:_GENERATE_YOUR_OWN_RANDOM_VALUE_HERE__",
        "login_url": "/login",
    }
    application = tornado.web.Application([
        (r"/", MainHandler),
        (r"/login", LoginHandler),
    ], **settings)

.. testoutput::
   :hide:

如果你使用 ``authenticated`` 装饰 ``post()`` 方法并且用户没有登录,
服务将返回一个 ``403`` 响应. ``@authenticated`` 装饰器是
``if not self.current_user: self.redirect()`` 的简写. 可能不适合
非基于浏览器的登录方案.

通过 `Tornado Blog example application
<https://github.com/tornadoweb/tornado/tree/stable/demos/blog>`_ 
可以看到一个使用用户验证(并且在MySQL数据库中存储用户数据)的完整例子.

第三方用户验证
~~~~~~~~~~~~~~~~~~~~~~~~~~

`tornado.auth` 模块实现了对一些网络上最流行的网站的身份认证和授权协议,
包括Google/Gmail, Facebook, Twitter,和FriendFeed. 该模块包括通过这些
网站登录用户的方法, 并在适用情况下允许访问该网站服务的方法, 例如, 下载
一个用户的地址簿或者在他们支持下发布一条Twitter信息.

这是个使用Google身份认证, 在cookie中保存Google的认证信息以供之后访问
的示例处理程序:

.. testcode::

    class GoogleOAuth2LoginHandler(tornado.web.RequestHandler,
                                   tornado.auth.GoogleOAuth2Mixin):
        @tornado.gen.coroutine
        def get(self):
            if self.get_argument('code', False):
                user = yield self.get_authenticated_user(
                    redirect_uri='http://your.site.com/auth/google',
                    code=self.get_argument('code'))
                # Save the user with e.g. set_secure_cookie
            else:
                yield self.authorize_redirect(
                    redirect_uri='http://your.site.com/auth/google',
                    client_id=self.settings['google_oauth']['key'],
                    scope=['profile', 'email'],
                    response_type='code',
                    extra_params={'approval_prompt': 'auto'})

.. testoutput::
   :hide:

查看 `tornado.auth` 模块的文档以了解更多细节.

.. _xsrf:

跨站请求伪造(防护)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

`跨站请求伪造(Cross-site request
forgery) <http://en.wikipedia.org/wiki/Cross-site_request_forgery>`_, 或
XSRF, 是所有web应用程序面临的一个主要问题. 可以通过
`Wikipedia
文章 <http://en.wikipedia.org/wiki/Cross-site_request_forgery>`_ 来了解
更多关于XSRF的细节.

普遍接受的预防XSRF攻击的方案是让每个用户的cookie都是不确定的值, 并且
把那个cookie值在你站点的每个form提交中作为额外的参数包含进来. 如果cookie
和form提交中的值不匹配, 则请求可能是伪造的.

Tornado内置XSRF保护. 你需要在你的应用设置中使用 ``xsrf_cookies`` 便可
以在你的网站上使用:

.. testcode::

    settings = {
        "cookie_secret": "__TODO:_GENERATE_YOUR_OWN_RANDOM_VALUE_HERE__",
        "login_url": "/login",
        "xsrf_cookies": True,
    }
    application = tornado.web.Application([
        (r"/", MainHandler),
        (r"/login", LoginHandler),
    ], **settings)

.. testoutput::
   :hide:

如果设置了 ``xsrf_cookies`` , Tornado web应用程序将会给所有用户设置
``_xsrf`` cookie并且拒绝所有不包含一个正确的 ``_xsrf`` 值的
``POST``, ``PUT``, 或 ``DELETE`` 请求. 如果你打开这个设置, 你必须给
所有通过 ``POST`` 请求的form提交添加这个字段. 你可以使用一个特性的
`.UIModule` ``xsrf_form_html()`` 来做这件事情, 
这个方法在所有模板中都是可用的::

    <form action="/new_message" method="post">
      {% module xsrf_form_html() %}
      <input type="text" name="message"/>
      <input type="submit" value="Post"/>
    </form>

如果你提交一个AJAX的 ``POST`` 请求, 你也需要在每个请求中给你的
JavaScript添加 ``_xsrf`` 值. 这是我们在FriendFeed为了AJAX的
``POST`` 请求使用的一个 `jQuery <http://jquery.com/>`_ 函数, 可以
自动的给所有请求添加 ``_xsrf`` 值::

    function getCookie(name) {
        var r = document.cookie.match("\\b" + name + "=([^;]*)\\b");
        return r ? r[1] : undefined;
    }

    jQuery.postJSON = function(url, args, callback) {
        args._xsrf = getCookie("_xsrf");
        $.ajax({url: url, data: $.param(args), dataType: "text", type: "POST",
            success: function(response) {
            callback(eval("(" + response + ")"));
        }});
    };

对于 ``PUT`` 和 ``DELETE`` 请求(除了不使用form编码(form-encoded) 参数
的 ``POST`` 请求, XSRF token也会通过一个 ``X-XSRFToken`` 的HTTP头传递.
XSRF cookie 通常在使用 ``xsrf_form_html`` 会设置, 但是在不使用正规
form的纯Javascript应用中, 你可能需要访问 ``self.xsrf_token`` 手动设置
(只读这个属性足够设置cookie了).

如果你需要自定义每一个处理程序基础的XSRF行为, 你可以复写
`.RequestHandler.check_xsrf_cookie()`. 例如, 如果你有一个没有使用
cookie验证的API, 你可能想禁用XSRF保护, 可以通过使 ``check_xsrf_cookie()``
不做任何处理. 然而, 如果你支持基于cookie和非基于cookie的认证, 重要的是,
当前带有cookie认证的请求究竟什么时候使用XSRF保护.
