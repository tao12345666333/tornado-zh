协程
==========

.. testsetup::

   from tornado import gen

Tornado中推荐使用 **协程** 写异步代码. 协程使用了Python的 ``yield`` 
关键字代替链式回调来将程序挂起和恢复执行(像在 `gevent
<http://www.gevent.org>`_ 中出现的轻量级线程合作方式有时也被称为协程,
但是在Tornado中所有的协程使用明确的上下文切换,并被称为异步函数).

使用协程几乎像写同步代码一样简单, 并且不需要浪费额外的线程. 它们还通过减少上下文切换来 `使并发编程更简单
<https://glyph.twistedmatrix.com/2014/02/unyielding.html>`_ .

例子::

    from tornado import gen

    @gen.coroutine
    def fetch_coroutine(url):
        http_client = AsyncHTTPClient()
        response = yield http_client.fetch(url)
        # 在Python 3.3之前, 在generator中是不允许有返回值的
        # 必须通过抛出异常来代替.
        # 就像 raise gen.Return(response.body).
        return response.body

.. _native_coroutines:

Python 3.5: ``async`` and ``await``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Python 3.5 引入了 ``async`` 和 ``await`` 关键字(使用这些关键字的
函数也被称为"原生协程"). 从Tornado 4.3, 你可以用它们代替 ``yield`` 为基础的协程.
只需要简单的使用 ``async def foo()`` 在函数定义的时候代替 ``@gen.coroutine`` 装饰器, 用 ``await`` 代替yield. 本文档的其他部分会继续使用 ``yield`` 的风格来和旧版本的Python兼容, 但是如果 ``async`` 和 ``await`` 可用的话，它们运行起来会更快::

    async def fetch_coroutine(url):
        http_client = AsyncHTTPClient()
        response = await http_client.fetch(url)
        return response.body

``await`` 关键字比 ``yield`` 关键字功能要少一些.
例如,在一个使用 ``yield`` 的协程中， 你可以得到
``Futures`` 列表, 但是在原生协程中,你必须把列表用 `tornado.gen.multi` 包起来. 你也可以使用 `tornado.gen.convert_yielded`
来把任何使用 ``yield`` 工作的代码转换成使用 ``await`` 的形式.

虽然原生协程没有明显依赖于特定框架(例如它们没有使用装饰器,例如 `tornado.gen.coroutine` 或
`asyncio.coroutine`), 不是所有的协程都和其他的兼容. 有一个 *协程执行者(coroutine runner)* 在第一个协程被调用的时候进行选择, 然后被所有用  ``await`` 直接调用的协程共享.
Tornado 的协程执行者(coroutine runner)在设计上是多用途的,可以接受任何来自其他框架的awaitable对象;
其他的协程运行时可能有很多限制(例如, ``asyncio`` 协程执行者不接受来自其他框架的协程).
基于这些原因,我们推荐组合了多个框架的应用都使用Tornado的协程执行者来进行协程调度.
为了能使用Tornado来调度执行asyncio的协程, 可以使用
`tornado.platform.asyncio.to_asyncio_future` 适配器.


它是如何工作的
~~~~~~~~~~~~~~~~~~~~

包含了 ``yield`` 关键字的函数是一个 **生成器(generator)**. 所有的生成器都是异步的;
当调用它们的时候,会返回一个生成器对象,而不是一个执行完的结果.
``@gen.coroutine`` 装饰器通过 ``yield`` 表达式和生成器进行交流, 而且通过返回一个 `.Future` 与协程的调用方进行交互.

下面是一个协程装饰器内部循环的简单版本::

    # tornado.gen.Runner 简化的内部循环
    def run(self):
        # send(x) makes the current yield return x.
        # It returns when the next yield is reached
        future = self.gen.send(self.next)
        def callback(f):
            self.next = f.result()
            self.run()
        future.add_done_callback(callback)

装饰器从生成器接收一个 `.Future` 对象, 等待(非阻塞的)这个 `.Future` 
对象执行完成, 然后"解开(unwraps)" 这个 `.Future` 对象，并把结果作为
``yield`` 表达式的结果传回给生成器.  大多数异步代码从来不会直接接触 `.Future` 类
除非 `.Future` 立即通过异步函数返回给 ``yield`` 表达式.

如何调用协程
~~~~~~~~~~~~~~~~~~~~~~~

协程一般不会抛出异常: 它们抛出的任何异常将被 `.Future` 捕获
直到它被得到. 这意味着用正确的方式调用协程是重要的, 否则你可能有被
忽略的错误::

    @gen.coroutine
    def divide(x, y):
        return x / y

    def bad_call():
        # 这里应该抛出一个 ZeroDivisionError 的异常, 但事实上并没有
        # 因为协程的调用方式是错误的.
        divide(1, 0)

几乎所有的情况下, 任何一个调用协程的函数都必须是协程它自身, 并且在
调用的时候使用 ``yield`` 关键字. 当你复写超类中的方法, 请参阅文档,
看看协程是否支持(文档应该会写该方法 "可能是一个协程" 或者 "可能返回
一个 `.Future` ")::

    @gen.coroutine
    def good_call():
        # yield 将会解开 divide() 返回的 Future 并且抛出异常
        yield divide(1, 0)

有时你可能想要对一个协程"一劳永逸"而且不等待它的结果. 在这种情况下,
建议使用 `.IOLoop.spawn_callback`, 它使得 `.IOLoop` 负责调用. 如果
它失败了, `.IOLoop` 会在日志中把调用栈记录下来::

    # IOLoop 将会捕获异常,并且在日志中打印栈记录.
    # 注意这不像是一个正常的调用, 因为我们是通过
    # IOLoop 调用的这个函数.
    IOLoop.current().spawn_callback(divide, 1, 0)

最后, 在程序顶层, *如果 `.IOLoop` 尚未运行,* 你可以启动 `.IOLoop`,
执行协程,然后使用 `.IOLoop.run_sync` 方法停止 `.IOLoop` . 这通常被
用来启动面向批处理程序的 ``main`` 函数::

    # run_sync() 不接收参数,所以我们必须把调用包在lambda函数中.
    IOLoop.current().run_sync(lambda: divide(1, 0))

协程模式
~~~~~~~~~~~~~~~~~~

结合 callback
^^^^^^^^^^^^^^^^^^^^^^^^^^

为了使用回调而不是 `.Future` 与异步代码进行交互, 把调用包在 `.Task`
中. 这将为你添加一个回调参数并且返回一个可以yield的 `.Future` :

.. testcode::

    @gen.coroutine
    def call_task():
        # 注意这里没有传进来some_function.
        # 这里会被Task翻译成
        #   some_function(other_args, callback=callback)
        yield gen.Task(some_function, other_args)

.. testoutput::
   :hide:

调用阻塞函数
^^^^^^^^^^^^^^^^^^^^^^^^^^

从协程调用阻塞函数最简单的方式是使用
`~concurrent.futures.ThreadPoolExecutor`, 它将返回和协程兼容的 
``Futures`` ::

    thread_pool = ThreadPoolExecutor(4)

    @gen.coroutine
    def call_blocking():
        yield thread_pool.submit(blocking_func, args)

并行
^^^^^^^^^^^

协程装饰器能识别列表或者字典对象中各自的 ``Futures``, 并且并行的等待这些 ``Futures`` :

.. testcode::

    @gen.coroutine
    def parallel_fetch(url1, url2):
        resp1, resp2 = yield [http_client.fetch(url1),
                              http_client.fetch(url2)]

    @gen.coroutine
    def parallel_fetch_many(urls):
        responses = yield [http_client.fetch(url) for url in urls]
        # 响应是和HTTPResponses相同顺序的列表

    @gen.coroutine
    def parallel_fetch_dict(urls):
        responses = yield {url: http_client.fetch(url)
                            for url in urls}
        # 响应是一个字典 {url: HTTPResponse}

.. testoutput::
   :hide:

交叉存取
^^^^^^^^^^^^

有时候保存一个 `.Future` 比立即yield它更有用, 所以你可以在等待之前
执行其他操作:

.. testcode::

    @gen.coroutine
    def get(self):
        fetch_future = self.fetch_next_chunk()
        while True:
            chunk = yield fetch_future
            if chunk is None: break
            self.write(chunk)
            fetch_future = self.fetch_next_chunk()
            yield self.flush()

.. testoutput::
   :hide:

循环
^^^^^^^

协程的循环是棘手的, 因为在Python中没有办法在 ``for`` 循环或者
``while`` 循环 ``yield`` 迭代器,并且捕获yield的结果. 相反,你需要将
循环条件从访问结果中分离出来, 下面是一个使用 `Motor
<http://motor.readthedocs.org/en/stable/>`_ 的例子::

    import motor
    db = motor.MotorClient().test

    @gen.coroutine
    def loop_example(collection):
        cursor = db.collection.find()
        while (yield cursor.fetch_next):
            doc = cursor.next_object()

在后台运行
^^^^^^^^^^^^^^^^^^^^^^^^^

`.PeriodicCallback` 通常不使用协程. 相反,一个协程可以包含一个
``while True:`` 循环并使用
`tornado.gen.sleep`::

    @gen.coroutine
    def minute_loop():
        while True:
            yield do_something()
            yield gen.sleep(60)

    # Coroutines that loop forever are generally started with
    # spawn_callback().
    IOLoop.current().spawn_callback(minute_loop)

有时可能会遇到一个更复杂的循环. 例如, 上一个循环运行每次花费
``60+N`` 秒, 其中 ``N`` 是 ``do_something()`` 花费的时间. 为了
准确的每60秒运行,使用上面的交叉模式::

    @gen.coroutine
    def minute_loop2():
        while True:
            nxt = gen.sleep(60)   # 开始计时.
            yield do_something()  # 计时后运行.
            yield nxt             # 等待计时结束.
