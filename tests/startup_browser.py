"""Standalone startup regression tests: python tests/startup_browser.py.

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
from urllib.parse import urlsplit
from playwright.async_api import async_playwright, expect

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
        self.browser = await self.pw.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH', self.pw.chromium.executable_path), headless=True, args=['--no-sandbox'])
        self.page = await self.browser.new_page(reduced_motion='reduce')
        self.errors = []
        self.page.on('pageerror', lambda err: self.errors.append(str(err)))
        await self.page.route('https://fonts.googleapis.com/**', lambda r: r.abort())
        await self.page.route('https://fonts.gstatic.com/**', lambda r: r.abort())
        self.requests = []
        responses = {
            '/api/bootstrap': DATA,
            '/api/projects': {'projects': [], 'quota': DATA['quota']},
            '/api/auth/tokens': {'items': []},
        }
        async def api(route):
            self.requests.append(route.request.url)
            path = urlsplit(route.request.url).path
            if path not in responses:
                await route.fulfill(status=404, json={'detail': f'Unexpected test API endpoint: {path}'})
                return
            await route.fulfill(json=responses[path])
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
        await expect(self.page.locator('[data-token-form] button[type=submit]')).to_be_enabled()
        await self.page.go_back()
        await self.page.get_by_role('heading', name='项目', exact=True).wait_for()
        self.assertFalse(self.errors)
    async def test_avatar_categories_save_and_responsive_layout(self):
        saved = {**DATA['user'], 'avatar_id': 'male-1'}
        await self.page.route('**/api/bootstrap', lambda r: r.fulfill(json={**DATA, 'user': saved}))
        async def profile(route):
            saved.update(route.request.post_data_json)
            await route.fulfill(json=saved)
        await self.page.route('**/api/auth/me', profile)
        await self.page.set_viewport_size({'width': 1440, 'height': 900})
        await self.page.goto(self.url + '/#/account')
        await self.page.locator('[data-form=account]').wait_for()
        await self.page.locator('input[name=display_name]').fill('我的新名字')
        for category in ('男生', '女生', '宠物', '机器人'):
            await self.page.get_by_role('button', name=category, exact=True).click()
            await expect(self.page.locator('.avatar-choice')).to_have_count(6)
            for image in await self.page.locator('.avatar-choice img').all():
                await image.evaluate('(img) => img.decode()')
        await self.page.get_by_role('button', name='奶油弹簧', exact=True).click()
        await self.page.get_by_role('button', name='宠物', exact=True).click()
        await expect(self.page.locator('input[name=avatar_id]')).to_have_value('robot-6')
        await expect(self.page.locator('input[name=display_name]')).to_have_value('我的新名字')
        await self.page.get_by_role('button', name='保存', exact=True).click()
        await expect(self.page.locator('.account-id img')).to_have_attribute('src', '/static/avatars/robot-6.webp?v=1')
        self.assertEqual(saved['avatar_id'], 'robot-6')
        for width in (1920, 1024, 901, 768, 701, 700, 390, 320):
            await self.page.set_viewport_size({'width': width, 'height': 900})
            self.assertTrue(await self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
            self.assertTrue(await self.page.evaluate('Array.from(document.querySelectorAll(".account-page *")).every(node => node.getBoundingClientRect().right <= innerWidth + 1)'))
        await self.page.reload()
        await expect(self.page.locator('input[name=avatar_id]')).to_have_value('robot-6')
        await self.page.get_by_role('button', name='宠物', exact=True).click()
        await self.page.get_by_role('button', name='橘猫', exact=True).click()
        await self.page.get_by_role('button', name='保存', exact=True).click()
        await expect(self.page.locator('.account-id img')).to_have_attribute('src', '/static/avatars/pet-1.webp?v=1')
        self.assertFalse(self.errors)

    async def mock_board(self):
        await self.page.add_init_script('''
            window.boardStreams = [];
            window.EventSource = class extends EventTarget {
                static CLOSED = 2;
                readyState = 1;
                constructor(url) {
                    super(); this.url = url; window.boardStreams.push(this);
                    queueMicrotask(() => this.emit('ready'));
                }
                emit(name) { this.dispatchEvent(new Event(name)); }
                close() { this.readyState = 2; }
            };
        ''')
        board = {
            'project': {'id': 1, 'name': '滚动测试', 'archived': False},
            'role': 'owner', 'members': [], 'labels': [],
            'columns': [
                {'id': column_id, 'name': f'列表 {column_id}', 'color': '#7A5EA8',
                 'wip_limit': None, 'cards': [
                     {'id': column_id * 100 + i, 'title': f'任务 {i}',
                      'column_id': column_id, 'priority': 'none', 'due_on': None,
                      'done': False, 'archived': False, 'assignee_ids': [], 'label_ids': [],
                      'checklist': {'done': 0, 'total': 0},
                      'comment_count': 0, 'attachment_count': 0}
                     for i in range(40)
                 ]}
                for column_id in range(1, 7)
            ],
        }
        self.board_requests = 0
        async def fetch_board(route):
            self.board_requests += 1
            await route.fulfill(json=board)
        await self.page.route('**/api/projects/1/board', fetch_board)
        await self.page.route('**/api/notifications', lambda r: r.fulfill(json={'items': [], 'unread': 0}))
        await self.page.clock.install()
        return board

    async def board_event(self, name='change'):
        async with self.page.expect_response('**/api/projects/1/board'):
            await self.page.evaluate('(name) => window.boardStreams.at(-1).emit(name)', name)
            await self.page.clock.run_for(500)
        await self.page.clock.run_for(500)

    async def open_mock_board(self, width=1280, height=800):
        await self.page.set_viewport_size({'width': width, 'height': height})
        url = self.url + '/#/board/1'
        if self.page.url == url:
            await self.page.reload()
        else:
            await self.page.goto(url)
        await self.page.locator('#board-canvas').wait_for()
        await self.page.clock.run_for(1000)

    async def settle_board_scrollbar(self):
        # Scroll events and their animation frames can arrive after scrollLeft
        # changes. Start mutation assertions only once the thumb catches up.
        for _ in range(10):
            await asyncio.sleep(.02)
            await self.page.clock.run_for(100)
            settled = await self.page.evaluate('''() => {
                const canvas = document.querySelector('.board-canvas');
                const thumb = document.querySelector('.board-scrollbar-thumb');
                const max = canvas.scrollWidth - canvas.clientWidth;
                return Number(thumb.getAttribute('aria-valuenow')) === (max > 0 ? Math.round(canvas.scrollLeft / max * 100) : 0);
            }''')
            if settled:
                return
        self.fail('Board scrollbar did not catch up with the canvas')

    async def test_board_events_preserve_nodes_and_scroll_on_desktop_and_mobile(self):
        board = await self.mock_board()
        positions = '''() => {
            const canvas = document.querySelector('#board-canvas');
            const view = document.querySelector('.board-main');
            return {
                page: [view.scrollLeft, view.scrollTop],
                canvas: [canvas.scrollLeft, canvas.scrollTop],
                columns: Object.fromEntries(Array.from(canvas.querySelectorAll('[data-drop-column]'), column => [
                    column.dataset.dropColumn, column.querySelector('.column-cards').scrollTop
                ])),
            };
        }'''
        for width, height in ((1280, 800), (390, 844)):
            with self.subTest(width=width):
                board['columns'][0]['cards'][0]['title'] = '任务 0'
                await self.open_mock_board(width, height)
                await self.page.evaluate('''() => {
                    const canvas = document.querySelector('#board-canvas');
                    canvas.scrollLeft = canvas.querySelector('.column').offsetWidth + 16;
                    canvas.scrollTop = 250;
                    document.querySelector('.board-main').scrollTop = 600;
                    canvas.querySelectorAll('.column-cards').forEach((body, i) => body.scrollTop = 200 + i * 100);
                }''')
                await self.settle_board_scrollbar()
                before = await self.page.evaluate(positions)
                self.assertGreater(before['canvas'][0], 0)
                if width > 900:
                    self.assertTrue(all(top > 0 for top in before['columns'].values()))
                else:
                    self.assertGreater(before['page'][1] + before['canvas'][1], 0)
                await self.page.evaluate('''() => {
                    window.originalCanvas = document.querySelector('#board-canvas');
                    window.originalCards = Array.from(document.querySelectorAll('.card'));
                    window.boardMutations = [];
                    new MutationObserver(records => boardMutations.push(...records))
                        .observe(document.querySelector('.board-page'), {subtree: true, childList: true, attributes: true, characterData: true});
                }''')
                # Identical snapshots don't mutate the DOM; changed cards keep their nodes.
                for updated in (False, True):
                    if updated:
                        board['columns'][0]['cards'][0]['title'] = '任务已更新'
                    await self.board_event()
                    await expect(self.page.locator('.card-title').first).to_have_text(board['columns'][0]['cards'][0]['title'])
                    self.assertEqual(await self.page.evaluate(positions), before)
                    self.assertTrue(await self.page.evaluate('originalCanvas === document.querySelector("#board-canvas") && originalCards.every(node => node.isConnected)'))
                    if not updated:
                        self.assertEqual(await self.page.evaluate('boardMutations.map(record => ({type: record.type, target: record.target.parentElement?.outerHTML.slice(0, 250)}))'), [])
                requests_before = self.board_requests
                await self.page.clock.fast_forward(24000)
                self.assertEqual(self.board_requests, requests_before)
        self.assertFalse(self.errors)

    async def test_mobile_hidden_board_keeps_scroll_during_live_updates(self):
        board = await self.mock_board()
        await self.open_mock_board(390, 844)
        await self.page.evaluate('''() => {
            document.querySelector('.board-main').scrollTop = 600;
            document.querySelector('.board-canvas').scrollLeft = 316;
        }''')
        await self.page.clock.run_for(300)
        positions = '''() => [document.querySelector('.board-main').scrollTop,
                              document.querySelector('.board-canvas').scrollLeft]'''
        before = await self.page.evaluate(positions)
        await self.page.get_by_role('tab', name='项目动态', exact=True).click()
        board['columns'][0]['cards'][0]['title'] = '切换期间收到的更新'
        await self.board_event()
        await expect(self.page.locator('.project-activity')).to_be_visible()
        await self.page.get_by_role('tab', name='看板', exact=True).click()
        await expect(self.page.locator('.card-title').first).to_have_text('切换期间收到的更新')
        self.assertEqual(await self.page.evaluate(positions), before)
        self.assertFalse(self.errors)

    async def test_hidden_board_preserves_reading_anchor_across_structural_updates(self):
        board = await self.mock_board()
        await self.open_mock_board(390, 844)
        await self.page.evaluate('document.querySelector(".board-main").scrollTop = 600')
        await self.page.clock.run_for(300)
        anchor_top = await self.page.evaluate('''() => {
            const bounds = document.querySelector('.board-main').getBoundingClientRect();
            window.readingCard = Array.from(document.querySelectorAll('.column:first-child .card'))
                .find(card => card.getBoundingClientRect().bottom > bounds.top);
            return readingCard.getBoundingClientRect().top;
        }''')
        cards = board['columns'][0]['cards']
        inserted = {**cards[0], 'id': 99999, 'title': '隐藏时插入'}
        for change in ('insert', 'delete', 'reorder'):
            with self.subTest(change=change):
                await self.page.get_by_role('tab', name='项目动态', exact=True).click()
                if change == 'insert':
                    cards.insert(0, inserted)
                elif change == 'delete':
                    cards.remove(inserted)
                else:
                    cards.append(cards.pop(0))
                await self.board_event()
                await self.page.get_by_role('tab', name='看板', exact=True).click()
                self.assertTrue(await self.page.evaluate('readingCard.isConnected'))
                self.assertAlmostEqual(await self.page.evaluate('readingCard.getBoundingClientRect().top'), anchor_top, delta=1)
                expected_ids = [str(card['id']) for card in cards]
                self.assertEqual(await self.page.locator('.column:first-child .card').evaluate_all('nodes => nodes.map(n => n.dataset.id)'), expected_ids)

        await self.page.get_by_role('tab', name='项目动态', exact=True).click()
        cards[0]['title'] = '恢复桌面时显示最新数据'
        await self.board_event()
        await self.page.set_viewport_size({'width': 1280, 'height': 800})
        await expect(self.page.locator('.card-title').first).to_have_text('恢复桌面时显示最新数据')
        self.assertTrue(await self.page.evaluate('readingCard.isConnected'))
        self.assertFalse(self.errors)

    async def test_mobile_activity_owns_pull_refresh_scroll_boundary(self):
        await self.mock_board()
        items = [dict(id=i, user={'id': 1, 'display_name': '用户'}, action='comment.added',
                      detail={'title': '任务', 'body': '评论内容 ' * 20}, created_at='2026-10-25T08:00:00Z')
                 for i in range(80)]
        await self.page.route('**/api/projects/1/activity', lambda r: r.fulfill(json={'items': items}))
        await self.open_mock_board(390, 844)
        await self.page.evaluate('document.querySelector(".board-main").scrollTop = 600')
        await self.page.get_by_role('tab', name='项目动态', exact=True).click()
        for scroll, allowed in ((300, False), (0, True)):
            await self.page.locator('.project-activity-feed').evaluate('(node, top) => node.scrollTop = top', scroll)
            for selector in ('.workspace-header', '.project-activity-head', '.project-activity-feed'):
                with self.subTest(scroll=scroll, selector=selector):
                    result = await self.page.evaluate('''selector => {
                        const rect = document.querySelector(selector).getBoundingClientRect();
                        return kanbanGestures.canPullRefreshAt((rect.left + rect.width / 2) / innerWidth,
                                                              (rect.top + 10) / innerHeight);
                    }''', selector)
                    self.assertEqual(result, allowed)
        self.assertFalse(self.errors)

    async def test_board_preserves_reading_anchor_on_insert_and_delete(self):
        board = await self.mock_board()
        for width, height in ((1280, 800), (390, 844)):
            with self.subTest(width=width):
                await self.open_mock_board(width, height)
                await self.page.evaluate('''() => {
                    document.querySelector('.column-cards').scrollTop = 650;
                    document.querySelector('.board-main').scrollTop = 900;
                }''')
                await self.page.clock.run_for(300)
                anchor = await self.page.evaluate('''() => {
                    const view = document.querySelector('.board-main').getBoundingClientRect();
                    const body = document.querySelector('.column-cards').getBoundingClientRect();
                    const cards = Array.from(document.querySelectorAll('.column:first-child .card'));
                    window.readingCard = cards.find(card => card.getBoundingClientRect().bottom > Math.max(view.top, body.top));
                    return {id: Number(readingCard.dataset.id), top: readingCard.getBoundingClientRect().top};
                }''')
                inserted = {**board['columns'][0]['cards'][0], 'id': 99999, 'title': '新插入的卡片'}
                board['columns'][0]['cards'].insert(0, inserted)
                await self.board_event()
                self.assertTrue(await self.page.evaluate('readingCard.isConnected'))
                self.assertAlmostEqual(await self.page.evaluate('readingCard.getBoundingClientRect().top'), anchor['top'], delta=1)
                board['columns'][0]['cards'].remove(inserted)
                await self.board_event()
                self.assertAlmostEqual(await self.page.evaluate('readingCard.getBoundingClientRect().top'), anchor['top'], delta=1)
                # If the reading card itself disappears, anchor the next surviving card.
                next_top = await self.page.evaluate('''() => {
                    window.nextCard = readingCard.nextElementSibling;
                    return nextCard.getBoundingClientRect().top;
                }''')
                removed = next(card for card in board['columns'][0]['cards'] if card['id'] == anchor['id'])
                board['columns'][0]['cards'].remove(removed)
                await self.board_event()
                self.assertAlmostEqual(await self.page.evaluate('nextCard.getBoundingClientRect().top'), next_top, delta=1)
        self.assertFalse(self.errors)

    async def test_board_defers_changes_during_edit_selection_and_pointer_hold(self):
        board = await self.mock_board()
        await self.open_mock_board()
        title = self.page.locator('.card-title').first
        search = self.page.locator('#board-search')
        await search.fill('任务')
        await search.evaluate('(node) => node.setSelectionRange(0, 1)')
        board['columns'][0]['cards'][0]['title'] = '任务已编辑'
        await self.page.evaluate('boardStreams.at(-1).emit("change")')
        await self.page.clock.run_for(1000)
        await expect(title).to_have_text('任务 0')
        self.assertEqual(await search.evaluate('(node) => node.selectionEnd'), 1)
        await search.blur()
        await self.page.clock.run_for(1000)
        await expect(title).to_have_text('任务已编辑')
        await self.page.evaluate('''() => {
            const range = document.createRange();
            range.selectNodeContents(document.querySelector('.card-title'));
            getSelection().addRange(range);
        }''')
        board['columns'][0]['cards'][0]['title'] = '任务选择期间'
        await self.page.evaluate('boardStreams.at(-1).emit("change")')
        await self.page.clock.run_for(1000)
        await expect(title).to_have_text('任务已编辑')
        await self.page.evaluate('getSelection().removeAllRanges()')
        await self.page.clock.run_for(1000)
        await expect(title).to_have_text('任务选择期间')
        await self.page.locator('.board-head').dispatch_event('pointerdown', {'pointerId': 9})
        board['columns'][0]['cards'][0]['title'] = '任务松开后'
        await self.page.evaluate('boardStreams.at(-1).emit("change")')
        await self.page.clock.run_for(1000)
        await expect(title).to_have_text('任务选择期间')
        await self.page.locator('.board-head').dispatch_event('pointerup', {'pointerId': 9})
        await self.page.clock.run_for(1000)
        await expect(title).to_have_text('任务松开后')
        self.assertFalse(self.errors)

    async def test_board_moves_reuse_nodes_and_metadata_updates_in_place(self):
        board = await self.mock_board()
        await self.open_mock_board()
        await self.page.evaluate('''() => {
            window.movingCard = document.querySelector('.card');
            window.unchangedColumn = document.querySelectorAll('.column')[2];
        }''')
        moved = board['columns'][0]['cards'].pop(0)
        moved['column_id'] = board['columns'][1]['id']
        board['columns'][1]['cards'].append(moved)
        board['project']['name'] = '协作项目已改名'
        board['columns'][1]['name'] = '协作列表已改名'
        await self.board_event()
        await expect(self.page.locator('.board-heading h2')).to_have_text('协作项目已改名')
        await expect(self.page.locator('.column-head strong').nth(1)).to_have_text('协作列表已改名')
        self.assertTrue(await self.page.evaluate('movingCard === document.querySelector(".column:nth-child(2) .card:last-child")'))
        self.assertTrue(await self.page.evaluate('unchangedColumn === document.querySelectorAll(".column")[2]'))
        board['labels'] = [
            {'id': 1, 'name': '需求', 'color': '#D63A56'},
            {'id': 2, 'name': '缺陷', 'color': '#D63A56'},
        ]
        await self.board_event()
        options = self.page.locator('#filter-label .filter-item')
        await expect(options).to_have_text(['全部标签', '需求', '缺陷'])
        board['labels'] = [{'id': 2, 'name': '待修复', 'color': '#D63A56'}]
        await self.board_event()
        await expect(options).to_have_text(['全部标签', '待修复'])
        board['role'] = 'viewer'
        await self.board_event()
        await expect(self.page.locator('.grip, .composer, .add-column')).to_have_count(0)
        self.assertFalse(self.errors)

    async def test_creation_modal_preserves_draft_and_defers_remote_column_updates(self):
        board = await self.mock_board()
        await self.open_mock_board()
        await self.page.locator('.column:nth-child(2) [data-act=compose]').first.click()
        draft = self.page.locator('[data-form=card] input[name=title]')
        await draft.fill('尚未提交的任务')
        await draft.blur()
        board['columns'].pop(1)
        await self.page.evaluate('boardStreams.at(-1).emit("change")')
        await self.page.clock.run_for(1000)
        await expect(draft).to_have_value('尚未提交的任务')
        await expect(self.page.locator('[data-form=card] select[name=column_id]')).to_have_value('2')
        await expect(self.page.locator('.column')).to_have_count(6)
        await self.page.keyboard.press('Escape')
        await self.page.clock.run_for(1000)
        await expect(self.page.locator('.column')).to_have_count(5)
        await self.page.locator('[data-act=compose]').first.click()
        await expect(draft).to_have_value('')
        await expect(self.page.locator('[data-form=card] select[name=column_id] option')).to_have_count(5)
        self.assertFalse(self.errors)

    async def test_deleted_selected_label_clears_filter_and_restores_cards(self):
        board = await self.mock_board()
        board['labels'] = [{'id': 1, 'name': '待删除标签', 'color': '#D63A56'}]
        board['columns'][0]['cards'][0]['label_ids'] = [1]
        await self.open_mock_board()
        await self.page.locator('#filter-label').click()
        await self.page.locator('#filter-label [data-value="1"]').click()
        await expect(self.page.locator('.card')).to_have_count(1)
        board['labels'] = []
        board['columns'][0]['cards'][0]['label_ids'] = []
        await self.board_event()
        await expect(self.page.locator('#filter-label .filter-trigger-text')).to_have_text('全部标签')
        await expect(self.page.locator('#filter-label [data-value=""]')).to_have_attribute('aria-selected', 'true')
        await expect(self.page.locator('.card')).to_have_count(240)
        await expect(self.page.locator('[data-filter-lock]')).to_be_hidden()
        self.assertFalse(self.errors)

    async def test_failed_card_load_releases_sync_without_an_invisible_drawer(self):
        board = await self.mock_board()
        await self.open_mock_board()
        for status in (404, 503):
            with self.subTest(status=status):
                async def unavailable(route):
                    await route.fulfill(status=status, json={'detail': '卡片暂时不可访问'})
                await self.page.route('**/api/cards/100', unavailable)
                await self.page.locator('.card').first.click()
                await expect(self.page.locator('.toast').last).to_have_text('卡片暂时不可访问')
                await expect(self.page.locator('#drawer')).to_be_hidden()
                board['columns'][0]['cards'][1]['title'] = f'加载失败后继续同步 {status}'
                await self.board_event()
                await expect(self.page.locator('.card-title').nth(1)).to_have_text(f'加载失败后继续同步 {status}')
                await self.page.unroute('**/api/cards/100', unavailable)
        self.assertFalse(self.errors)

    async def test_notification_badges_disappear_after_reading(self):
        notes = [
            {"id": i, "type": "project_created", "status": None, "read": False,
             "title": f"通知 {i}", "body": "项目已创建", "actor": None,
             "created_at": "2026-01-01T00:00:00"}
            for i in (1, 2)
        ]
        def payload():
            return {"items": notes, "unread": sum(not note["read"] for note in notes)}
        async def notifications(route):
            path = urlsplit(route.request.url).path
            if path.endswith("/read-all"):
                for note in notes:
                    note["read"] = True
                await route.fulfill(json={"ok": True, "count": 1})
            elif path.endswith("/read"):
                note_id = int(path.split("/")[-2])
                next(note for note in notes if note["id"] == note_id)["read"] = True
                await route.fulfill(json={"ok": True})
            else:
                await route.fulfill(json=payload())
        await self.page.route("**/api/bootstrap", lambda r: r.fulfill(json={**DATA, "unread": payload()["unread"]}))
        await self.page.route("**/api/notifications{,/**}", notifications)
        await self.page.goto(self.url)
        header_badge = self.page.locator(".workspace-tools [data-badge]")
        await expect(header_badge).to_have_text("2")
        await expect(header_badge).to_be_visible()
        await self.page.get_by_role("button", name="查看通知", exact=True).click()
        await self.page.locator('.note[data-id="1"]').click()
        await expect(header_badge).to_have_text("1")
        await expect(header_badge).to_be_visible()
        await self.page.get_by_role("button", name="全部已读", exact=True).click()
        await expect(self.page.locator(".note.is-unread")).to_have_count(0)
        for selector in (".workspace-tools [data-badge]", ".nav-btn [data-badge]"):
            await expect(self.page.locator(selector)).to_be_hidden()
        await self.page.set_viewport_size({"width": 390, "height": 844})
        await expect(self.page.locator(".tabbar [data-badge]")).to_be_hidden()
        await self.page.reload()
        await self.page.locator(".shell").wait_for()
        await expect(self.page.locator(".workspace-tools [data-badge]")).to_be_hidden()
        self.assertFalse(self.errors)


if __name__ == '__main__':
    unittest.main(verbosity=2)
