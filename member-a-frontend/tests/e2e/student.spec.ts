import { test, expect, login, call, scenario, submit, shot } from './helpers';
test('E01/E02 登录、错误口令、深链接与安全跳转', async ({
  page,
  allowConsole,
}) => {
  allowConsole(/status of 401/);
  await page.goto('/reports/report-a-001');
  await expect(page).toHaveURL(/\/login\?redirect=/);
  await page.getByLabel('账号', { exact: true }).fill('demo_student_a');
  await page.getByLabel('密码', { exact: true }).fill('wrong');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('账号或密码错误');
  await page.getByLabel('密码', { exact: true }).fill('Demo123!');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(page).toHaveURL(/\/reports\/report-a-001$/);
  await expect(page.getByTestId('percentage')).toHaveText('54.17 / 100 分');
});
test('E03/E04/E05/E06 新测验单多选、草稿刷新、未答确认取消、幂等提交', async ({
  page,
}) => {
  await login(page);
  await page.getByRole('link', { name: /进入课程/ }).click();
  await shot(page, 'course');
  await page.getByRole('button', { name: '开始新测验' }).click();
  await expect(page).toHaveURL(/\/attempts\/attempt-/);
  const attemptPath = new URL(page.url()).pathname;
  await page.getByRole('radio').first().check();
  await page.getByTestId('question-nav-2').click();
  await page.getByRole('checkbox').nth(0).check();
  await page.getByRole('checkbox').nth(1).check();
  await page.reload();
  await page.getByTestId('question-nav-2').click();
  await expect(page.getByRole('checkbox').nth(0)).toBeChecked();
  await expect(page.getByRole('checkbox').nth(1)).toBeChecked();
  await shot(page, 'quiz');
  await page.getByRole('button', { name: '提交测验', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('已答 2 题，未答 22 题');
  await page.getByRole('button', { name: '继续作答', exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`${attemptPath}$`));
  await submit(page);
  await expect(page.getByTestId('percentage')).toHaveText('8.33 / 100 分');
  await expect(page.getByTestId('knowledge-table')).toBeVisible();
  const saved = await call(page, attemptPath);
  expect(saved.body.data.status).toBe('submitted');
  expect(saved.body.data.questions[0]).not.toHaveProperty('correct_option_ids');
  const r = saved.body.data.result;
  const duplicate = await call(
    page,
    `${attemptPath}/submit`,
    'POST',
    {
      snapshot_version: saved.body.data.snapshot_version,
      answers: r.graded_answers.map(
        (a: { question_id: string; selected_option_ids: string[] }) => ({
          question_id: a.question_id,
          selected_option_ids: a.selected_option_ids,
        }),
      ),
    },
    { 'Idempotency-Key': 'repeat-observer' },
  );
  expect(duplicate.status).toBe(200);
  expect(duplicate.body.data.diagnosis_task_id).toBe(
    saved.body.data.diagnosis_task_id,
  );
  await page.reload();
  await expect(page.getByTestId('percentage')).toHaveText('8.33 / 100 分');
  await page.goto(attemptPath);
  await expect(page).toHaveURL(/\/diagnosis$/);
  await expect(page.getByRole('radio')).toHaveCount(0);
  await shot(page, 'diagnosis');
});
test('E07 空答、提交已保存但响应丢失，查询恢复同一测验', async ({
  page,
  allowConsole,
}) => {
  allowConsole(/Failed to load resource: net::ERR_FAILED/);
  await login(page);
  await page.goto('/courses/course-ds');
  await page.getByRole('button', { name: '开始新测验' }).click();
  await expect(page).toHaveURL(/\/attempts\/attempt-/);
  const path = new URL(page.url()).pathname;
  await scenario(page, 'submit-committed-response-lost');
  await submit(page);
  await expect(page.getByTestId('percentage')).toHaveText('0 / 100 分');
  const a = await call(page, path);
  expect(a.body.data.status).toBe('submitted');
  expect(a.body.data.result.score.raw_score).toBe(0);
});
test('E08/E09/E10 固定成绩、2/2证据不足、引用展开及可读来源', async ({
  page,
}) => {
  await login(page);
  await page.goto('/reports/report-a-004');
  const table = page.getByTestId('knowledge-table');
  await expect(table).toContainText('2 / 2');
  await expect(table).toContainText('100%');
  await expect(table).toContainText('证据不足');
  await expect(table).not.toContainText('已掌握');
  await expect(page.getByRole('img', { name: /知识点掌握度/ })).toHaveCount(0);
  await shot(page, 'insufficient');
  await page.goto('/reports/report-a-001');
  await expect(page.getByTestId('percentage')).toContainText('54.17');
  await page.locator('.evidence summary').first().click();
  await expect(page.locator('blockquote').first()).toContainText('顺序表');
  await shot(page, 'evidence-expanded');
  await page.getByRole('link', { name: '查看原资料与章节 →' }).first().click();
  await expect(page.locator('.resource-content')).toContainText(
    '按下标访问为 O(1)',
  );
  await expect(page.getByText('定位章节：概念与边界')).toBeVisible();
  await page.getByRole('link', { name: '← 返回来源页面' }).click();
  await expect(page).toHaveURL(/\/reports\/report-a-001$/);
});
test('E11 推荐练习是真实作答并进入历史；E12 历史报告固定baseline复测', async ({
  page,
}) => {
  await login(page);
  await page.goto('/reports/report-a-001/recommendations');
  await shot(page, 'recommendations');
  await page
    .getByRole('button', { name: /开始推荐练习/ })
    .first()
    .click();
  await expect(
    page.getByRole('heading', { name: '推荐练习', exact: true }),
  ).toBeVisible();
  await page.getByRole('radio').nth(3).check();
  await submit(page);
  await expect(page.getByTestId('percentage')).toContainText('50');
  await page.goto('/reports');
  await expect(page.getByRole('row').nth(1)).toContainText('练习');
  await page.goto('/reports/report-a-001');
  await page.getByRole('button', { name: '以本次为基准复测' }).click();
  await expect(
    page.getByText('复测基准：attempt-a-001', { exact: true }),
  ).toBeVisible();
  await submit(page);
  await page.getByRole('link', { name: '本次完整报告' }).click();
  await expect(page.getByTestId('comparison-table')).toBeVisible();
  await expect(page.getByText(/基准 attempt-a-001 →/)).toBeVisible();
  await page.goto('/reports/report-a-002');
  await expect(page.getByTestId('percentage')).toContainText('79.17');
  await expect(
    page.getByText('总分变化：+25 个百分点', { exact: true }),
  ).toBeVisible();
  await shot(page, 'retest-comparison');
});
test('E13 无历史、无推荐、无复测、无可比点均有空态', async ({ page }) => {
  await login(page);
  await scenario(page, 'empty-history');
  await page.goto('/reports');
  await expect(page.getByText('暂无记录', { exact: true })).toBeVisible();
  await scenario(page, 'empty-recommendations');
  await page.goto('/reports/report-a-004');
  await expect(page.getByText(/当前没有匹配资源或练习/)).toBeVisible();
  await expect(page.getByText(/当前报告没有复测对比/)).toBeVisible();
  const r = await call(page, '/attempts', 'POST', {
    course_id: 'course-ds',
    kind: 'retest',
    baseline_attempt_id: 'attempt-a-004',
    source_report_id: 'report-a-004',
    client_request_id: 'insufficient-retest',
  });
  await page.goto(`/attempts/${r.body.data.attempt_id}`);
  await submit(page);
  await page.getByRole('link', { name: '本次完整报告' }).click();
  await expect(page.getByText(/整卷不可比较/)).toBeVisible();
  await expect(page.getByTestId('comparison-table')).toContainText('不可比较');
});
test('E14 检索空、模型降级保留统计；E22 失效来源保留历史片段', async ({
  page,
  allowConsole,
}) => {
  allowConsole(/status of 410/);
  await login(page);
  await scenario(page, 'retrieval-empty');
  await page.goto('/reports/report-a-001');
  await expect(page.getByText(/资料依据不足：/)).toBeVisible();
  await expect(page.getByTestId('percentage')).toContainText('54.17');
  await expect(page.locator('.evidence')).toHaveCount(0);
  await scenario(page, 'model-fallback');
  await page.reload();
  await expect(page.getByText(/智能分析暂不可用/)).toBeVisible();
  await scenario(page, 'resource-removed');
  await page.reload();
  await page.locator('.evidence summary').first().click();
  await expect(page.getByText(/来源当前已移除/).first()).toBeVisible();
  await page.getByRole('link', { name: '查看原资料与章节 →' }).first().click();
  await expect(page.getByRole('alert')).toContainText('来源已移除');
  await page.getByRole('link', { name: '← 返回来源页面' }).click();
  await expect(page.locator('.evidence')).toHaveCount(8);
});
test('E15 诊断失败保留成绩、受控重试，持续running有限停止', async ({
  page,
}) => {
  await login(page);
  await page.goto('/courses/course-ds');
  await page.getByRole('button', { name: '开始新测验' }).click();
  await scenario(page, 'diagnosis-failed');
  await submit(page);
  await expect(
    page.getByRole('button', { name: '重试诊断', exact: true }),
  ).toBeVisible();
  await expect(page.getByTestId('percentage')).toContainText('0');
  await shot(page, 'diagnosis-error');
  await page.getByRole('button', { name: '重试诊断', exact: true }).click();
  await expect(page.getByTestId('knowledge-table')).toBeVisible();
  await page.goto('/courses/course-ds');
  await page.getByRole('button', { name: '开始新测验' }).click();
  await scenario(page, 'diagnosis-stuck');
  await submit(page);
  await expect(
    page.getByText('仍在处理，已达本轮等待上限，可稍后查询。'),
  ).toBeVisible();
  await expect(page.getByTestId('percentage')).toContainText('0');
});
test('E16/E23/E24 越权、响应异常、过期、退出与账号隔离', async ({
  page,
  allowConsole,
}) => {
  allowConsole(/status of 403/);
  allowConsole(/status of 401/);
  await login(page);
  await page.goto('/teacher/questions');
  await expect(
    page.getByRole('heading', { name: '无权访问此页面' }),
  ).toBeVisible();
  expect((await call(page, '/teacher/questions')).status).toBe(403);
  expect((await call(page, '/reports/report-b-001')).status).toBe(403);
  expect((await call(page, '/attempts/attempt-b-001')).status).toBe(403);
  await scenario(page, 'invalid-response');
  await page.goto('/reports/report-a-001');
  await expect(page.getByRole('alert')).toContainText('收到的数据暂时无法展示');
  await expect(page.getByTestId('percentage')).toHaveCount(0);
  await scenario(page, 'session-expired');
  await page.goto('/reports');
  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByText('登录已过期，请重新登录。')).toBeVisible();
  await scenario(page, 'normal');
  await page.getByLabel('账号', { exact: true }).fill('demo_student_b');
  await page.getByLabel('密码', { exact: true }).fill('Demo123!');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(
    page.locator('.userbar').getByText('学生乙', { exact: false }),
  ).toBeVisible();
  await page.goto('/reports');
  await expect(page.locator('table')).not.toContainText('attempt-a-');
  await page.getByRole('button', { name: '退出登录' }).click();
  await expect(page).toHaveURL(/\/login/);
  await page.goBack();
  await expect(page).toHaveURL(/\/login/);
  await expect(page.locator('table')).toHaveCount(0);
});
test('E25 长内容在两种桌面尺寸可操作，无整页横向溢出', async ({ page }) => {
  await page.goto('/login');
  await shot(page, 'login');
  await login(page);
  await scenario(page, 'long-content');
  for (const size of [
    { width: 1366, height: 768 },
    { width: 1920, height: 1080 },
  ]) {
    await page.setViewportSize(size);
    await page.goto('/reports/report-a-001');
    await expect(page.getByTestId('knowledge-table')).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await shot(page, 'report-long');
    await page.goto('/courses/course-ds');
    await page.getByRole('button', { name: '开始新测验' }).click();
    await expect(
      page.getByRole('button', { name: '提交测验', exact: true }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await shot(page, 'quiz-long');
    await submit(page);
  }
});
