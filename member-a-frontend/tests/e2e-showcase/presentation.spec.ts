import { test, expect, login } from '../e2e/helpers';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
async function capture(page: import('@playwright/test').Page, name: string) {
  const dir = resolve('docs/testing/frontend/screenshots/showcase');
  await page.evaluate(() => window.scrollTo(0, 0));
  await mkdir(dir, { recursive: true });
  await page.screenshot({
    path: resolve(
      dir,
      `${name}-${page.viewportSize()!.width}x${page.viewportSize()!.height}.png`,
    ),
    fullPage: true,
  });
}
test('默认展示环境没有开发控制、演示口令、内部ID与英文运行状态', async ({
  page,
}) => {
  await page.goto('/login');
  await expect(page.getByLabel('账号', { exact: true })).toBeVisible();
  await expect(
    page.getByText('演示环境 · 示例数据', { exact: true }),
  ).toBeVisible();
  expect(await page.evaluate(() => window.__LEARNMATE_DEMO__)).toBeUndefined();
  await expect(page.locator('body')).not.toContainText('Demo123!');
  await expect(page.getByRole('button', { name: /场景控制/ })).toHaveCount(0);
  await capture(page, 'login');
  await login(page);
  await page.goto('/reports/report-a-001');
  await expect(page.getByTestId('percentage')).toContainText('54.17');
  await page.locator('.evidence summary').first().click();
  const body = await page.locator('body').innerText();
  expect(body).not.toMatch(
    /attempt-a-001|mock-rule-v1|mock-report-v1|chunk-|document_id|服务执行摘要|来源状态：available|场景控制|后端报告/,
  );
  expect(body).toContain('示例数据报告');
  expect(body).toContain('来源可访问');
  await capture(page, 'report');
  await page.goto('/reports');
  await expect(page.locator('table')).toBeVisible();
  await expect(page.locator('table')).not.toContainText('attempt-a-');
});
test('展示环境教师资料中文状态、错误字段本地化、表单停用也需确认', async ({
  page,
}) => {
  await login(page, 'teacher');
  await page.goto('/teacher/resources');
  await expect(page.locator('table')).toBeVisible();
  const body = await page.locator('table').innerText();
  expect(body).not.toMatch(/available|processing|removed|\bnote\b|\beasy\b/);
  expect(body).toContain('文本资料');
  await page
    .getByRole('row')
    .filter({ hasText: '顺序表与复杂度 · 概念笔记' })
    .getByRole('button', { name: '编辑', exact: true })
    .click();
  await expect(
    page.getByRole('dialog', { name: '编辑学习资源', exact: true }),
  ).toBeVisible();
  await page.getByText('启用资源', { exact: true }).click();
  await expect(
    page.getByRole('checkbox', { name: '启用资源' }),
  ).not.toBeChecked();
  await page.getByRole('button', { name: '保存资源', exact: true }).click();
  await expect(
    page.getByRole('dialog', { name: '确认停用', exact: true }),
  ).toBeVisible();
  await page
    .getByRole('dialog', { name: '确认停用', exact: true })
    .getByRole('button', { name: '取消', exact: true })
    .click();
  await expect(
    page.getByRole('dialog', { name: '编辑学习资源', exact: true }),
  ).toBeVisible();
  await page
    .getByRole('dialog', { name: '编辑学习资源', exact: true })
    .getByRole('button', { name: '取消', exact: true })
    .click();
  await page.getByRole('button', { name: '新建学习资源' }).click();
  await page.getByRole('button', { name: '保存资源', exact: true }).click();
  const alert = page.getByRole('alert');
  await expect(alert).toContainText('标题');
  await expect(alert).not.toContainText('course_id');
  await expect(alert).not.toContainText('Too small');
  await capture(page, 'teacher-validation');
});
test('教师学生记录支持分页且切换后无旧数据残留', async ({ page }) => {
  await login(page, 'teacher');
  // Test-only seed: valid copies exercise page 7, beyond the previous 50-record limit.
  await page.evaluate(async () => {
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open('learning-diagnosis-demo-v1', 1);
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction('demo-state', 'readwrite'),
        store = tx.objectStore('demo-state'),
        read = store.get('state');
      read.onsuccess = () => {
        const state = read.result;
        for (let i = 0; i < 55; i++) {
          const entry = structuredClone(state.attempts['attempt-a-001']);
          const aid = `audit-page-${i}`,
            rid = `audit-report-${i}`,
            tid = `audit-task-${i}`;
          const submitted = new Date(Date.UTC(2026, 8, i + 1)).toISOString();
          Object.assign(entry.value, {
            attempt_id: aid,
            report_id: rid,
            diagnosis_task_id: tid,
            created_at: submitted,
            submitted_at: submitted,
          });
          entry.value.result.attempt_id = aid;
          state.attempts[aid] = entry;
          state.reports[rid] = {
            ...structuredClone(state.reports['report-a-001']),
            report_id: rid,
            attempt_id: aid,
            generated_at: submitted,
          };
          state.tasks[tid] = {
            ...structuredClone(state.tasks['task-a-001']),
            task_id: tid,
            attempt_id: aid,
            report_id: rid,
            created_at: submitted,
            updated_at: submitted,
          };
        }
        store.put(state, 'state');
      };
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    db.close();
  });
  await page
    .getByRole('row')
    .filter({ hasText: '学生甲' })
    .getByRole('button', { name: '查看全部记录' })
    .click();
  const dialog = page.getByRole('dialog', { name: '学生测验记录' });
  await expect(dialog.getByRole('link', { name: '查看报告' })).toHaveCount(10);
  await dialog.locator('.el-pager li').filter({ hasText: /^7$/ }).click();
  await expect(dialog.getByRole('link', { name: '查看报告' })).toHaveCount(1);
  await dialog.getByRole('button', { name: '关闭此对话框' }).click();
  await page
    .getByRole('row')
    .filter({ hasText: '学生乙' })
    .getByRole('button', { name: '查看全部记录' })
    .click();
  await expect(dialog.getByRole('link', { name: '查看报告' })).toHaveCount(4);
  expect(
    await dialog
      .getByRole('link', { name: '查看报告' })
      .first()
      .getAttribute('href'),
  ).toContain('/student-b/');
});
