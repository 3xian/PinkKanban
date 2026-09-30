"""Startup regression tests: python tests/startup_browser_test.py.

Requires Playwright and Chromium (CHROMIUM_PATH may override the executable).
Uses only a local static server and mocked API responses, never production data.
"""
import asyncio
import functools
import json
import os
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import unittest
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
CSP = ("default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src 'self' https://fonts.gstatic.com data:; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
DATA = {"user": {"id": 1, "display_name": "测试", "email": "test@example.com"}, "projects": [], "unread": 0,
        "quota": {"remaining": 30, "limit": 30, "used": 0}}

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.split('?')[0] == '/':
            self.path = '/static/index.html'
        super().do_GET()
    def end_headers(self):
        self.send_header('Content-Security-Policy', CSP)
        super().end_headers()
    def log_message(self, *_):
        pass

class StartupTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=str(ROOT)))
        Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
    async def asyncSetUp(self):
        self.pw = await async_playwright().start()
        self.browser = await self.pw.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH', '/usr/bin/chromium'), headless=True, args=['--no-sandbox'])
        self.page = await self.browser.new_page(reduced_motion='reduce')
        self.errors = []
        self.page.on('pageerror', lambda err: self.errors.append(str(err)))
        await self.page.route('https://fonts.googleapis.com/**', lambda r: r.abort())
        await self.page.route('https://fonts.gstatic.com/**', lambda r: r.abort())
        self.requests = []
        async def api(route):
            self.requests.append(route.request.url)
            await route.fulfill(json=DATA if '/bootstrap' in route.request.url else {'projects': [], 'quota': DATA['quota']})
        await self.page.route('**/api/**', api)
    async def asyncTearDown(self):
        await self.browser.close()
        await self.pw.stop()
    async def test_visible_without_javascript_or_styles(self):
        context = await self.browser.new_context(java_script_enabled=False)
        page = await context.new_page()
        await page.route('**/static/css/**', lambda r: r.abort())
        await page.goto(self.url)
        self.assertTrue(await page.locator('.startup').is_visible())
        self.assertTrue(await page.locator('noscript p').is_visible())
        self.assertEqual(await page.locator('noscript p').inner_text(), '请启用 JavaScript 后重新加载看板。')
        self.assertEqual(await page.locator('body').evaluate('(el) => getComputedStyle(el).backgroundColor'), 'rgb(8, 11, 18)')
        await context.close()
    async def test_delayed_assets_show_fallback_then_projects(self):
        async def delayed(route):
            await asyncio.sleep(.7)
            await route.continue_()
        await self.page.route('**/static/js/app.js', delayed)
        await self.page.route('**/static/css/app.css', delayed)
        await self.page.goto(self.url, wait_until='commit')
        await self.page.locator('.startup').wait_for(state='visible')
        await self.page.locator('.shell').wait_for()
        self.assertEqual(len([x for x in self.requests if '/bootstrap' in x]), 1)
        self.assertFalse(any('/api/projects' in x for x in self.requests))
        self.assertFalse(self.errors)
    async def test_failed_module_keeps_reload_link(self):
        await self.page.route('**/static/js/app.js', lambda r: r.abort())
        await self.page.goto(self.url)
        await self.page.locator('#startup-message[role=alert]').wait_for()
        self.assertTrue(await self.page.get_by_role('link', name='重新加载').is_visible())
        self.assertFalse(self.errors)
    async def test_failed_css_keeps_reload_link(self):
        await self.page.route('**/static/css/app.css', lambda r: r.abort())
        await self.page.goto(self.url)
        await self.page.locator('#startup-message[role=alert]').wait_for()
        self.assertFalse(await self.page.locator('.shell').count())
    async def test_server_failure_does_not_show_login_and_reload_recovers(self):
        await self.page.route('**/api/bootstrap', lambda r: r.fulfill(status=503, json={'detail': '服务暂不可用'}))
        await self.page.goto(self.url)
        await self.page.locator('#startup-message[role=alert]').wait_for()
        self.assertFalse(await self.page.locator('.auth-card').count())
        await self.page.unroute('**/api/bootstrap')
        await self.page.get_by_role('link', name='重新加载').click()
        await self.page.locator('.shell').wait_for()
        self.assertFalse(self.errors)
    async def test_timeout_is_bounded(self):
        await self.page.add_init_script('const timer = window.setTimeout; window.setTimeout = (fn, ms, ...args) => timer(fn, ms === 15000 ? 100 : ms, ...args);')
        async def delayed(route):
            await asyncio.sleep(.5)
            await route.fulfill(json=DATA)
        await self.page.route('**/api/bootstrap', delayed)
        await self.page.goto(self.url)
        await self.page.locator('#startup-message[role=alert]').wait_for()
        self.assertIn('超时', await self.page.locator('#startup-message').inner_text())
        self.assertFalse(await self.page.locator('.auth-card').count())
        self.assertFalse(self.errors)
    async def test_logged_out_registration_toggle_and_login(self):
        await self.page.route('**/api/bootstrap', lambda r: r.fulfill(status=401, json={'detail': '请先登录'}))
        await self.page.route('**/api/auth/login', lambda r: r.fulfill(json=DATA['user']))
        await self.page.goto(self.url)
        await self.page.locator('.auth-card').wait_for()
        await self.page.get_by_role('button', name='注册', exact=True).click()
        self.assertTrue(await self.page.locator('input[name=code]').is_visible())
        await self.page.get_by_role('button', name='登录', exact=True).click()
        self.assertFalse(await self.page.locator('input[name=code]').count())
        await self.page.locator('input[name=email]').fill('test@example.com')
        await self.page.locator('input[name=password]').fill('password-test')
        await self.page.unroute('**/api/bootstrap')
        await self.page.get_by_role('button', name='进入看板').click()
        await self.page.locator('.shell').wait_for()
        self.assertFalse(self.errors)
    async def test_hash_change_during_boot_uses_latest_route(self):
        async def delayed(route):
            await asyncio.sleep(.3)
            await route.fulfill(json=DATA)
        await self.page.route('**/api/bootstrap', delayed)
        await self.page.goto(self.url, wait_until='domcontentloaded')
        await self.page.evaluate('location.hash = "#/account"')
        await self.page.locator('.shell').wait_for()
        await self.page.locator('[data-form=account]').wait_for(state='visible')
        await self.page.go_back()
        await self.page.get_by_role('heading', name='项目', exact=True).wait_for()
        self.assertFalse(self.errors)

if __name__ == '__main__':
    unittest.main(verbosity=2)
