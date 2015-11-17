.. title:: Tornado Web Server

|Tornado Web Server|
======================

.. |Tornado Web Server| image:: tornado.png
    :alt: Tornado Web Server

`Tornado <http://www.tornadoweb.org>`_ 是一个Python web框架和异步网络库，起初在 `FriendFeed
<http://friendfeed.com>`_ 开发. 通过使用非阻塞网络I/O， Tornado可以支撑上万级的连接，处理 `长连接 <http://en.wikipedia.org/wiki/Push_technology#Long_polling>`_,
`WebSockets <http://en.wikipedia.org/wiki/WebSocket>`_ ，和其他需要与每个用户保持长久连接的应用.

相关链接
-----------

* `下载当前4.3版本 <https://github.com/tornadoweb/tornadohttps://pypi.python.org/packages/source/t/tornado/tornado-4.3.tar.gz>`_
* `源码 (github) <https://github.com/tornadoweb/tornado>`_
* 邮件列表: `discussion <http://groups.google.com/group/python-tornado>`_ and `announcements <http://groups.google.com/group/python-tornado-announce>`_
* `Stack Overflow <http://stackoverflow.com/questions/tagged/tornado>`_
* `Wiki <https://github.com/tornadoweb/tornado/wiki/Links>`_

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

这个例子没有使用Tornado的任何异步特性;了解详情请看 `simple chat room
<https://github.com/tornadoweb/tornado/tree/stable/demos/chat>`_.

安装
-----

**自动安装**::

    pip install tornado

Tornado在 `PyPI <http://pypi.python.org/pypi/tornado>`_ 列表中，可以使用 ``pip`` 或 ``easy_install`` 安装. 注意源码发布中包含的示例应用可能不会出现在这种方式安装的代码中，所以你也可能希望通过下载一份源码包的拷贝来进行安装.

**手动安装**: 下载当前4.3版本:

.. parsed-literal::

    tar xvzf tornado-4.3.tar.gz
    cd tornado-4.3
    python setup.py build
    sudo python setup.py install

Tornado的源码托管在 `hosted on GitHub
<https://github.com/tornadoweb/tornado>`_.

**Prerequisites**: Tornado 4.3 运行在Python 2.6, 2.7, 和 3.2+
(对Python 2.6 和 3.2的支持是不推荐的并将在下个版本中移除). 对Python 2的2.7.9或更新版 *强烈*
推荐提高对SSL支持. 另外Tornado的依赖包可能通过 ``pip`` or ``setup.py install`` 被自动安装,
下面这些可选包可能是有用的:

* `unittest2 <https://pypi.python.org/pypi/unittest2>`_ 是用来在Python 2.6上运行Tornado的测试用例的(更高版本的Python是不需要的)
* `concurrent.futures <https://pypi.python.org/pypi/futures>`_ 是推荐配合Tornado使用的线程池并且可以支持 `tornado.netutil.ThreadedResolver` 的用法. 它只在Python 2中被需要，Python 3已经包括了这个标准库.
* `pycurl <http://pycurl.sourceforge.net>`_ 是在
  ``tornado.curl_httpclient`` 中可选使用的.需要Libcurl 7.19.3.1 或更高版本;推荐使用7.21.1或更高版本.
* `Twisted <http://www.twistedmatrix.com>`_ 会在
  `tornado.platform.twisted` 中使用.
* `pycares <https://pypi.python.org/pypi/pycares>`_ 是一个当线程不适用情况下的非阻塞DNS解决方案.
* `Monotime <https://pypi.python.org/pypi/Monotime>`_ 添加对monotonic clock的支持,当环境中的时钟被频繁调整的时候，改善其可靠性. 在Python 3.3中不再需要.

**平台**: Tornado可以运行在任何类Unix平台上,虽然为了最好的性能和可扩展性
只有Linux(使用 ``epoll``)和BSD(使用 ``kqueue``)是推荐的产品部署环境(尽管Mac OS X通过BSD发展来并且支持kqueue,但它的网络质量很差，所以它只适合开发使用)
Tornado也可以运行在Windows上，虽然它的配置不是官方支持的,同时也仅仅推荐开发使用.

文档
-------------

这个文档同时也提供 `PDF 和 Epub 格式
<https://readthedocs.org/projects/tornado/downloads/>`_.

.. toctree::
   :titlesonly:

   guide
   webframework
   http
   networking
   coroutine
   integration
   utilities
   faq
   releases

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

讨论和支持
----------------------

你可以讨论Tornado在 `Tornado 开发者邮件列表
<http://groups.google.com/group/python-tornado>`_, 报告bug在 `GitHub issue tracker
<https://github.com/tornadoweb/tornado/issues>`_. 

其他资源可以在 `Tornado wiki
<https://github.com/tornadoweb/tornado/wiki/Links>`_ 上找到. 新版本会宣布在 `announcements mailing list
<http://groups.google.com/group/python-tornado-announce>`_.

Tornado is available under
the `Apache License, Version 2.0
<http://www.apache.org/licenses/LICENSE-2.0.html>`_.

This web site and all documentation is licensed under `Creative
Commons 3.0 <http://creativecommons.org/licenses/by/3.0/>`_.
