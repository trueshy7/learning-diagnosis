import { readdir, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import assert from 'node:assert/strict';
async function list(dir) {
  return (
    await Promise.all(
      (await readdir(dir, { withFileTypes: true })).map((x) =>
        x.isDirectory() ? list(join(dir, x.name)) : join(dir, x.name),
      ),
    )
  ).flat();
}
const files = await list('dist/group');
for (const file of files) {
  assert(
    !file.includes('mockServiceWorker'),
    '真实组接口产物不可包含模拟 worker',
  );
  if (!/\.(html|js)$/.test(file)) continue;
  const text = await readFile(file, 'utf8');
  for (const secret of [
    'demo12345',
    'Demo123!',
    'demo_student_a',
    '__LEARNMATE_DEMO__',
    'answerKeys',
    'local_mock_only',
  ]) {
    assert(!text.includes(secret), `发现模拟或调试内容 ${secret} in ${file}`);
  }
}
console.log(
  `PASS: ${files.length} 个组接口构建文件无演示口令、模拟答案与开发控制。`,
);
