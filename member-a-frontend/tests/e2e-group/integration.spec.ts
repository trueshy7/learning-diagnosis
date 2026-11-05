import { test, expect, type Page } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
const base = '/api/v1';
test('登录页不公开口令，错误口令及网络失败不回落示例', async ({ page }) => {
  await page.goto('/#/login');
  await expect(page.locator('body')).not.toContainText('demo12345');
  await expect(page.getByLabel('密码', { exact: true })).toHaveValue('');
  await page.getByLabel('用户名').fill('student');
  await page.getByLabel('密码', { exact: true }).fill('wrong-password');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('账号或密码错误');
  await page.route('**/api/v1/auth/login', (route) =>
    route.abort('connectionrefused'),
  );
  await page.getByLabel('密码', { exact: true }).fill('demo12345');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('无法连接服务');
  await expect(
    page.getByRole('heading', { name: '选择一门课程' }),
  ).not.toBeVisible();
  expect(
    await page.evaluate(() =>
      sessionStorage.getItem('learnmate-group-session-v1'),
    ),
  ).toBeNull();
});
async function login(page: Page, user = 'student') {
  await page.goto('/#/login');
  await page.getByLabel('用户名').fill(user);
  await page.getByLabel('密码', { exact: true }).fill('demo12345');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: '选择一门课程' }),
  ).toBeVisible();
}
async function choose(page: Page, value: string) {
  const questions = page.locator('fieldset.question');
  await expect(questions).toHaveCount(6);
  for (const question of await questions.all())
    await question.locator(`input[value="${value}"]`).check();
}
test('提交中离开后，旧响应不会把用户从历史页拉回报告', async ({ page }) => {
  await login(page);
  page.on('dialog', (dialog) => dialog.accept());
  await page.getByRole('link', { name: '开始测验' }).click();
  await choose(page, 'A');
  let release!: () => void;
  let ready!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const received = new Promise<void>((resolve) => {
    ready = resolve;
  });
  await page.route('**/api/v1/attempts', async (route) => {
    if (route.request().method() !== 'POST') return route.continue();
    const response = await route.fetch();
    ready();
    await gate;
    await route.fulfill({ response });
  });
  await page.getByRole('button', { name: '提交测验', exact: true }).click();
  await received;
  await page.getByRole('link', { name: '测验历史' }).click();
  await expect(page.getByRole('heading', { name: '测验历史' })).toBeVisible();
  const handled = page.waitForResponse(
    (response) =>
      response.url().endsWith('/api/v1/attempts') &&
      response.request().method() === 'POST',
  );
  release();
  await handled;
  await page.waitForLoadState('networkidle');
  await expect(page).toHaveURL(/#\/history$/);
});
test('真实 B/C/D：计分、HTTP引用、历史与固定基线复测，退出撤销令牌', async ({
  page,
}) => {
  await login(page);
  await page.getByRole('link', { name: '开始测验' }).click();
  await choose(page, 'B');
  await page.getByRole('button', { name: '提交测验', exact: true }).click();
  await expect(page.getByRole('heading', { name: '知识点表现' })).toBeVisible();
  await expect(page.locator('.score')).toContainText('0');
  await expect(page.locator('.evidence')).not.toHaveCount(0);
  await expect(
    page.getByText('规则与模板分析 · 未调用大语言模型'),
  ).toBeVisible();
  await expect(page.locator('body')).not.toContainText('rule_template_demo');
  await expect(page.locator('body')).not.toContainText('att-');
  await page.getByRole('link', { name: '基于本次结果复测' }).click();
  await choose(page, 'A');
  await page.getByRole('button', { name: '提交测验', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: '与基线测验比较' }),
  ).toBeVisible();
  await expect(page.getByText('+100.0 个百分点')).toHaveCount(2);
  await mkdir('docs/testing/frontend/screenshots/group', { recursive: true });
  await page.screenshot({
    path: 'docs/testing/frontend/screenshots/group/real-report.png',
    fullPage: true,
  });
  await page.getByRole('link', { name: '测验历史' }).click();
  await expect(
    page.getByRole('link', { name: '查看报告' }).first(),
  ).toBeVisible();
  const token = await page.evaluate(
    () =>
      JSON.parse(sessionStorage.getItem('learnmate-group-session-v1')!)
        .access_token,
  );
  await page.getByRole('button', { name: '退出 student' }).click();
  await expect(
    page.getByRole('heading', { name: '登录学习工作台' }),
  ).toBeVisible();
  const revoked = await page.request.get(base + '/courses', {
    headers: { Authorization: 'Bearer ' + token },
  });
  expect(revoked.status()).toBe(401);
});
test('响应丢失后刷新恢复提交意图：沿用同一幂等键，只有一条真实记录', async ({
  page,
}) => {
  await login(page);
  const token = await page.evaluate(
    () =>
      JSON.parse(sessionStorage.getItem('learnmate-group-session-v1')!)
        .access_token,
  );
  const headers = { Authorization: 'Bearer ' + token };
  const before = (
    await (await page.request.get(base + '/attempts', { headers })).json()
  ).data.length;
  await page.getByRole('link', { name: '开始测验' }).click();
  await choose(page, 'A');
  const keys: string[] = [];
  await page.route('**/api/v1/attempts', async (route) => {
    if (route.request().method() !== 'POST') return route.continue();
    keys.push(route.request().headers()['idempotency-key']!);
    if (keys.length === 1) {
      await route.fetch();
      await route.abort('connectionreset');
    } else await route.continue();
  });
  await page.getByRole('button', { name: '提交测验', exact: true }).click();
  await expect(page.getByRole('button', { name: '重试提交' })).toBeVisible();
  page.on('dialog', (dialog) => dialog.accept());
  await page.reload();
  await expect(
    page.getByText('已恢复未确认提交，重试将沿用原答案和提交编号。'),
  ).toBeVisible();
  await page.getByRole('button', { name: '重试提交' }).click();
  await expect(page.getByRole('heading', { name: '知识点表现' })).toBeVisible();
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
  const after = (
    await (await page.request.get(base + '/attempts', { headers })).json()
  ).data.length;
  expect(after).toBe(before + 1);
});
test('真实成绩保留，诊断未就绪和处理中的页面可恢复', async ({ page }) => {
  await login(page);
  const token = await page.evaluate(
    () =>
      JSON.parse(sessionStorage.getItem('learnmate-group-session-v1')!)
        .access_token,
  );
  const data = (
    await (
      await page.request.post(base + '/attempts', {
        headers: { Authorization: 'Bearer ' + token },
        data: {
          course_id: 'course-ds',
          answers: ['stack', 'queue'].flatMap((kp) =>
            [1, 2, 3].map((i) => ({
              question_id: 'q-' + kp + '-' + i,
              selected_option_ids: ['A'],
            })),
          ),
        },
      })
    ).json()
  ).data;
  expect(data).toBeTruthy();
  let diagnosticStatus = 'unavailable';
  await page.route('**/api/v1/attempts/' + data.id, (route) =>
    route.fulfill({
      json: {
        code: 0,
        message: 'ok',
        request_id: 'test-unavailable',
        data: {
          ...data,
          report: null,
          ai_status: diagnosticStatus,
          ai_message: '/private/secret/path',
        },
      },
    }),
  );
  await page.goto('/#/report/' + data.id);
  await expect(
    page.getByRole('heading', { name: '诊断服务暂不可用' }),
  ).toBeVisible();
  await expect(page.locator('body')).not.toContainText('/private');
  diagnosticStatus = 'processing';
  await page.getByRole('button', { name: '刷新报告' }).click();
  await expect(page.getByRole('heading', { name: '报告准备中' })).toBeVisible();
  await page.getByRole('button', { name: '重新生成报告', exact: true }).click();
  await expect(page.getByRole('heading', { name: '知识点表现' })).toBeVisible();
});
test('真实教师文本导入；学生受保护，过期会话正确退出', async ({ page }) => {
  await login(page, 'teacher');
  await page.getByRole('link', { name: '教师工作台' }).click();
  await expect(
    page.getByRole('heading', { name: '导入课程文本' }),
  ).toBeVisible();
  await page.getByLabel('资料标题').fill('浏览器联调自编栈材料');
  await page
    .getByLabel('资料正文')
    .fill('栈是一种后进先出的线性结构，插入和删除均发生在栈顶。');
  await page.getByLabel('栈', { exact: true }).check();
  await page.getByRole('button', { name: '导入文本', exact: true }).click();
  await expect(page.getByText(/文本已导入，生成/)).toBeVisible();
  await page.screenshot({
    path: 'docs/testing/frontend/screenshots/group/teacher-import.png',
    fullPage: true,
  });
  await page.getByRole('button', { name: '退出 teacher' }).click();
  await login(page);
  const token = await page.evaluate(
    () =>
      JSON.parse(sessionStorage.getItem('learnmate-group-session-v1')!)
        .access_token,
  );
  const forbidden = await page.request.get(base + '/teacher/overview', {
    headers: { Authorization: 'Bearer ' + token },
  });
  expect(forbidden.status()).toBe(403);
  await page.goto('/#/teacher');
  await expect(
    page.getByRole('heading', { name: '选择一门课程' }),
  ).toBeVisible();
  await page.evaluate(() => {
    const key = 'learnmate-group-session-v1';
    const session = JSON.parse(sessionStorage.getItem(key)!);
    session.access_token = 'expired';
    sessionStorage.setItem(key, JSON.stringify(session));
  });
  await page.reload();
  await expect(
    page.getByRole('heading', { name: '登录学习工作台' }),
  ).toBeVisible();
  await expect(
    page.getByRole('link', { name: '教师工作台' }),
  ).not.toBeVisible();
});
