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


## 2026-11-14 中期增量

当前默认仍为规则模板演示。若自行配置兼容 Chat Completions 的模型服务，可设置 `LLM_MODE=openai_compatible`、`LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY` 和 `LLM_TIMEOUT_SECONDS`。只有通过输出校验的本次调用才标记 `grounded_llm`；密钥只保存在本地环境，不提交。此适配器目前通过模拟响应测试，**尚无真实模型调用证据**。新增的资源过滤、证据校验、评测方法与待联调字段见 [中期实现说明](docs/中期实现说明.md)。

## DeepSeek 真实模型闭环（待持有密钥者执行）

本服务内置 DeepSeek Chat Completions 配置，默认模型 `deepseek-flash`。在 `member-d-agents/` 中复制 `.env.example` 为 `.env`，把 `LLM_MODE` 改为 `deepseek`，在**本机** `.env` 中增加 `DEEPSEEK_API_KEY=你的密钥`。该文件已被 `.gitignore` 排除，不要提交、截图或在群聊发送密钥。可选调整 `DEEPSEEK_MODEL` 和 `LLM_TIMEOUT_SECONDS`。密钥由运行机器提供，报告和日志不记录原始请求或密钥。

从仓库根目录启动真实闭环检查（需本机可访问 `api.deepseek.com`，会产生一次真实 API 调用及相应费用）：

```bash
# macOS / Linux / Git Bash
EXPECT_REAL_MODEL=1 python scripts/check_integration.py
```

```powershell
# Windows PowerShell
$env:EXPECT_REAL_MODEL="1"
python scripts/check_integration.py
Remove-Item Env:EXPECT_REAL_MODEL
```

脚本在临时环境启动 C、D、B，完成登录、评分、C 的 HTTP 检索、D 的规则诊断和 DeepSeek 解释。成功时必须返回 `model_mode=grounded_llm`、非空的 `model_evidence_ids` 和 `result=passed`；失败不会把规则回退误报为真实模型成功。仅保存脱敏的检查结果和调用时间，再对照人工量表评价建议。当前仓库未包含真实调用记录，持有密钥者执行后才可在报告中标记完成。
