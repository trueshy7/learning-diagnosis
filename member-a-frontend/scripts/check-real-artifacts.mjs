import { readdir, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import assert from 'node:assert/strict';
async function files(dir) {
  return (
    await Promise.all(
      (await readdir(dir, { withFileTypes: true })).map((x) =>
        x.isDirectory() ? files(join(dir, x.name)) : join(dir, x.name),
      ),
    )
  ).flat();
}
const all = await files('dist/real');
const forbidden = [
  'MOCK_ONLY_ANSWER_KEY',
  'isolated-original-demo-answer-catalog',
  'demo_student_a',
  'demo_student_b',
  'demo_teacher',
  'Demo123!',
  '__LEARNMATE_DEMO__',
  'setupWorker(',
  'learning-diagnosis-demo-v1',
];
for (const file of all) {
  assert(
    !/mockServiceWorker|\/mocks[-/]|\\mocks[-\\]|DemoPanel/.test(file),
    `模拟文件泄漏：${file}`,
  );
  const text = await readFile(file, 'utf8');
  for (const marker of forbidden)
    assert(!text.includes(marker), `真实产物 ${file} 含 ${marker}`);
}
console.log(
  `PASS: ${all.length} 个真实构建文件无演示账号、答案、worker、模拟控制入口。`,
);
