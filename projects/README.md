# 外部贡献项目

这个目录是 Anaxagore 的工程控制面。每个子目录都是一个 Git submodule，指向自己 GitHub fork 的固定提交；主仓库只记录这一个提交指针，不复制上游历史，也不把项目源码发布到 GitHub Pages。

当前项目：

| 目录 | Fork | 上游 | 用途 |
| --- | --- | --- | --- |
| `sglang/` | `lgyStoic/sglang` | `sgl-project/sglang` | `codex/qwen-image-edit-batching` 待审贡献分支 |

## 日常流程

### Gemini 审查与 CPU 验证

在主仓库 Actions 手动运行「Gemini patch review」，填写 fork 分支和审查任务。工作流使用 GitHub-hosted `ubuntu-latest`，运行于摘要固定的 SGLang Xeon CPU 镜像（已含 SGLang 基础及 Diffusion 依赖），执行 Qwen Image Edit 聚焦单测和 Python 编译检查；随后调用 `.gemini/agents/sglang-contributor.md` 只读审查 diff 与测试报告。Gemini 不会改文件或推送。运行摘要和测试日志作为 14 天 artifact 保存。此流程不依赖 SGLang 官方的 GPU runner。

首次 checkout：

```bash
git clone --recurse-submodules https://github.com/lgyStoic/lgystoic.github.io.git
```

在项目内开发并推到自己的 fork：

```bash
cd projects/sglang
git switch -c codex/<topic>
# 改动、测试、commit
git push -u origin codex/<topic>
```

回到根目录后，手动触发 Actions 的「Gemini patch review」，填 branch 名。审查通过后从 fork 向上游开 PR。需要把控制面固定到更新后的提交时，更新 submodule 指针：

```bash
git submodule update --remote --depth=1 projects/sglang
git add projects/sglang
git commit -m "projects: 更新 SGLang 基线"
```

submodule 默认浅克隆；需要看较早历史时，在子项目中执行 `git fetch --unshallow`，不要把历史复制进本仓库。
