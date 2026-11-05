import { test, expect, login, call, scenario, shot } from './helpers';
test('E17/E21 教师概况、授权学生报告、课程和知识点持久化', async ({ page }) => {
  await login(page, 'teacher');
  await expect(page.getByText('学生甲', { exact: true })).toBeVisible();
  await expect(page.getByText('学生乙', { exact: true })).toBeVisible();
  await page.getByRole('link', { name: '最新报告 →' }).nth(1).click();
  await expect(page).toHaveURL(/\/teacher\/students\/student-b\/reports\//);
  await expect(page.getByTestId('knowledge-table')).toBeVisible();
  await expect(
    page.getByRole('button', { name: '以本次为基准复测' }),
  ).toHaveCount(0);
  await page.goto('/teacher/course');
  await page
    .getByLabel('课程标题', { exact: true })
    .fill('数据结构基础 · 教师修订');
  await page.getByRole('button', { name: '保存课程' }).click();
  await expect(
    page.getByRole('status').filter({ hasText: '课程信息已保存' }),
  ).toBeVisible();
  await page.reload();
  await expect(page.getByLabel('课程标题', { exact: true })).toHaveValue(
    '数据结构基础 · 教师修订',
  );
  await page.goto('/teacher/knowledge-points');
  await page.getByRole('button', { name: '新增知识点' }).click();
  await page.getByLabel('知识点名称', { exact: true }).fill('综合边界复习');
  await page
    .getByLabel('知识点说明', { exact: true })
    .fill('教师维护的补充学习主题');
  await page.getByRole('button', { name: '保存知识点' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.reload();
  await expect(page.locator('table')).toContainText('综合边界复习');
  const row = page.getByRole('row').filter({ hasText: '综合边界复习' });
  await row.getByRole('button', { name: '编辑', exact: true }).click();
  await page.getByLabel('知识点说明', { exact: true }).fill('已编辑并持久化');
  await page.getByRole('button', { name: '保存知识点' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await row.getByRole('button', { name: '停用', exact: true }).click();
  await page.getByRole('button', { name: '确认停用', exact: true }).click();
  await expect(row).toContainText('停用');
});
test('E18 题目表单校验、创建编辑停用和历史快照不变', async ({ page }) => {
  await login(page, 'teacher');
  const old = await call(
    page,
    '/teacher/students/student-a/reports/report-a-001',
  );
  await page.goto('/teacher/questions');
  await shot(page, 'teacher-questions');
  await page.getByRole('button', { name: '新增题目' }).click();
  await page.getByRole('button', { name: '保存题目' }).click();
  await expect(page.getByRole('alert')).toContainText('题干');
  await page
    .getByLabel('题干', { exact: true })
    .fill('教师自编：队列最先入队的元素何时出队？');
  for (const [i, label] of ['A', 'B', 'C', 'D'].entries())
    await page
      .getByLabel(`选项 ${label} 内容`, { exact: true })
      .fill(['最先出队', '最后出队', '随机出队', '永不出队'][i]);
  await page.getByLabel('正确选项 A', { exact: true }).check();
  await page.getByLabel('正确选项 B', { exact: true }).check();
  await page
    .getByLabel('关联知识点（可多选）', { exact: true })
    .selectOption('kp-queue');
  await page.getByRole('button', { name: '保存题目' }).click();
  await expect(page.getByRole('alert')).toContainText('单选需一个答案');
  await page.getByLabel('正确选项 B', { exact: true }).uncheck();
  await page.getByRole('button', { name: '保存题目' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page
    .getByRole('combobox', { name: '知识点', exact: true })
    .selectOption('kp-queue');
  const row = page
    .getByRole('row')
    .filter({ hasText: '教师自编：队列最先入队' });
  await expect(row).toBeVisible();
  await row.getByRole('button', { name: '编辑', exact: true }).click();
  await page
    .getByLabel('题干', { exact: true })
    .fill('教师自编：队列遵循哪种顺序？');
  await page.getByRole('button', { name: '保存题目' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.reload();
  await page
    .getByRole('combobox', { name: '知识点', exact: true })
    .selectOption('kp-queue');
  const changed = page
    .getByRole('row')
    .filter({ hasText: '教师自编：队列遵循哪种顺序' });
  await expect(changed).toBeVisible();
  await changed.getByRole('button', { name: '停用', exact: true }).click();
  await page.getByRole('button', { name: '确认停用', exact: true }).click();
  await expect(changed).toContainText('停用');
  const after = await call(
    page,
    '/teacher/students/student-a/reports/report-a-001',
  );
  expect(after.body.data.score).toEqual(old.body.data.score);
});
test('E19 教师文本资源、知识点关联、刷新保存并由学生实际阅读', async ({
  page,
}) => {
  await login(page, 'teacher');
  await page.goto('/teacher/resources');
  await page.getByRole('button', { name: '新建学习资源' }).click();
  await page
    .getByLabel('资源标题', { exact: true })
    .fill('教师自编队列边界笔记');
  await page
    .getByLabel('资料正文', { exact: true })
    .fill('# 空队列检查\n出队前应检查队列是否为空，不能读取不存在的队头。');
  await page.getByLabel('关联知识点', { exact: true }).selectOption('kp-queue');
  await page.getByRole('button', { name: '保存资源' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page
    .getByRole('combobox', { name: '知识点', exact: true })
    .selectOption('kp-queue');
  await page.reload();
  await page
    .getByRole('combobox', { name: '知识点', exact: true })
    .selectOption('kp-queue');
  const row = page.getByRole('row').filter({ hasText: '教师自编队列边界笔记' });
  await expect(row).toBeVisible();
  const href = await row
    .getByRole('link', { name: '阅读', exact: true })
    .getAttribute('href');
  await page.getByRole('button', { name: '退出登录' }).click();
  await expect(page).toHaveURL(/\/login/);
  await login(page);
  await page.goto(href!);
  await expect(page.locator('.resource-content')).toContainText(
    '不能读取不存在的队头',
  );
});
test('E20 上传受理/完成/刷新恢复、格式超限、取消和解析失败', async ({
  page,
}) => {
  await login(page, 'teacher');
  await page.goto('/teacher/resources');
  await page.getByLabel('上传资料标题', { exact: true }).fill('队列上传笔记');
  await page
    .getByLabel('上传关联知识点', { exact: true })
    .selectOption('kp-queue');
  await page.getByLabel('选择文件', { exact: true }).setInputFiles({
    name: 'note.exe',
    mimeType: 'application/octet-stream',
    buffer: Buffer.from('not-supported'),
  });
  await expect(page.getByRole('alert')).toContainText('仅支持');
  await page.getByLabel('选择文件', { exact: true }).setInputFiles({
    name: 'large.txt',
    mimeType: 'text/plain',
    buffer: Buffer.alloc(10 * 1024 * 1024 + 1),
  });
  await expect(page.getByRole('alert')).toContainText('超过');
  await page.getByLabel('选择文件', { exact: true }).setInputFiles({
    name: 'note.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('上传的自编文本：队列先进先出，空队列不可出队。'),
  });
  await page.getByRole('button', { name: '上传并处理' }).click();
  await expect(page.getByText(/文件已受理，等待处理/)).toBeVisible();
  await expect(page.getByText(/已完成 · 资料处理完成/)).toBeVisible();
  await shot(page, 'teacher-upload');
  await page.reload();
  await page
    .getByRole('combobox', { name: '资源类型', exact: true })
    .selectOption('document');
  await expect(page.locator('table')).toContainText('队列上传笔记');
  await page.getByRole('button', { name: '查看处理' }).first().click();
  await expect(page.getByText(/已完成 · 资料处理完成/)).toBeVisible();
  await scenario(page, 'upload-failed');
  await page.getByLabel('上传资料标题', { exact: true }).fill('模拟失败文件');
  await page
    .getByLabel('上传关联知识点', { exact: true })
    .selectOption('kp-linear');
  await page.getByLabel('选择文件', { exact: true }).setInputFiles({
    name: 'fail.md',
    mimeType: 'text/markdown',
    buffer: Buffer.from('原创上传内容'),
  });
  await page.getByRole('button', { name: '上传并处理' }).click();
  await expect(
    page.getByRole('button', { name: '重试资料处理' }),
  ).toBeVisible();
  await shot(page, 'upload-error');
  await page.getByRole('button', { name: '重试资料处理' }).click();
  await expect(page.getByText(/已完成 · 资料处理完成/)).toBeVisible();
  await page.evaluate(() => window.__LEARNMATE_DEMO__!.setDelay(1000));
  await page.getByRole('button', { name: '上传并处理' }).click();
  await page.getByRole('button', { name: '取消上传', exact: true }).click();
  await expect(
    page.getByRole('alert').filter({ hasText: '上传已取消' }),
  ).toBeVisible();
});
