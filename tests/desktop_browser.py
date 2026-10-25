"""Isolated desktop layout checks; serves fixtures without a database."""
import functools
import json
import sys
import unittest
from datetime import date, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
USER = dict(id=1, display_name='小林', email='preview@example.com', avatar_id='female-1')
MEMBERS = [
    {**USER, 'role': 'owner'},
    dict(id=2, display_name='陈晨', email='chen@example.com', avatar_id='male-1', role='admin'),
    dict(id=3, display_name='阿雅', email='aya@example.com', avatar_id='female-2', role='member'),
]
PREVIEW_MEMBERS = MEMBERS + [
    dict(id=i+4, display_name=name, avatar_id=avatar)
    for i, (name, avatar) in enumerate([
        ('小夏', 'female-3'), ('阿杰', 'male-2'), ('小宇', 'male-3'),
        ('小鹿', 'pet-1'), ('小白', 'robot-1'),
    ])
]
PROJECT_NAMES = ['品牌设计与春季发布', '产品研发', '内容运营', '增长计划', '客户支持', '活动筹备', '团队协作', '资料归档']
COLORS = ['#D63A56', '#3D6B8A', '#5C6B52', '#C47B2B', '#7A5EA8', '#C46B4A', '#2F6F6A', '#8A4B5A']
COLUMN_NAMES = ['待办', '进行中', '待验收', '已完成']
PROJECTS = [
    dict(id=i+1, name=name, description='从想法到落地，让每一步协作清晰可见。',
         color=color, archived=False, open_cards=12, member_count=[8, 1, 5][i % 3],
         member_preview=PREVIEW_MEMBERS[:min(5, [8, 1, 5][i % 3])], role='owner')
    for i, (name, color) in enumerate(zip(PROJECT_NAMES, COLORS))
]
QUOTA = dict(used=8, remaining=22, limit=30)
ACTIVITY = [
    dict(id=i, user=MEMBERS[[0, 0, 0, 0, 0, 0, 1, 2][i]], action='comment.added' if i in (2, 3) else 'card.updated',
         detail={'title': '首页视觉与交互方案', 'body': '首页方案已确认。\n请补充移动端效果，<script>保留为文字</script>。'}, created_at='2026-10-25T08:00:00Z')
    for i in range(8)
]
CARD_TITLES = [
    '梳理本次发布的设计方向与完整交付范围', '完成首页视觉方案', '整理设计规范与组件状态',
    '准备品牌素材与文案', '完成用户访谈记录', '发布上一版产品说明', '补充移动端交互原型', '校对上线文案',
]
CARDS = [
    dict(
        id=i+1, title=title,
        description='## 目标\n让项目的信息层级更清晰，让团队协作更高效。\n\n- 确认交互方案\n- 整理设计规范\n- 完成多尺寸验收',
        column_id=i % 4+1, priority=['high', 'medium', 'none'][i % 3],
        due_on=(date.today()+timedelta(days=[-2, 0, 3, 0, -1, 4, 0, 2][i])).isoformat() if i != 6 else None,
        done=i in (4, 5, 7), archived=False, can_edit=True,
        assignee_ids=[1, 3], responsible_user_id=2, label_ids=[1],
        checklist={'done': 1, 'total': 3}, comment_count=2, attachment_count=1,
        project_id=i % 3+1, project_name=PROJECTS[i % 3]['name'],
        project_color=PROJECTS[i % 3]['color'], column_name=COLUMN_NAMES[i % 4],
    )
    for i, title in enumerate(CARD_TITLES)
]
NOTES = [
    dict(
        id=i+1, type='project_invite' if i == 0 else 'mention',
        status='pending' if i == 0 else 'info', read=i > 2, actor=MEMBERS[i % 3],
        title='邀请你加入「产品研发」' if i == 0 else '在卡片「首页视觉与交互方案」中提到了你',
        body='一起推进本次产品发布，确认交付范围、页面信息层级和设计验收标准。',
        created_at='2026-10-25T08:00:00Z',
    )
    for i in range(7)
]


def card_detail(card):
    return dict(
        card=card,
        checklists=[dict(id=1, title='验收清单', items=[
            dict(id=i+1, text=text, done=i == 0)
            for i, text in enumerate(['明确页面信息层级', '检查桌面与移动端布局', '完成交互验收'])
        ])],
        attachments=[
            dict(id=1, filename='设计说明.pdf', size=20480, image=False),
            dict(id=2, filename='角色形象参考与设计说明.webp', size=81920, image=True),
            dict(id=3, filename='备选角色形象.webp', size=65536, image=True),
        ],
        comments=[dict(
            id=i+1, user=MEMBERS[i], created_at='2026-10-25T08:00:00Z',
            edited=False, mine=i == 0, body='方案已同步，请确认页面的阅读顺序与操作位置。',
        ) for i in range(2)],
        activity=ACTIVITY,
    )


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path = urlsplit(self.path).path
        if path in ('/api/attachments/2/file', '/api/attachments/3/file'):
            self.path = '/static/avatars/' + ('female-1.webp' if '/2/' in path else 'robot-1.webp')
            return super().do_GET()
        if not path.startswith('/api/'):
            if path == '/':
                self.path = '/static/index.html'
            return super().do_GET()
        if path == '/api/bootstrap':
            data = dict(user=USER, projects=PROJECTS, unread=3, quota=QUOTA)
        elif path == '/api/projects':
            data = dict(projects=PROJECTS, quota=QUOTA)
        elif path == '/api/me/cards':
            data = dict(cards=CARDS)
        elif path == '/api/notifications':
            data = dict(items=NOTES, unread=3)
        elif path == '/api/auth/tokens':
            data = dict(items=[dict(id=1, name='设计协作助手', expires_at=None)])
        elif path.startswith('/api/projects/'):
            project = PROJECTS[int(path.split('/')[3])-1]
            if path.endswith('/events'):
                self.send_response(204)
                self.end_headers()
                return
            if path.endswith('/activity'):
                data = dict(items=ACTIVITY)
            elif path.endswith('/board'):
                data = dict(
                    project=project, role='owner', members=MEMBERS,
                    labels=[dict(id=1, name='设计', color='#7A5EA8')],
                    columns=[dict(
                        id=i+1, name=name, color=COLORS[i], wip_limit=None,
                        cards=[card for card in CARDS if card['column_id'] == i+1],
                    ) for i, name in enumerate(COLUMN_NAMES)],
                )
            else:
                data = dict(project=project, role='owner', members=MEMBERS, invites=[dict(id=1, display_name='王小明', email='wang@example.com')])
        elif path.startswith('/api/cards/'):
            card = CARDS[int(path.split('/')[3])-1]
            data = card_detail(card)
        else:
            self.send_error(404)
            return
        payload = json.dumps(data).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_):
        pass


class DesktopTests(unittest.IsolatedAsyncioTestCase):
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
        self.browser = await self.pw.chromium.launch(headless=True)
        self.page = await self.browser.new_page(viewport={'width': 1920, 'height': 1080}, reduced_motion='reduce')
        self.page.set_default_timeout(5000)
        self.page.set_default_navigation_timeout(10000)
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        await self.page.route('https://fonts.googleapis.com/**', lambda r: r.abort())
        await self.page.route('https://fonts.gstatic.com/**', lambda r: r.abort())

    async def asyncTearDown(self):
        await self.browser.close()
        await self.pw.stop()

    async def visit(self, route, selector):
        # A fresh document also resets authentication and drawer state between cases.
        self.visit_id = getattr(self, 'visit_id', 0) + 1
        await self.page.goto(f'{self.url}/?layout={self.visit_id}#/{route}')
        await self.page.locator(selector).first.wait_for()

    async def test_pages_keep_readable_width_and_controls_in_bounds(self):
        pages = [('projects', '.projects-page', 1440), ('tasks', '.tasks-page', 1160), ('notifications', '.notes-page', 960), ('settings/1', '.settings-grid', 1180), ('account', '.account-page', 1080)]
        for width in (320, 390, 768, 901, 1024, 1440, 1920, 2560):
            await self.page.set_viewport_size({'width': width, 'height': 1080})
            for route, selector, limit in pages:
                with self.subTest(width=width, route=route):
                    await self.visit(route, selector)
                    bounds = await self.page.locator(selector).bounding_box()
                    self.assertLessEqual(bounds['width'], limit + 1)
                    self.assertLessEqual(bounds['x'] + bounds['width'], width + 1)
                    overflow = await self.page.locator(selector).evaluate('''node => [...node.querySelectorAll('input, select, textarea, button')].filter(el => {
                        const r = el.getBoundingClientRect();
                        return r.width && (r.left < 0 || r.right > innerWidth + 1);
                    }).map(el => el.outerHTML.slice(0, 160))''')
                    self.assertEqual(overflow, [])
                    self.assertTrue(await self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        self.assertFalse(self.errors)

    async def test_task_groups_include_every_card_once_and_open_completed_cards(self):
        await self.visit('tasks', '.tasks-page')
        ids = await self.page.locator('.task').evaluate_all('nodes => nodes.map(n => Number(n.dataset.id))')
        self.assertCountEqual(ids, [card['id'] for card in CARDS])
        self.assertEqual(await self.page.locator('.tasks-completed .task').count(), 3)
        self.assertEqual(await self.page.locator('.task-group:not(.tasks-completed) .task.is-done').count(), 0)
        self.assertIn('未设日期', await self.page.locator('.task[data-id="7"]').inner_text())
        await self.page.locator('.tasks-completed summary').click()
        self.assertEqual(await self.page.locator('.tasks-completed .is-over').count(), 0)
        await self.page.locator('.task[data-id="5"]').click()
        await self.page.locator('.drawer-title').wait_for()
        self.assertEqual(await self.page.locator('.drawer-title').input_value(), CARDS[4]['title'])
        self.assertFalse(self.errors)

    async def test_project_cards_show_member_avatars_and_overflow_count(self):
        await self.visit('projects', '.project-card')
        cards = self.page.locator('.project-card')
        for index, count, overflow in [(0, 5, '+3'), (1, 1, None), (2, 5, None)]:
            card = cards.nth(index)
            self.assertEqual(await card.locator('.project-members img').count(), count)
            images = await card.locator('.project-members img').evaluate_all(
                'nodes => nodes.map(n => ({src: n.getAttribute("src"), alt: n.alt}))'
            )
            self.assertTrue(all(image['alt'] and image['src'].startswith('/static/avatars/') for image in images))
            if overflow:
                self.assertEqual(await card.locator('.project-members-more').inner_text(), overflow)
            else:
                self.assertEqual(await card.locator('.project-members-more').count(), 0)
            self.assertNotRegex(await card.locator('.project-foot').inner_text(), r'\d+ 人')
        await cards.first.locator('.project-members img').first.click()
        await self.page.locator('.board-page').wait_for()
        self.assertFalse(self.errors)

    async def test_notification_heading_updates_after_reading_without_moving_list(self):
        await self.page.route('**/api/notifications/1/read', lambda route: route.fulfill(json={'ok': True}))
        await self.visit('notifications', '.notes-page')
        note = self.page.locator('.note').first
        position = await note.bounding_box()
        await note.locator('.note-content').click()
        await self.page.wait_for_function('document.querySelector("[data-unread-count]").textContent === "2 条未读"')
        self.assertNotIn('is-unread', await note.get_attribute('class'))
        self.assertEqual((await note.bounding_box())['y'], position['y'])
        self.assertFalse(self.errors)

    async def test_notifications_open_card_project_and_keep_invite_actions_separate(self):
        notes = [
            {**NOTES[1], 'id': 2, 'project_id': 1, 'card_id': 1},
            {**NOTES[3], 'id': 4, 'project_id': 1, 'card_id': 1},
            {**NOTES[4], 'id': 5, 'project_id': 2, 'card_id': None},
            {**NOTES[0], 'project_id': 2, 'card_id': None},
        ]
        await self.page.route('**/api/notifications', lambda route: route.fulfill(json={'items': notes, 'unread': 2}))
        reads = []
        async def read(route):
            reads.append(route.request.url)
            await route.fulfill(json={'ok': True})
        await self.page.route('**/api/notifications/*/read', read)
        for index in (0, 1):
            await self.visit('notifications', '.note')
            button = self.page.locator('.note-content').nth(index)
            await button.focus()
            await button.press('Enter')
            await self.page.locator('.drawer-title').wait_for()
            self.assertTrue(self.page.url.endswith('#/board/1'))
            self.assertEqual(await self.page.locator('.drawer-title').input_value(), CARDS[0]['title'])
        self.assertEqual(len(reads), 1)
        await self.visit('notifications', '.note')
        await self.page.locator('.note-content').nth(2).click()
        await self.page.locator('.board-page').wait_for()
        self.assertTrue(self.page.url.endswith('#/board/2'))
        await self.visit('notifications', '.note')
        await self.page.locator('.note-content').last.click()
        await self.page.get_by_text('请先接受邀请，再进入项目', exact=True).wait_for()
        self.assertTrue(self.page.url.endswith('#/notifications'))
        accepted = []
        async def accept(route):
            accepted.append(route.request.url)
            await route.fulfill(json={'ok': True, 'project_id': 2})
        await self.page.route('**/api/notifications/1/accept', accept)
        await self.page.locator('[data-act=accept]').click()
        await self.page.get_by_text('已加入项目', exact=True).wait_for()
        self.assertEqual(len(accepted), 1)
        self.assertEqual(len(reads), 2)
        self.assertFalse(self.errors)

    async def test_project_activity_groups_keep_comments_separate_and_expansion_on_filter(self):
        await self.visit('board/1', '.project-activity .activity-group')
        panel = self.page.locator('.project-activity')
        self.assertEqual(await panel.locator('.activity-group').count(), 2)
        self.assertEqual(await panel.locator('.activity-comment').count(), 2)
        self.assertEqual(await panel.locator('.activity-group .activity-comment').count(), 0)
        self.assertIn('请补充移动端效果', await panel.locator('.activity-comment-body').first.inner_text())
        self.assertEqual(await panel.locator('.activity-comment-body script').count(), 0)
        self.assertFalse(await panel.locator('.activity-group').first.evaluate('node => node.open'))
        await panel.locator('.activity-group summary').first.click()
        await self.page.locator('[data-act=filter][data-key=mine]').click()
        self.assertTrue(await panel.locator('.activity-group').first.evaluate('node => node.open'))
        board = await self.page.locator('.board-canvas').bounding_box()
        activity = await panel.bounding_box()
        self.assertGreater(activity['x'], board['x'] + board['width'])
        for width in (901, 1024, 1200, 1440, 1920):
            await self.page.set_viewport_size({'width': width, 'height': 900})
            board = await self.page.locator('.board-canvas').bounding_box()
            activity = await panel.bounding_box()
            self.assertGreater(activity['x'], board['x'] + board['width'])
            self.assertAlmostEqual(activity['y'], board['y'], delta=2)
            self.assertLessEqual((await self.page.locator('.board-head').bounding_box())['height'], 64)
            self.assertTrue(await self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        await self.page.set_viewport_size({'width': 390, 'height': 844})
        await panel.scroll_into_view_if_needed()
        self.assertLessEqual(await panel.evaluate('node => node.scrollWidth - node.clientWidth'), 1)
        self.assertTrue(await self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        self.assertFalse(self.errors)

    async def test_attachment_previews_open_original_without_leaving_card(self):
        await self.visit('board/1', '.card')
        await self.page.locator('.card').first.click()
        preview = self.page.locator('.attachment-preview').first
        await preview.scroll_into_view_if_needed()
        await self.page.wait_for_function('document.querySelector(".attachment-preview img").naturalWidth > 0')
        self.assertEqual(await self.page.locator('.attachment-preview').count(), 2)
        self.assertEqual(await preview.locator('img').evaluate('node => getComputedStyle(node).objectFit'), 'contain')
        self.assertGreater((await preview.bounding_box())['height'], 150)
        async with self.page.expect_popup() as opened:
            await preview.click()
        original = await opened.value
        await original.wait_for_load_state()
        self.assertTrue(original.url.endswith('/api/attachments/2/file'))
        await original.close()
        self.assertTrue(await self.page.locator('.drawer-panel').is_visible())
        self.assertEqual(await self.page.locator('.attachment-files a').get_attribute('download'), '设计说明.pdf')
        await self.page.route('**/api/attachments/2/file', lambda route: route.fulfill(status=404, body='missing'))
        await self.visit('board/1', '.card')
        await self.page.locator('.card').first.click()
        await self.page.locator('.attachment-preview').first.scroll_into_view_if_needed()
        await self.page.locator('.attachment-fallback').wait_for()
        self.assertEqual(await self.page.locator('.attachment-preview').first.get_attribute('href'), '/api/attachments/2/file')
        self.assertFalse(self.errors)

    async def test_drawer_work_area_and_save_preserve_reading_position(self):
        await self.visit('board/1', '.card')
        await self.page.locator('.card').first.click()
        await self.page.locator('.drawer-title').wait_for()
        main = await self.page.locator('.drawer-content').bounding_box()
        side = await self.page.locator('.drawer-side').bounding_box()
        self.assertGreater(main['width'], side['width'] * 1.5)
        self.assertEqual(await self.page.locator('.drawer-content .checklist').count(), 1)
        self.assertEqual(await self.page.locator('.drawer-content .comment').count(), 2)
        self.assertEqual(await self.page.locator('.drawer-side .props').count(), 1)
        detail = await self.page.request.get(f'{self.url}/api/cards/1')
        detail = await detail.json()
        saves = []
        async def save(route):
            body = route.request.post_data_json
            saves.append(body)
            detail['card'].update(body)
            await route.fulfill(json=detail)
        await self.page.route('**/api/cards/1', save)
        await self.page.locator('.drawer-title').fill('适用于宽屏与窄屏的完整卡片标题' * 5)
        await self.page.locator('.drawer-title').blur()
        await self.page.wait_for_function('document.querySelector(".drawer-title").value.length > 50')
        await self.page.locator('.drawer-content').evaluate('node => node.scrollTop = 300')
        before = await self.page.locator('.drawer-content').evaluate('node => node.scrollTop')
        async with self.page.expect_response(lambda r: r.url.endswith('/api/cards/1') and r.request.method == 'PATCH'):
            await self.page.locator('[data-act=priority][data-value=urgent]').click()
        await self.page.wait_for_function('document.querySelector("[data-act=priority][data-value=urgent]").classList.contains("is-on")')
        self.assertAlmostEqual(await self.page.locator('.drawer-content').evaluate('node => node.scrollTop'), before, delta=1)
        title = await self.page.locator('.drawer-title').evaluate('node => ({width: node.clientWidth, scroll: node.scrollWidth, height: node.clientHeight})')
        self.assertLessEqual(title['scroll'], title['width'] + 1)
        self.assertGreater(title['height'], 50)
        self.assertTrue(any('title' in body for body in saves))
        await self.page.keyboard.press('Escape')
        self.assertFalse(await self.page.locator('.drawer-panel').is_visible())
        self.assertFalse(self.errors)

    async def test_create_task_form_submits_details_and_keeps_failed_draft(self):
        await self.visit('board/1', '.column')
        await self.page.locator('.column').nth(1).locator('.add-card').click()
        form = self.page.locator('[data-form=card]')
        self.assertEqual(await form.locator('[name=column_id]').input_value(), '2')
        await form.locator('[name=title]').fill('完成首页设计')
        await form.locator('[name=description]').fill('需要完成移动端验收')
        await form.locator('[name=responsible_user_id]').select_option('2')
        await form.locator('[name=due_on]').fill('2026-12-01')
        sent = []
        async def create(route):
            sent.append(route.request.post_data_json)
            if len(sent) == 1:
                await route.fulfill(status=400, json={'detail': '请重试'})
            else:
                await route.fulfill(json={'id': 100})
        await self.page.route('**/api/projects/1/cards', create)
        await form.locator('[type=submit]').click()
        await self.page.get_by_text('请重试', exact=True).wait_for()
        self.assertEqual(await form.locator('[name=description]').input_value(), '需要完成移动端验收')
        await form.locator('[type=submit]').click()
        await form.wait_for(state='hidden')
        self.assertEqual(sent[-1], dict(column_id=2, title='完成首页设计', description='需要完成移动端验收', responsible_user_id=2, due_on='2026-12-01'))
        for width in (320, 390, 1440):
            await self.page.set_viewport_size({'width': width, 'height': 640})
            await self.page.locator('.add-card').first.click()
            await form.locator('[type=submit]').scroll_into_view_if_needed()
            bounds = await form.bounding_box()
            self.assertGreaterEqual(bounds['x'], 0)
            self.assertLessEqual(bounds['x'] + bounds['width'], width)
            self.assertLessEqual(bounds['y'] + bounds['height'], 640)
            await self.page.keyboard.press('Escape')
        self.assertFalse(self.errors)

    async def test_column_overflow_cue_tracks_scroll_filter_and_resize(self):
        await self.page.set_viewport_size({'width': 1440, 'height': 600})
        await self.visit('board/1', '.column-cards')
        body = self.page.locator('.column-cards').first
        cue = self.page.locator('.column-scroll').first
        await self.page.wait_for_function('document.querySelector(".column-scroll").classList.contains("has-more")')
        self.assertEqual(await body.evaluate('n => getComputedStyle(n).scrollbarWidth'), 'none')
        self.assertEqual(await cue.evaluate('n => getComputedStyle(n, "::after").pointerEvents'), 'none')
        await body.evaluate('n => n.scrollTop = n.scrollHeight')
        await self.page.wait_for_function('!document.querySelector(".column-scroll").classList.contains("has-more")')
        await body.evaluate('n => n.scrollTop = 0')
        await self.page.wait_for_function('document.querySelector(".column-scroll").classList.contains("has-more")')
        await self.page.set_viewport_size({'width': 1440, 'height': 1600})
        await self.page.wait_for_function('!document.querySelector(".column-scroll").classList.contains("has-more")')
        await self.page.set_viewport_size({'width': 1440, 'height': 600})
        await self.page.wait_for_function('document.querySelector(".column-scroll").classList.contains("has-more")')
        await self.page.locator('#board-search').fill('no-matching-card')
        await self.page.wait_for_function('!document.querySelector(".column-scroll").classList.contains("has-more")')
        self.assertFalse(self.errors)

    async def test_board_columns_expand_without_losing_scroll_access(self):
        for width in (1440, 1920, 2560):
            await self.page.set_viewport_size({'width': width, 'height': 900})
            await self.visit('board/1', '.column')
            col = await self.page.locator('.column').first.bounding_box()
            self.assertGreaterEqual(col['width'], 260)
            self.assertLessEqual(col['width'], 400)
            if width >= 1920:
                self.assertGreater(col['width'], 300)
            await self.page.locator('.add-column').scroll_into_view_if_needed()
            self.assertTrue(await self.page.locator('.add-column').is_visible())
            self.assertTrue(await self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        self.assertFalse(self.errors)

    async def test_drawer_keeps_all_work_sections_accessible_on_narrow_screens(self):
        for width in (320, 390, 768, 901):
            await self.page.set_viewport_size({'width': width, 'height': 900})
            await self.visit('board/1', '.card')
            await self.page.locator('.card').first.click()
            await self.page.locator('.drawer-title').wait_for()
            panel = self.page.locator('.drawer-panel')
            overflow = await panel.evaluate('node => node.scrollWidth - node.clientWidth')
            self.assertLessEqual(overflow, 1)
            await self.page.locator('[data-form=comment] button').scroll_into_view_if_needed()
            button = await self.page.locator('[data-form=comment] button').bounding_box()
            self.assertGreaterEqual(button['y'], 0)
            self.assertLessEqual(button['y'] + button['height'], 900)
            await self.page.locator('[data-act=close-drawer].icon-btn').click()
            self.assertFalse(await panel.is_visible())
        self.assertFalse(self.errors)

    async def test_auth_and_dialogs_fit_short_desktop_and_mobile(self):
        await self.page.route('**/api/bootstrap', lambda route: route.fulfill(status=401, json={'detail': '请先登录'}))
        for width, height in ((1920, 1080), (1440, 768), (320, 640)):
            await self.page.set_viewport_size({'width': width, 'height': height})
            await self.page.goto(self.url)
            await self.page.locator('.auth-card').wait_for()
            await self.page.get_by_role('button', name='注册', exact=True).click()
            await self.page.locator('.auth-card button[type=submit]').scroll_into_view_if_needed()
            bounds = await self.page.locator('.auth-card').bounding_box()
            self.assertGreaterEqual(bounds['x'], 0)
            self.assertGreaterEqual(bounds['y'], 0)
            self.assertLessEqual(bounds['x'] + bounds['width'], width)
            self.assertLessEqual(bounds['y'] + bounds['height'], height)
        await self.page.unroute('**/api/bootstrap')
        await self.page.set_viewport_size({'width': 1920, 'height': 1080})
        await self.visit('projects', '.projects-page')
        await self.page.locator('[data-act=new-project]').click()
        box = await self.page.locator('.modal-card').bounding_box()
        self.assertLessEqual(box['width'], 500)
        await self.page.keyboard.press('Escape')
        self.assertFalse(await self.page.locator('.modal-card').is_visible())
        self.assertFalse(self.errors)


if __name__ == '__main__':
    if '--preview' in sys.argv:
        ThreadingHTTPServer(('127.0.0.1', 18765), functools.partial(Handler, directory=str(ROOT))).serve_forever()
    else:
        unittest.main()
