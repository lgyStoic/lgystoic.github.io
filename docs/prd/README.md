# 产品说明（PRD）索引

每个模块一份，结构相同，方便修 bug 和加功能时直接对照。改了功能请顺手更新对应文件；开新会话时先让 agent 读这里。

| 模块 | 角色 | 页面 | 文档 |
|---|---|---|---|
| 站点框架 | — | 全站 | [site.md](site.md) |
| 笔记 | 记 | `/notes/` | [notes.md](notes.md) |
| 上手指南 | 记 | `/guides/` | [guides.md](guides.md) |
| 每日雷达 | 看 | `/radar/` | [radar.md](radar.md) |
| 活动清单 | 看 | `/radar/events/` | [events.md](events.md) |
| 工作机会 | 看 | `/radar/jobs/` | [jobs.md](jobs.md) |
| 开源贡献路线 | 看 | `/radar/contributions/` | [contributions.md](contributions.md) |
| 收件箱 · 小红书文稿 | 做 | 私有仓库 | [inbox.md](inbox.md) |
| 运行状态 · 巡检 | 做 | `/status/` | [status.md](status.md) |

每份文档的固定章节：目标与非目标 → 用户与约束 → 功能清单 → 数据管线 → 数据模型 → 规则 → 渲染 → 配置 → 验证与排查 → 已知问题 → 待办 → 常见改动去哪改。

站点级共同约束（所有模块都要满足）：纯静态、无框架、页面不加载第三方脚本（访问统计与评论区除外）；手机 340–430px 宽不能横向溢出；数据即文件（`radar/data/*.json` 是公开 API，不能放密钥或私密信息）；AI 环节可插拔，没有 key 时退回规则；任何一次自动运行失败都不能让整站挂掉。
