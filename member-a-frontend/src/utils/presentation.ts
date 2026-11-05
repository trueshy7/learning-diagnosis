import { z } from 'zod';
import { ApiError } from '../api/client';
import type { Task } from '../api/contracts';

const errors: Record<string, string> = {
  INVALID_CREDENTIALS: '账号或密码错误',
  AUTH_REQUIRED: '请先登录后继续操作',
  TOKEN_EXPIRED: '登录已过期，请重新登录',
  FORBIDDEN: '你没有访问这项内容的权限',
  NOT_FOUND: '未找到所请求的内容，请返回后重试',
  ATTEMPT_NOT_FOUND: '未找到这次测验',
  REPORT_NOT_FOUND: '未找到这份报告',
  RESOURCE_REMOVED: '来源已移除或停用，报告中仍保留生成时的引用片段',
  ATTEMPT_ALREADY_SUBMITTED: '测验已提交，无法修改本次答案，请重新查看结果',
  SNAPSHOT_MISMATCH: '题目版本发生变化，请重新加载测验后核对作答',
  ATTEMPT_NOT_SUBMITTED: '本次测验尚未提交，请先完成作答',
  TASK_NOT_RETRYABLE: '当前任务暂不支持重试，请刷新查看最新状态',
  REFERENCE_CONFLICT: '当前内容仍有关联或暂不满足操作条件，请检查后重试',
  DUPLICATE_NAME: '名称已存在，请使用其他名称',
  INVALID_OPTIONS: '题目或选项已变化，请重新加载并核对作答',
  INVALID_BASELINE: '复测与基准报告不匹配，请从原报告重新发起',
  FILE_TOO_LARGE: '文件超过 10 MiB 上限',
  UNSUPPORTED_FILE_TYPE: '仅支持 TXT、MD、文本型 PDF',
  NO_TEXT: '未检测到可提取的文本，请选择文本资料后重新上传',
  VALIDATION_ERROR: '部分填写内容不符合要求，请核对表单后重试',
  SERVICE_UNAVAILABLE: '服务暂时不可用，请稍后重试',
  MOCK_PROCESSING_FAILED: '处理未完成，原始记录已保留，可按提示重试',
  NETWORK_ERROR: '暂时无法连接服务，请检查网络后重试',
  REQUEST_TIMEOUT: '等待响应超时，请稍后确认处理结果',
  REQUEST_CANCELLED: '操作已取消',
  INVALID_RESPONSE: '收到的数据暂时无法展示，请刷新重试或联系维护者',
};
export function userError(error: unknown): string {
  if (error instanceof ApiError)
    return (
      errors[error.code] ||
      (error.httpStatus === 403
        ? errors.FORBIDDEN
        : error.httpStatus === 410
          ? errors.RESOURCE_REMOVED
          : '操作暂未完成，请稍后重试或联系维护者')
    );
  return '操作暂未完成，请稍后重试或联系维护者';
}
export function taskError(code: string | null) {
  return code
    ? errors[code] || '处理暂未完成，请稍后重试或联系教师'
    : '处理暂未完成，请稍后重试或联系教师';
}
export function taskText(task: Task | null) {
  if (!task) return '正在查询处理进度';
  const doc = task.kind === 'document_ingestion';
  return task.status === 'queued'
    ? doc
      ? '资料已接收，等待处理'
      : '成绩已保存，等待分析'
    : task.status === 'running'
      ? doc
        ? '正在处理资料，请稍候'
        : '正在整理本次学习结果'
      : task.status === 'completed'
        ? doc
          ? '资料处理完成'
          : '学习报告已生成'
        : doc
          ? '资料处理未完成'
          : '学习分析未完成，成绩已保留';
}
const fields: Record<string, string> = {
  title: '标题',
  name: '名称',
  description: '说明',
  stem: '题干',
  options: '选项',
  text: '选项内容',
  label: '选项标签',
  correct_option_keys: '正确答案',
  knowledge_point_ids: '关联知识点',
  course_id: '课程',
  explanation: '解析',
  sort_order: '显示顺序',
  text_content: '资料正文',
  external_url: '外部链接',
  difficulty: '难度',
};
export function validationMessage(error: z.ZodError) {
  return [
    ...new Set(
      error.issues.map((issue) => {
        const name =
          issue.path
            .map(String)
            .reverse()
            .map((key) => fields[key])
            .find(Boolean) || '填写内容';
        if (issue.code === 'custom') return issue.message;
        if (issue.code === 'too_small')
          return `${name}不能为空或数量不足，请核对后填写`;
        if (issue.code === 'too_big')
          return `${name}超过长度或数量上限，请适当缩减`;
        return `${name}格式不正确，请核对后填写`;
      }),
    ),
  ].join('；');
}
