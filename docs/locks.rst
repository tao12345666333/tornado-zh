``tornado.locks`` -- 同步原语
===============================================

.. versionadded:: 4.2

使用和标准库提供给线程相似的同步原语协调协程.

*(请注意, 这些原语不是线程安全的, 不能被用来代替标准库中的--它
们是为了协调在单线程app中的Tornado协程, 而不是为了在一个多线程
app中保护共享对象.)*

.. automodule:: tornado.locks

   Condition
   ---------
   .. autoclass:: Condition
    :members:

   Event
   -----
   .. autoclass:: Event
    :members:

   Semaphore
   ---------
   .. autoclass:: Semaphore
    :members:

   BoundedSemaphore
   ----------------
   .. autoclass:: BoundedSemaphore
    :members:
    :inherited-members:

   Lock
   ----
   .. autoclass:: Lock
    :members:
    :inherited-members:
