异步和非阻塞I/O
---------------------------------

实时web功能需要为每个用户提供一个多数时间被闲置的长连接,
在传统的同步web服务器中，这意味着要为每个用户提供一个线程,
当然每个线程的开销都是很昂贵的.

为了尽量减少并发连接造成的开销，Tornado使用了一种单线程事件循环的方式.
这就意味着所有的应用代码都应该是异步非阻塞的,
因为在同一时间只有一个操作是有效的.

异步和非阻塞是非常相关的并且这两个术语经常交换使用,但它们不是完全相同的事情.

阻塞
~~~~~~~~

一个函数在等待某些事情的返回值的时候会被 **阻塞**. 函数被阻塞的原因有很多:
网络I/O,磁盘I/O,互斥锁等.事实上 *每个* 函数在运行和使用CPU的时候都或多或少
会被阻塞(举个极端的例子来说明为什么对待CPU阻塞要和对待一般阻塞一样的严肃:
比如密码哈希函数
`bcrypt <http://bcrypt.sourceforge.net/>`_, 需要消耗几百毫秒的CPU时间,这已
经远远超过了一般的网络或者磁盘请求时间了).

一个函数可以在某些方面阻塞在另外一些方面不阻塞.例如,
`tornado.httpclient` 在默认的配置下,会在DNS解析上面阻塞,但是在其他网络请
求的时候不阻塞
(为了减轻这种影响，可以用 `.ThreadedResolver` 或者是
通过正确配置 ``libcurl`` 用 ``tornado.curl_httpclient`` 来做).
在Tornado的上下文中,我们一般讨论网络I/O上下文的阻塞,尽管各种阻塞已经被最小
化.

异步
~~~~~~~~~~~~

**异步** 函数在会在完成之前返回，在应用中触发下一个动作之前通常会在后
台执行一些工作(和正常的 **同步** 函数在返回前就执行完所有的事情不同).这里列
举了几种风格的异步接口:

* 回调参数
* 返回一个占位符 (`.Future`, ``Promise``, ``Deferred``)
* 传送给一个队列
* 回调注册表 (POSIX信号)

不论使用哪种类型的接口, *按照定义* 异步函数与它们的调用者都有着不同的交互方
式;也没有什么对调用者透明的方式使得同步函数异步(类似 `gevent
<http://www.gevent.org>`_ 使用轻量级线程的系统性能虽然堪比异步系统,但它们并
没有真正的让事情异步).

例子
~~~~~~~~

一个简单的同步函数:

.. testcode::

    from tornado.httpclient import HTTPClient

    def synchronous_fetch(url):
        http_client = HTTPClient()
        response = http_client.fetch(url)
        return response.body

.. testoutput::
   :hide:

把上面的例子用回调参数重写的异步函数:

.. testcode::

    from tornado.httpclient import AsyncHTTPClient

    def asynchronous_fetch(url, callback):
        http_client = AsyncHTTPClient()
        def handle_response(response):
            callback(response.body)
        http_client.fetch(url, callback=handle_response)

.. testoutput::
   :hide:

使用 `.Future` 代替回调:

.. testcode::

    from tornado.concurrent import Future

    def async_fetch_future(url):
        http_client = AsyncHTTPClient()
        my_future = Future()
        fetch_future = http_client.fetch(url)
        fetch_future.add_done_callback(
            lambda f: my_future.set_result(f.result()))
        return my_future

.. testoutput::
   :hide:

`.Future` 版本明显更加复杂，但是 ``Futures`` 却是Tornado中推荐的写法
因为它有两个主要的优势.首先是错误处理更加一致,因为 `.Future.result` 
方法可以简单的抛出异常(相较于常见的回调函数接口特别指定错误处理),
而且 ``Futures`` 很适合和协程一起使用.协程会在后面深入讨论.这里是上
面例子的协程版本,和最初的同步版本很像:

.. testcode::

    from tornado import gen

    @gen.coroutine
    def fetch_coroutine(url):
        http_client = AsyncHTTPClient()
        response = yield http_client.fetch(url)
        raise gen.Return(response.body)

.. testoutput::
   :hide:

``raise gen.Return(response.body)`` 声明是在Python 2 (and 3.2)下人为
执行的, 因为在其中生成器不允许返回值.为了克服这个问题,Tornado的协程
抛出一种特殊的叫 `.Return` 的异常. 协程捕获这个异常并把它作为返回值.
在Python 3.3和更高版本,使用 ``return
response.body`` 有相同的结果.
