``tornado.httpclient`` --- 异步 HTTP 客户端
===================================================

.. automodule:: tornado.httpclient

   HTTP 客户端接口
   ----------------------

   .. autoclass:: HTTPClient
      :members:

   .. autoclass:: AsyncHTTPClient
      :members:

   Request 对象
   ---------------
   .. autoclass:: HTTPRequest
      :members:
   
   Response 对象
   ----------------
   .. autoclass:: HTTPResponse
      :members:

   异常
   ----------
   .. autoexception:: HTTPError
      :members:

   Command-line 接口
   ----------------------

   This module provides a simple command-line interface to fetch a url
   using Tornado's HTTP client.  Example usage::

      # Fetch the url and print its body
      python -m tornado.httpclient http://www.google.com

      # Just print the headers
      python -m tornado.httpclient --print_headers --print_body=false http://www.google.com

Implementations
~~~~~~~~~~~~~~~

.. automodule:: tornado.simple_httpclient
   :members:

.. module:: tornado.curl_httpclient

.. class:: CurlAsyncHTTPClient(io_loop, max_clients=10, defaults=None)

   ``libcurl``-based HTTP client.
