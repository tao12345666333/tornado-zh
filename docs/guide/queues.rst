:class:`~tornado.queues.Queue` 示例 - 一个并发网络爬虫
================================================================

.. currentmodule:: tornado.queues

Tornado的 `tornado.queues` 模块实现了异步生产者/消费者模式的协程, 类似于
通过Python 标准库的 `queue` 实现线程模式.

一个yield `Queue.get` 的协程直到队列中有值的时候才会暂停. 如果队列设置了最大长度
yield `Queue.put` 的协程直到队列中有空间才会暂停.

一个 `~Queue`  从0开始对完成的任务进行计数. `~Queue.put` 加计数;
`~Queue.task_done` 减少计数.

这里的网络爬虫的例子, 队列开始的时候只包含 base_url. 当一个worker抓取到一个页面
它会解析链接并把它添加到队列中, 然后调用 `~Queue.task_done` 减少计数一次.
最后, 当一个worker抓取到的页面URL都是之前抓取到过的并且队列中没有任务了.
于是worker调用 `~Queue.task_done` 把计数减到0.
等待 `~Queue.join` 的主协程取消暂停并且完成.

.. literalinclude:: ../../demos/webspider/webspider.py
