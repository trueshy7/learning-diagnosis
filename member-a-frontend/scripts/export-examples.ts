import { mkdir, writeFile } from 'node:fs/promises';
import { createSeed } from '../src/mocks/repository';
const dir = 'docs/frontend/examples';
await mkdir(dir, { recursive: true });
const state = createSeed();
for (const suffix of ['a-001', 'a-002', 'a-004']) {
  await writeFile(
    `${dir}/report-${suffix}.json`,
    JSON.stringify(
      {
        code: 'OK',
        message: '模拟契约样例',
        request_id: `sample-${suffix}`,
        data: state.reports[`report-${suffix}`],
      },
      null,
      2,
    ),
  );
}
await writeFile(
  `${dir}/attempt-a-001.json`,
  JSON.stringify(
    {
      code: 'OK',
      message: '学生DTO不含标准答案',
      request_id: 'sample-attempt',
      data: state.attempts['attempt-a-001'].value,
    },
    null,
    2,
  ),
);
console.log('已导出3份报告与1份学生测验响应，仅供接口协作。');
