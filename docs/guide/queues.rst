:class:`~tornado.queues.Queue` 示例 - 一个并发网络爬虫
================================================================

.. currentmodule:: tornado.queues

Tornado的 `tornado.queues` 模块实现了异步生产者/消费者模式的协程, 类似于
通过Python 标准库的 `queue` 实现线程模式.

一个yield `Queue.get` 的协程直到队列中有值的时候才会暂停. 如果队列设置了最大长度
yield `Queue.put` 的协程直到队列中有空间才会暂停.
A coroutine that yields `Queue.get` pauses until there is an item in the queue.
If the queue has a maximum size set, a coroutine that yields `Queue.put` pauses
until there is room for another item.

A `~Queue` maintains a count of unfinished tasks, which begins at zero.
`~Queue.put` increments the count; `~Queue.task_done` decrements it.

In the web-spider example here, the queue begins containing only base_url. When
a worker fetches a page it parses the links and puts new ones in the queue,
then calls `~Queue.task_done` to decrement the counter once. Eventually, a
worker fetches a page whose URLs have all been seen before, and there is also
no work left in the queue. Thus that worker's call to `~Queue.task_done`
decrements the counter to zero. The main coroutine, which is waiting for
`~Queue.join`, is unpaused and finishes.

.. literalinclude:: ../../demos/webspider/webspider.py
