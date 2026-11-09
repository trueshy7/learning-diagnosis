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
const files = await list('dist/mock');
assert(
  files.some((file) => file.endsWith('mockServiceWorker.js')),
  '示例构建需要HTTP模拟worker',
);
for (const file of files) {
  assert(!file.includes('DemoPanel'), `展示构建包含开发面板 ${file}`);
  const text = await readFile(file, 'utf8');
  assert(!text.includes('__LEARNMATE_DEMO__'), `展示构建包含开发控制 ${file}`);
  assert(!text.includes('重置演示数据'), `展示构建包含面板重置按钮 ${file}`);
}
console.log(
  `PASS: ${files.length} 个示例展示构建文件无开发面板和控制入口；保留必要HTTP模拟，不作为正式业务安全验收。`,
);
