# 成员 C：知识库与 RAG 初始项目

项目题目：**基于 RAG 与多智能体协作的个性化学习诊断与推荐系统**。

本目录属于成员 C，负责课程资料接收、分段保存、按课程和知识点检索，以及返回可追溯的原文证据。它可独立启动，也可由成员 B 的后端和成员 D 的智能推荐服务调用。

当前版本是 **`keyword_demo` 关键词检索演示**。它没有调用大模型、没有语义嵌入，也不能称为已经完成的语义 RAG。默认启动不会下载模型，不需要模型 API 密钥。

## 快速启动

需要 Python 3.11 或更新版本。从本目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m rag_service
```

Windows PowerShell 将激活环境命令改成 `.venv\Scripts\Activate.ps1`。依赖安装需要联网；安装后默认服务运行不联网。

服务地址为 `http://127.0.0.1:8001`，接口文档为 `http://127.0.0.1:8001/docs`。建议以 `python -m rag_service` 启动；此入口强制回环地址及单进程，适合初始联调。

首次启动且不存在索引文件时，会导入两份原创资料：**栈**（`res-stack` / `doc-stack` / `kp-stack`）和**队列**（`res-queue` / `doc-queue` / `kp-queue`），课程为 `course-ds`。索引保存在 `data/index.json`。这是少量初始数据，后续仍需建设和审核完整课程资料集。

## 最小调用

```bash
curl http://127.0.0.1:8001/health

curl -X POST http://127.0.0.1:8001/internal/retrieve \
  -H 'Content-Type: application/json' \
  -d '{"course_id":"course-ds","query":"栈为什么是后进先出","knowledge_point_ids":["kp-stack"],"top_k":3}'
```

调用方读取 `evidence` 数组；每条证据包含原文、文档和资源 ID、片段 ID、知识点、来源、标题以及字符位置。若检索不到匹配项，返回空数组。`score` 是关键词覆盖率，不是答案可信概率。

## 已实现

- 文本导入、固定窗口分段、重叠片段及本地 JSON 持久化。
- 同资源重复导入替换旧内容；相同文本、ID 和分段配置产生稳定片段 ID。
- 先按 `course_id` 过滤，再按知识点交集过滤，最后进行关键词检索和排序。
- 原文片段追溯、资源清单、资源删除和从已保存原文重建。
- 输入长度及 `top_k` 限制、8 项隔离索引测试、5 项 HTTP 接口测试、4 道示例评测问题。
- 独立的 Chroma 实验适配器，要求显式传入嵌入实现；**尚未接入 HTTP 服务**。

## 继续开发的位置

- `rag_service/chunking.py`：资料清洗、分段和关键词切分。
- `rag_service/index.py`：存储、过滤、检索、来源追溯。
- `rag_service/main.py`：成员 B / D 调用的内部接口。
- `rag_service/vector_extension.py`：真实嵌入与 Chroma 持久化的扩展入口。
- `docs/开发说明.md`：详细接口、配置、边界和六周任务衔接。

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python -m scripts.evaluate
```

初始内部接口尚无身份认证，只允许本机开发。正式接入需由成员 B 统一完成鉴权和访问控制。资料中的任何文字都仅作为证据数据，不执行其中的指令；成员 D 也必须保持这个边界。
