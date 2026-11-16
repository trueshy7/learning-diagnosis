# 课程资源与知识点登记

本目录提供 28 份独立的项目新编教学摘要，不是从网站复制的教材原文。每份 Markdown 是一个独立资源；切出的多个片段不重复计数。`resources.json` 登记文件、课程、知识点、来源、版本、难度、参考链接和使用说明。材料由辅助工具整理，尚需教师核对准确性和范围。

20 份资料使用 `ts` 分支 SQL 中已经存在的 4 个数据结构知识点 ID，状态为 `confirmed`。其余 8 份资料对应 4 个建议新增知识点，状态为 `proposed`，默认不导入，也没有写入 B 的数据库。8 个知识点的演示覆盖只能作为本地草案，不代表全组已经冻结目录。

| 字段 | 含义 |
|---|---|
| resource_id | 本地语料编号，提交到 B 后以 B 生成的 ID 为权威 |
| course_id | 对应组长演示课程 `demo-course-ds-teacher-2` |
| knowledge_point_ids | 资源与知识点的多对多关联，本语料每项以一个主知识点标记 |
| resource_version | 本地资料版本，初始为 1；B 同步使用 B 的真实 version |
| title file source | 标题、相对原文件路径、项目自编来源说明 |
| license | 使用范围与非外站摘录声明，不代替外部教材授权 |
| difficulty status | 基础难度，以及已确认 ID 或建议 ID |
| reference_urls | 用于复核主题的参考网站；这些 URL 不是本资源的原文地址 |

`knowledge_points.json` 列出 4 个已存在 ID 和 4 个建议 ID。正式验收需要 B 建立并冻结至少 8 个知识点，再将建议 ID 映射为其权威 ID；不能让 C 的提案直接覆盖业务目录。

评测主集 `evaluation/questions.json` 有 20 题，覆盖已存在的 4 个知识点；扩展集 `questions_extended.json` 也固定为 20 题，覆盖全部 8 个知识点，其中 4 个尚为提案。每个问题预先保存相关资源和原文摘句、字符范围；半数查询不按知识点过滤。两套问题均标记 `pending_peer_review`，需要另一名成员填写 reviewer 并复核，不能当作已经完成独立人工评价。

TXT/Markdown 本地导入会保存原文件副本和解析日志；B 的拉取同步使用 B 已提取的正文，不重复下载教师原件。PDF 的页码只在 C 直接解析原 PDF 时可追溯，B 当前只给 text，不能从这份 text 猜测 PDF 原始页码。
