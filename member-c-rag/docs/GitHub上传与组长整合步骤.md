# 成员 C 上传 GitHub 与组长整合步骤

代码已经保存在本机 `E:\classwork_software_C\project-yjy\member-c-rag`，本地仓库分支为 `yjy`，远程指向你们的项目。本次没有执行 GitHub 上传。只提交 `member-c-rag`，不把其他成员代码、模型、索引、虚拟环境、密钥一起提交。

## 上传前确认

打开 PowerShell，逐条执行：

```powershell
cd E:\classwork_software_C\project-yjy
git branch --show-current
git remote -v
git status --short
```

分支应为 yjy，远程应为 `https://github.com/trueshy7/learning-diagnosis.git`。当前修改应都在 member-c-rag 下。本次是在远程 yjy 的原提交上开发，组长代码仅用作接口参照，未把其整个后端复制进你的分支。

## 本地验证

```powershell
cd E:\classwork_software_C\project-yjy\member-c-rag
.\.venv\Scripts\python.exe -m scripts.check
```

若需要重跑语义检索，先按 README 准备模型，再设置 RAG_BACKEND 和 RAG_MODEL_PATH。评测命令和真实结果都保存在本模块；没有配置 B 密钥时不能把真实 B 同步联调写为通过。

## 提交并推送到 yjy

```powershell
cd E:\classwork_software_C\project-yjy
git fetch origin
git add -- member-c-rag
git diff --cached --stat
git diff --cached --name-only
git commit -m "feat(rag): implement member C knowledge service and adapt ts contract"
git push origin yjy
```

执行 commit 前看暂存清单，应该只有 C 的源代码、教学摘要、评测集、结果和说明。`.venv`、`.env`、`data/models`、Chroma 数据、个人上传原件和运行索引已忽略。

第一次 push 如需登录，使用有该仓库写权限的 GitHub 账号完成 Git 提供的认证。如果没有权限，需要组长把你的账号加入协作者。不要把登录令牌写入命令、源码或截图。若提示远程已有新提交导致拒绝推送，先保留本地提交并查看 `git fetch origin` 后的差异，再整合；不要使用强制推送。

推送成功后打开 [yjy 分支](https://github.com/trueshy7/learning-diagnosis/tree/yjy)，核对 member-c-rag 和其中的当前完成情况文档，记录自己的提交 SHA。把该提交 SHA 和文档交给组长即可；不需要把整个 E:\classwork_software_C 文件夹上传。

## ts 与 yjy 的特殊情况

本次检查时，yjy 为 `c2bf9383f965d1812e0a74c80f23438cb6ba57e3`，ts 为 `37c05764e5041b2c47c567a4db5b950161bf6c94`，两个分支没有共同祖先。直接用普通 merge 或比较页面不一定能形成正常合并请求，不能把问题误当成你没有提交成功。

你正常推送 yjy。组长在自己的干净工作区中，可以仅拣入你的 C 模块提交：

```powershell
git switch ts
git status --short
git fetch origin
git cherry-pick 替换为你本次C模块提交的SHA
# 复验 C 服务、B 同步及 D 新检索接口后，由组长推送
git push origin ts
```

cherry-pick 不要求两分支有共同祖先。本次提交只应含 member-c-rag，避免引入你分支上其他成员的旧实现。如果组长期间已改过 C 文件，可能出现冲突，逐项核对接口和测试后处理；不要覆盖其未提交工作。

另一个可控方案是在 ts 上取你的 C 目录，再由组长检查并提交：

```powershell
git switch ts
git status --short
git fetch origin yjy
git restore --source=origin/yjy -- member-c-rag
git diff --stat
git add -- member-c-rag
git commit -m "integrate member C RAG service"
```

这两种方案二选一。都应由另一名成员检查后再完成最终整合。交接文档在 `member-c-rag/docs/成员C当前实现与下一阶段计划.md`，可直接在 GitHub 阅读。
