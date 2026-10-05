# 独立内容交接服务

## 目的

把采集、初加工、研究、创作和发布预检之间的任务从 ChatGPT desktop 中解耦。服务只管理元数据和交接状态，正文与素材仍由所属仓库保存。

## 当前实现

`tools/content_flow/` 提供 SQLite 状态核心：

- 固定输入版本和 SHA-256 引用；
- 交接幂等键，重复请求不会创建第二个任务；
- 受约束的状态转移；
- 接收、处理、审核和完成的审计日志；
- 从共享工作区 `operations/content-flow/handoffs.json` 导入历史交接。

## 状态

`draft → sent → accepted → in_progress → ready_for_review → completed`。

`needs_input`、`blocked` 和 `cancelled` 是可追踪的旁路状态。完成状态必须由外部验收证据支持，服务不会把文件存在推断成已发布。

## 安全边界

公开仓库不能保存私有正文、账号状态、SQLite 生产数据库或 LongCat/Gmail 密钥。模型密钥只能作为 GitHub Actions secret 或私有运行环境变量注入。平台提交仍受 `content-projects/publishing/state.json` 和人工审核门控制。

## 验收命令

```bash
python3 -m unittest discover -s tools/content_flow -p 'test_*.py' -v
```

后续阶段将接入 manifest 注册、GitHub Actions 定时调度和私有工作台；接口和字段先保持向后兼容。
