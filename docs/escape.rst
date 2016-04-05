``tornado.escape`` --- 转义和字符串操作
=======================================================

.. automodule:: tornado.escape

   转义函数
   ------------------

   .. autofunction:: xhtml_escape
   .. autofunction:: xhtml_unescape

   .. autofunction:: url_escape
   .. autofunction:: url_unescape

   .. autofunction:: json_encode
   .. autofunction:: json_decode

   Byte/unicode 转换 
   ------------------------
   这些函数在Tornado自身中被广泛使用, 但不应该被大多数应用程序直接
   需要. 值得注意的是,许多这些功能的复杂性来源于这样一个事实:
   Tornado 同时支持Python 2 和Python 3.

   .. autofunction:: utf8
   .. autofunction:: to_unicode
   .. function:: native_str

      转换一个byte 或unicode 字符串到 `str` 类型. 等价于
      Python 2的 `utf8` 和Python 3的 `to_unicode` .

   .. autofunction:: to_basestring

   .. autofunction:: recursive_unicode

   其他函数
   -----------------------
   .. autofunction:: linkify
   .. autofunction:: squeeze
