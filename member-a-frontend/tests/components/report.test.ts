import { it, expect, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import KnowledgeTable from '../../src/components/reports/KnowledgeTable.vue';
import ComparisonPanel from '../../src/components/reports/ComparisonPanel.vue';
import QuestionCard from '../../src/components/quiz/QuestionCard.vue';
import PageState from '../../src/components/common/PageState.vue';
import { createSeed } from '../../src/mocks/repository';
import { ApiError } from '../../src/api/client';
vi.mock('../../src/components/reports/BarChart.vue', () => ({
  default: {
    props: ['items'],
    template: '<div data-testid="chart">{{ items }}</div>',
  },
}));
it('2/2 展示正确率100%和证据不足，掌握度图无柱', () => {
  const r = createSeed().reports['report-a-004'];
  const w = mount(KnowledgeTable, { props: { points: r.knowledge_points } });
  expect(w.text()).toContain('2 / 2');
  expect(w.text()).toContain('100%');
  expect(w.text()).toContain('证据不足');
  expect(w.text()).toContain('本次未覆盖');
  expect(w.text()).not.toContain('已掌握');
  expect(w.find('[data-testid="chart"]').exists()).toBe(false);
});
it('有效零分与接口失败显示不同，不填补失败数据', () => {
  const w = mount(KnowledgeTable, {
    props: { points: createSeed().reports['report-a-005'].knowledge_points },
  });
  expect(w.text()).toContain('0%');
  expect(w.text()).toContain('薄弱');
  const err = mount(PageState, {
    props: {
      error: new ApiError('NETWORK_ERROR', '内部网络栈 /private/server/path'),
    },
    global: {
      stubs: {
        ElButton: { template: '<button><slot /></button>' },
        RouterLink: true,
      },
    },
  });
  expect(err.text()).toContain('暂时无法连接服务');
  expect(err.text()).not.toContain('/private/server/path');
  expect(err.text()).not.toContain('0%');
});
it('部分可比仅绘制可比点，不可比显示原因', () => {
  const c = createSeed().reports['report-a-002'].comparison!;
  c.knowledge_points[0].comparable = false;
  c.knowledge_points[0].reason = '覆盖不足';
  c.knowledge_points[0].delta_percentage_points = null;
  const w = mount(ComparisonPanel, { props: { comparison: c } });
  expect(w.text()).toContain('覆盖不足');
  expect(w.text()).toContain('个百分点');
  expect(w.find('[data-testid="chart"]').text()).not.toContain(
    '顺序表与复杂度',
  );
});
it('多选可取消，禁用后不可修改；组件不携带标准答案', async () => {
  const q = createSeed().attempts['attempt-a-001'].value.questions[2];
  const w = mount(QuestionCard, {
    props: { question: q, index: 2, modelValue: [], disabled: false },
  });
  await w.findAll('input')[0].setValue(true);
  expect(w.emitted('update:modelValue')![0]).toEqual([
    [q.options[0].option_id],
  ]);
  await w.setProps({ modelValue: [q.options[0].option_id] });
  await w.findAll('input')[0].setValue(false);
  expect(w.emitted('update:modelValue')![1]).toEqual([[]]);
  await w.setProps({ disabled: true });
  expect(w.find('fieldset').attributes()).toHaveProperty('disabled');
  expect(w.html()).not.toContain('correct_option_ids');
});
