# 每日内容交付契约

## 用户收到什么

每天收到一封 Gmail 通知，邮件指向对应的 GitHub Actions 运行页。运行页的 artifact 名称为 `content-flow-dispatch-<run_id>`，下载后得到一个交付目录。

```text
delivery.json
xiaohongshu/
  posts/cards/...
  posts/jobs/...
  posts/tracks/...
```

公众号和视频号有成品时，分别增加 `wechat_official/`、`wechat_channels/` 目录；没有成品时，`delivery.json` 中标记 `optional_not_ready`，不会伪造附件。

## `delivery.json`

- `channels.<channel>.status`：`ready`、`empty` 或 `optional_not_ready`。
- `channels.<channel>.files[]`：相对路径和 SHA-256。
- `review.status`：默认 `needs_review`。
- `review.platform_submission`：固定为 `manual`，表示最终平台提交由用户完成。

## 本地操作

1. 下载 artifact。
2. 打开 `delivery.json`，只处理 `ready` 渠道。
3. 对需要发布的正文、图片或视频做最后人工审看。
4. 在官方平台完成发布或保存草稿。
5. 将平台内容 ID、渠道、版本、状态和可见证据回填发布台账。

本地不需要运行采集、模型、交接或重试脚本，也不需要打开其他 Codex chat。

## 验收规则

- 文件存在且 SHA-256 匹配，才算交付包完整。
- 交付包完整不等于已发布。
- 平台开关、账号限制和发布结果仍以发布台账为准。
- 未能取得平台可见证据的内容不能标记为已发布。
