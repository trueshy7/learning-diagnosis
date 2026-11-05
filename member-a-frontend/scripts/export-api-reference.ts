import { z } from 'zod';
import { writeFile, readFile, mkdir } from 'node:fs/promises';
import * as s from '../src/api/contracts';
import * as req from '../src/api/contracts/requests';

const models: Record<string, z.ZodType> = {
  UserDTO: s.userSchema,
  LoginRequest: req.loginRequestSchema,
  LoginResponse: s.loginSchema,
  KnowledgePointDTO: s.knowledgeSchema,
  CourseDTO: s.courseSchema,
  OptionDTO: s.optionSchema,
  StudentQuestionDTO: s.studentQuestionSchema,
  AnswerDTO: s.answerSchema,
  ScoreDTO: s.scoreSchema,
  AttemptResultDTO: s.resultSchema,
  AttemptDTO: s.attemptSchema,
  CreateAttemptRequest: req.createAttemptRequestSchema,
  SubmitAttemptRequest: req.submitAttemptRequestSchema,
  SubmitAttemptResponse: s.submitResponseSchema,
  TaskDTO: s.taskSchema,
  KnowledgePointResultDTO: s.pointResultSchema,
  EvidenceDTO: s.evidenceSchema,
  ResourceSummaryDTO: s.resourceSummarySchema,
  ResourceDetailDTO: s.resourceSchema,
  RecommendationDTO: s.recommendationSchema,
  ComparisonPointDTO: s.comparisonPointSchema,
  ComparisonDTO: s.comparisonSchema,
  ReportDTO: s.reportSchema,
  HistoryItemDTO: s.historySchema,
  TeacherQuestionDTO: s.teacherQuestionSchema,
  CourseWriteDTO: s.courseWriteSchema,
  KnowledgePointWriteDTO: s.knowledgeWriteSchema,
  TeacherQuestionWriteDTO: s.questionWriteSchema,
  ResourceWriteDTO: s.resourceWriteSchema,
  UploadMetadataDTO: req.uploadMetadataSchema,
  DocumentDTO: s.documentSchema,
  TeacherResourceListItemDTO: s.teacherResourceSchema,
  OverviewDTO: s.overviewSchema,
  TeacherStudentDTO: s.teacherStudentSchema,
};
type JsonSchema = {
  [key: string]: unknown;
  type?: string | string[];
  properties?: Record<string, JsonSchema>;
  required?: string[];
  items?: JsonSchema;
  anyOf?: JsonSchema[];
  enum?: unknown[];
  const?: unknown;
};
const converted = Object.fromEntries(
  Object.entries(models).map(([name, schema]) => [
    name,
    z.toJSONSchema(schema) as JsonSchema,
  ]),
);
function key(schema: JsonSchema) {
  const { $schema: _schema, ...data } = schema;
  void _schema;
  return JSON.stringify(data);
}
const names = new Map(
  Object.entries(converted).map(([name, schema]) => [key(schema), name]),
);
function type(schema: JsonSchema, root = false): string {
  const known = names.get(key(schema));
  if (known && !root) return known;
  if (schema.enum) return schema.enum.map((x) => JSON.stringify(x)).join(' | ');
  if ('const' in schema) return JSON.stringify(schema.const);
  if (schema.anyOf) return schema.anyOf.map((x) => type(x)).join(' | ');
  if (Array.isArray(schema.type))
    return schema.type.map((t) => type({ ...schema, type: t })).join(' | ');
  if (schema.type === 'array') {
    const item = type(schema.items || {});
    return `Array<${item}>`;
  }
  if (schema.type === 'object')
    return `{ ${Object.entries(schema.properties || {})
      .map(
        ([name, child]) =>
          `${name}${schema.required?.includes(name) ? '' : '?'}: ${type(child)};`,
      )
      .join(' ')} }`;
  return schema.type === 'integer' || schema.type === 'number'
    ? 'number'
    : schema.type === 'boolean'
      ? 'boolean'
      : schema.type === 'string'
        ? 'string'
        : schema.type === 'null'
          ? 'null'
          : 'unknown';
}
const types = Object.entries(converted)
  .map(
    ([name, schema]) =>
      `export interface ${name} {\n${Object.entries(schema.properties || {})
        .map(
          ([prop, child]) =>
            `  ${prop}${schema.required?.includes(prop) ? '' : '?'}: ${type(child)};`,
        )
        .join('\n')}\n}`,
  )
  .join('\n\n');
const path = 'docs/frontend/backend-api-alignment.md';
const marker = '<!-- GENERATED_DTO_REFERENCE -->';
const content = await readFile(path, 'utf8');
if (!content.includes(marker)) throw new Error('缺少DTO附录标记');
await writeFile(
  path,
  content.slice(0, content.indexOf(marker)) +
    marker +
    '\n\n## 附录 完整 DTO 字段\n\n此附录由实际Zod契约生成；`?`表示可省略，`| null`表示字段存在但值可为空。数字范围、精度与跨字段规则以前文为准。对象未知非关键字段通常被前端忽略，StudentQuestionDTO严格拒绝任何额外字段。请求条件必填与业务校验不能只靠TypeScript表达。\n\n```typescript\nexport interface ApiResponse<T> { code: string; message: string; data: T | null; request_id: string; errors?: Array<{ field: string; message: string }>; }\nexport interface Page<T> { items: T[]; total: number; page: number; page_size: number; }\n\n' +
    types +
    '\n```\n',
);
await mkdir('docs/frontend/examples', { recursive: true });
await writeFile(
  'docs/frontend/examples/contract-schemas.json',
  JSON.stringify(converted, null, 2),
);
console.log(
  `已从实际schema生成${Object.keys(models).length}个DTO的Markdown附录及JSON Schema。自定义跨字段业务规则见文档正文。`,
);
