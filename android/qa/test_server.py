"""Regression checks using only the local QA fixture, never the application database."""
import http.client
import threading
import unittest
from http.server import ThreadingHTTPServer

from server import Handler


class StaticBoundaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def status(self, path, method="GET"):
        connection = http.client.HTTPConnection(*self.server.server_address)
        try:
            connection.request(method, path)
            response = connection.getresponse()
            response.read()
            return response.status
        finally:
            connection.close()

    def test_web_assets_remain_available(self):
        for path in ("/", "/static/index.html", "/static/js/app.js", "/static/css/app.css"):
            with self.subTest(path=path):
                self.assertEqual(self.status(path), 200)

    def test_repository_paths_and_traversal_are_rejected(self):
        for method in ("GET", "HEAD"):
            for path in ("/.env", "/.git/config", "/android/local.properties", "/static/../README.md",
                         "/static/%2e%2e/README.md", "/static/%2e%2e%2f.env", "/static/", "/static/js/"):
                with self.subTest(path=path, method=method):
                    self.assertEqual(self.status(path, method), 404)


if __name__ == "__main__":
    unittest.main()
