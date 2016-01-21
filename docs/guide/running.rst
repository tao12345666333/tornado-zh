运行和部署
=====================

因为Tornado内置了自己的HTTPServer, 运行和部署它与其他Python web框架不
太一样. 你需要写一个``main()``函数来启动服务, 而不是配置一个WSGI容器
来运行你的应用:

.. testcode::

    def main():
        app = make_app()
        app.listen(8888)
        IOLoop.current().start()

    if __name__ == '__main__':
        main()

.. testoutput::
   :hide:

配置你的操作系统或者进程管理器来运行这个程序以启动服务. 请注意, 增加每个
进程允许打开的最大文件句柄数是可能是必要的(为了避免"Too many open files"
的错误). 为了增加这个上限(例如设置为50000 ) 你可以使用ulimit命令, 
修改/etc/security/limits.conf 或者设置``minfds`` 在你的supervisord配置中.

进程和端口
~~~~~~~~~~~~~~~~~~~

由于Python的GIL(全局解释器锁), 为了充分利用多CPU的机器, 运行多个Python
进程是很有必要的. 通常, 最好是每个CPU运行一个进程.

Tornado包含了一个内置的多进程模式来一次启动多个进程. 这需要一个在main
函数上做点微小的改变:

.. testcode::

    def main():
        app = make_app()
        server = tornado.httpserver.HTTPServer(app)
        server.bind(8888)
        server.start(0)  # forks one process per cpu
        IOLoop.current().start()

.. testoutput::
   :hide:

这是最简单的方式来启动多进程并让他们共享同样的端口, 虽然它有一些局限
性. 首先, 每个子进程将有它自己的IOLoop, 所以fork之前, 不接触全局
IOLoop实例是重要的(甚至是间接的). 其次, 在这个模型中, 很难做到零停机
(zero-downtime)更新. 最后, 因为所有的进程共享相同的端口, 想单独监控
它们就更加困难了.

对更复杂的部署, 建议启动独立的进程, 并让它们各自监听不同的端口.
`supervisord <http://www.supervisord.org>`_ 的"进程组(process groups)"
功能是一个很好的方式来安排这些. 当每个进程使用不同的端口, 一个外部的
负载均衡器例如HAProxy 或nginx通常需要对外向访客提供一个单一的地址.


运行在负载均衡器后面
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当运行在一个负载均衡器例如nginx, 建议传递``xheaders=True`` 给
`.HTTPServer` 的构造器. 这将告诉Tornado使用类似 ``X-Real-IP``
这样的HTTP头来获取用户的IP地址而不是把所有流量都认为来自于
负载均衡器的IP地址.

这是一份原始的nginx配置文件, 在结构上类似于我们在FriendFeed所使用的
配置. 这是假设nginx和Tornado server运行在同一台机器上的, 并且四个
Tornado server正运行在8000 - 8003端口::

    user nginx;
    worker_processes 1;

    error_log /var/log/nginx/error.log;
    pid /var/run/nginx.pid;

    events {
        worker_connections 1024;
        use epoll;
    }

    http {
        # Enumerate all the Tornado servers here
        upstream frontends {
            server 127.0.0.1:8000;
            server 127.0.0.1:8001;
            server 127.0.0.1:8002;
            server 127.0.0.1:8003;
        }

        include /etc/nginx/mime.types;
        default_type application/octet-stream;

        access_log /var/log/nginx/access.log;

        keepalive_timeout 65;
        proxy_read_timeout 200;
        sendfile on;
        tcp_nopush on;
        tcp_nodelay on;
        gzip on;
        gzip_min_length 1000;
        gzip_proxied any;
        gzip_types text/plain text/html text/css text/xml
                   application/x-javascript application/xml
                   application/atom+xml text/javascript;

        # Only retry if there was a communication error, not a timeout
        # on the Tornado server (to avoid propagating "queries of death"
        # to all frontends)
        proxy_next_upstream error;

        server {
            listen 80;

            # Allow file uploads
            client_max_body_size 50M;

            location ^~ /static/ {
                root /var/www;
                if ($query_string) {
                    expires max;
                }
            }
            location = /favicon.ico {
                rewrite (.*) /static/favicon.ico;
            }
            location = /robots.txt {
                rewrite (.*) /static/robots.txt;
            }

            location / {
                proxy_pass_header Server;
                proxy_set_header Host $http_host;
                proxy_redirect off;
                proxy_set_header X-Real-IP $remote_addr;
                proxy_set_header X-Scheme $scheme;
                proxy_pass http://frontends;
            }
        }
    }

静态文件和文件缓存
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Tornado中, 你可以通过在应用程序中指定特殊的 ``static_path`` 来提供静态文
件服务::

    settings = {
        "static_path": os.path.join(os.path.dirname(__file__), "static"),
        "cookie_secret": "__TODO:_GENERATE_YOUR_OWN_RANDOM_VALUE_HERE__",
        "login_url": "/login",
        "xsrf_cookies": True,
    }
    application = tornado.web.Application([
        (r"/", MainHandler),
        (r"/login", LoginHandler),
        (r"/(apple-touch-icon\.png)", tornado.web.StaticFileHandler,
         dict(path=settings['static_path'])),
    ], **settings)

这些设置将自动的把所有以 ``/static/`` 开头的请求从static目录进行提供,
e.g., ``http://localhost:8888/static/foo.png`` 将会通过指定的static目录
提供 ``foo.png`` 文件. 我们也自动的会从static目录提供 ``/robots.txt``
和 ``/favicon.ico`` (尽管它们并没有以 ``/static/`` 前缀开始).

在上面的设置中, 我们明确的配置Tornado 提供 ``apple-touch-icon.png``
文件从 `.StaticFileHandler` 根下, 虽然文件在static文件目录中.
(正则表达式捕获组必须告诉 `.StaticFileHandler` 请求的文件名; 调用捕获组
把文件名作为方法的参数传递给处理程序.) 你可以做同样的事情 e.g.
从网站的根提供 ``sitemap.xml`` 文件. 当然, 你也可以通过在你的HTML中使用
``<link />`` 标签来避免伪造根目录的 ``apple-touch-icon.png`` .

为了改善性能, 通常情况下, 让浏览器主动缓存静态资源是个好主意, 这样浏览器
就不会发送不必要的可能在渲染页面时阻塞的 ``If-Modified-Since`` 或
``Etag`` 请求了. Tornado使用 *静态内容版本(static content versioning)*
来支持此项功能.

为了使用这些功能, 在你的模板中使用 `~.RequestHandler.static_url` 方法
而不是直接在你的HTML中输入静态文件的URL::

    <html>
       <head>
          <title>FriendFeed - {{ _("Home") }}</title>
       </head>
       <body>
         <div><img src="{{ static_url("images/logo.png") }}"/></div>
       </body>
     </html>

``static_url()`` 函数将把相对路径翻译成一个URI类似于
``/static/images/logo.png?v=aae54``. 其中的 ``v`` 参数是 ``logo.png``
内容的哈希(hash), 并且它的存在使得Tornado服务向用户的浏览器发送缓存头,
这将使浏览器无限期的缓存内容.

因为参数 ``v`` 是基于文件内容的, 如果你更新一个文件并重启服务, 它将发送
一个新的 ``v`` 值, 所以用户的浏览器将会自动的拉去新的文件. 如果文件的内
容没有改变, 浏览器将会继续使用本地缓存的副本, 而不会从服务器检查更新,
显著的提高了渲染性能.

在生产中, 你可能想提供静态文件通过一个更优的静态服务器, 比如
`nginx <http://nginx.net/>`_ . 你可以配置任何web服务器识别通过
``static_url()`` 提供的版本标签并相应的设置缓存头. 下面是我们在
FriendFeed 使用的nginx相关配置的一部分::

    location /static/ {
        root /var/friendfeed/static;
        if ($query_string) {
            expires max;
        }
     }

.. _debug-mode:

Debug模式和自动重载
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

如果传递 ``debug=True`` 配置给 ``Application`` 的构造函数, 应用程序将会
运行在debug/开发模式. 在这个模式下, 为了方便于开发的一些功能将被启用(
每一个也可以作为独立的标签使用; 如果它们都被专门指定, 那它们都将获得
独立的优先级):

* ``autoreload=True``: 应用程序将会观察它的源文件是否改变, 并且当任何
  文件改变的时候便重载它自己. 这减少了在开发中需要手动重启服务的需求.
  然而, 在debug模式下, 某些错误(例如import的时候有语法错误)会导致服务
  关闭, 并且无法自动恢复.
* ``compiled_template_cache=False``: 模板将不会被缓存.
* ``static_hash_cache=False``: 静态文件哈希 (被 ``static_url`` 函数
  使用) 将不会被缓存
* ``serve_traceback=True``: 当一个异常在 `.RequestHandler` 中没有捕获,
  将会生成一个包含调用栈信息的错误页.

自动重载(autoreload)模式和 `.HTTPServer` 的多进程模式不兼容. 你不能给
`HTTPServer.start <.TCPServer.start>` 传递1以外的参数(或者调用
`tornado.process.fork_processes`) 当你使用自动重载模式的时候.

debug模式的自动重载功能可作为一个独立的模块位于 `tornado.autoreload`.
以下两者可以结合使用, 在语法错误之时提供额外的健壮性: 设置
``autoreload=True`` 可以在app运行时检测文件修改, 还有启动
``python -m tornado.autoreload myserver.py`` 来捕获任意语法错误或者
其他的启动时错误.

重载会丢失任何Python解释器命令行参数(e.g. ``-u``). 因为它使用
`sys.executable` 和 `sys.argv` 重新执行Python. 此外, 修改这些变量
将造成重载错误.

在一些平台(包括Windows 和Mac OSX 10.6之前), 进程不能被"原地"更新,
所以当检测到代码更新, 旧服务就会退出然后启动一个新服务. 这已经被公知
来混淆一些IDE.


WSGI和Google App Engine
~~~~~~~~~~~~~~~~~~~~~~~~~~

Tornado通常是独立运行的, 不需要一个WSGI容器. 然而, 在一些环境中
(例如Google App Engine), 只运行WSGI, 应用程序不能独立运行自己的
服务. 在这种情况下, Tornado支持一个有限制的操作模式, 不支持异步
操作但允许一个Tornado's功能的子集在仅WSGI环境中. 以下功能在WSGI
模式下是不支持的, 包括协程, ``@asynchronous`` 装饰器,
`.AsyncHTTPClient`, ``auth`` 模块和WebSockets.

你可以使用 `tornado.wsgi.WSGIAdapter` 把一个Tornado
`.Application` 转换成WSGI应用. 在这个例子中, 配置你的WSGI容器发
现 ``application`` 对象:

.. testcode::

    import tornado.web
    import tornado.wsgi

    class MainHandler(tornado.web.RequestHandler):
        def get(self):
            self.write("Hello, world")

    tornado_app = tornado.web.Application([
        (r"/", MainHandler),
    ])
    application = tornado.wsgi.WSGIAdapter(tornado_app)

.. testoutput::
   :hide:

查看 `appengine example application
<https://github.com/tornadoweb/tornado/tree/stable/demos/appengine>`_ 以
了解AppEngine在Tornado上开发的完整功能.
