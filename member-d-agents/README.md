# 成员 D：学习诊断与多智能体推荐骨架

项目：《基于 RAG 与多智能体协作的个性化学习诊断与推荐系统》。本目录由成员 D 负责，可独立运行，也可由成员 B 的后端调用。

当前实现采用 **规则诊断 + 固定的三个逻辑代理顺序编排**（诊断 → 检索 → 推荐），返回 `mode=rule_template_demo`。它没有调用真实大语言模型，也不具备自主规划或多模型协商能力。`llm_client.py` 只是后续实现的接口边界，调用占位实现会抛出 `NotImplementedError`。

## 快速开始

要求 Python 3.11 或以上；在本目录执行。若总项目提供统一锁定文件，优先按总项目说明安装锁定版本。

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
python -m uvicorn diagnosis_service.main:app --host 127.0.0.1 --port 8002
```

Windows PowerShell 激活命令为 `.venv\Scripts\Activate.ps1`，复制配置用 `Copy-Item .env.example .env`；其余 Python 命令相同。

浏览器打开 [交互接口文档](http://127.0.0.1:8002/docs)。健康检查 `GET /health` 返回：

```json
{"status":"ok","service":"agents","mode":"rule_template_demo"}
```

另开终端，在本目录提交示例：

```bash
curl -X POST http://127.0.0.1:8002/internal/diagnose-and-recommend \
  -H 'Content-Type: application/json' --data-binary @examples/request.json
```

预期：栈 3 题答对 1 题，状态 `weak`；队列 3 题全部正确，状态 `mastered`；推荐仅含目录中的 `res-stack`。默认检索是 `RAG_MODE=mock`，证据 `source=builtin_mock_fixture`，不是知识库真实检索结果。

## 与成员 C 联调

先启动 C 的 8001 服务，将本目录 `.env` 中的 `RAG_MODE=mock` 改为 `RAG_MODE=http`，再重新启动 D。也可以直接设置环境变量（优先于 `.env`）：

```bash
export RAG_MODE=http
export RAG_BASE_URL=http://127.0.0.1:8001
export RAG_TIMEOUT_SECONDS=5
python -m uvicorn diagnosis_service.main:app --host 127.0.0.1 --port 8002
```

PowerShell 用 `$env:RAG_MODE="http"` 等设置。程序通过 `python-dotenv` 自动读取启动目录的 `.env`，请在本目录启动，修改配置后重启。如果 C 超时、不可达、返回错误或响应格式不符，D 返回空证据和明确的 `fallback_status`，不把失败当成功。此时仍可能依据 B 给出的合法资源目录生成规则建议。

## 验证与开发

```bash
python -m pytest -q
```

覆盖规则阈值、少样本、重复题去重、矛盾输入拒绝、合法资源 ID、检索异常及复测比较。详细目录、数据流、接口边界、六周计划见 [开发说明](docs/开发说明.md)。服务默认仅监听本机，内部接口没有鉴权，不能直接面向公网部署。

