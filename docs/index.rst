.. title:: Tornado Web Server




|Tornado Web Server|
======================

.. |Tornado Web Server| image:: tornado.png
    :alt: Tornado Web Server

`Tornado <http://www.tornadoweb.org>`_ 是一个Python web 框架和异步网络库，起初在 `FriendFeed
<http://friendfeed.com>`_ 开发. 通过使用非阻塞网络 I/O， Tornado 可以支撑上万级的连接，处理 `长连接 <http://en.wikipedia.org/wiki/Push_technology#Long_polling>`_,
`WebSockets <http://en.wikipedia.org/wiki/WebSocket>`_, 和其他需要与每个用户保持长久连接的应用.

相关链接
-----------

* `下载当前4.3版本 <https://github.com/tornadoweb/tornadohttps://pypi.python.org/packages/source/t/tornado/tornado-4.3.tar.gz>`_
* `源码 (github) <https://github.com/tornadoweb/tornado>`_
* 邮件列表: `discussion <http://groups.google.com/group/python-tornado>`_ and `announcements <http://groups.google.com/group/python-tornado-announce>`_
* `Stack Overflow <http://stackoverflow.com/questions/tagged/tornado>`_
* `Wiki <https://github.com/tornadoweb/tornado/wiki/Links>`_

.. |Download current version| replace:: Download version |version|

Hello, world
------------

这是一个简单的Tornado的web应用::

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

这个例子没有使用Tornado的任何异步特性; 了解详情请看 `simple chat room
<https://github.com/tornadoweb/tornado/tree/stable/demos/chat>`_.

安装
------------

**自动安装**::

    pip install tornado
