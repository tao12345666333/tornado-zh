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
这里有一个例子, 这个例子允许用户通过一个保存在cookie中特殊的昵称登录
到应用程序中:

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

You can require that the user be logged in using the `Python
decorator <http://www.python.org/dev/peps/pep-0318/>`_
`tornado.web.authenticated`. If a request goes to a method with this
decorator, and the user is not logged in, they will be redirected to
``login_url`` (another application setting). The example above could be
rewritten:

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

If you decorate ``post()`` methods with the ``authenticated``
decorator, and the user is not logged in, the server will send a
``403`` response.  The ``@authenticated`` decorator is simply
shorthand for ``if not self.current_user: self.redirect()`` and may
not be appropriate for non-browser-based login schemes.

Check out the `Tornado Blog example application
<https://github.com/tornadoweb/tornado/tree/stable/demos/blog>`_ for a
complete example that uses authentication (and stores user data in a
MySQL database).

Third party authentication
~~~~~~~~~~~~~~~~~~~~~~~~~~

The `tornado.auth` module implements the authentication and
authorization protocols for a number of the most popular sites on the
web, including Google/Gmail, Facebook, Twitter, and FriendFeed.
The module includes methods to log users in via these sites and, where
applicable, methods to authorize access to the service so you can, e.g.,
download a user's address book or publish a Twitter message on their
behalf.

Here is an example handler that uses Google for authentication, saving
the Google credentials in a cookie for later access:

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

See the `tornado.auth` module documentation for more details.

.. _xsrf:

Cross-site request forgery protection
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

`Cross-site request
forgery <http://en.wikipedia.org/wiki/Cross-site_request_forgery>`_, or
XSRF, is a common problem for personalized web applications. See the
`Wikipedia
article <http://en.wikipedia.org/wiki/Cross-site_request_forgery>`_ for
more information on how XSRF works.

The generally accepted solution to prevent XSRF is to cookie every user
with an unpredictable value and include that value as an additional
argument with every form submission on your site. If the cookie and the
value in the form submission do not match, then the request is likely
forged.

Tornado comes with built-in XSRF protection. To include it in your site,
include the application setting ``xsrf_cookies``:

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

If ``xsrf_cookies`` is set, the Tornado web application will set the
``_xsrf`` cookie for all users and reject all ``POST``, ``PUT``, and
``DELETE`` requests that do not contain a correct ``_xsrf`` value. If
you turn this setting on, you need to instrument all forms that submit
via ``POST`` to contain this field. You can do this with the special
`.UIModule` ``xsrf_form_html()``, available in all templates::

    <form action="/new_message" method="post">
      {% module xsrf_form_html() %}
      <input type="text" name="message"/>
      <input type="submit" value="Post"/>
    </form>

If you submit AJAX ``POST`` requests, you will also need to instrument
your JavaScript to include the ``_xsrf`` value with each request. This
is the `jQuery <http://jquery.com/>`_ function we use at FriendFeed for
AJAX ``POST`` requests that automatically adds the ``_xsrf`` value to
all requests::

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

For ``PUT`` and ``DELETE`` requests (as well as ``POST`` requests that
do not use form-encoded arguments), the XSRF token may also be passed
via an HTTP header named ``X-XSRFToken``.  The XSRF cookie is normally
set when ``xsrf_form_html`` is used, but in a pure-Javascript application
that does not use any regular forms you may need to access
``self.xsrf_token`` manually (just reading the property is enough to
set the cookie as a side effect).

If you need to customize XSRF behavior on a per-handler basis, you can
override `.RequestHandler.check_xsrf_cookie()`. For example, if you
have an API whose authentication does not use cookies, you may want to
disable XSRF protection by making ``check_xsrf_cookie()`` do nothing.
However, if you support both cookie and non-cookie-based authentication,
it is important that XSRF protection be used whenever the current
request is authenticated with a cookie.
