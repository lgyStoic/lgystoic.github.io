# 独立内容交接服务核心

这是内容全链路的纯 Python 状态核心，负责以 SQLite 保存交接元数据、幂等键、状态转移和审计日志。它不保存正文、图片、账号状态或密钥；源文件继续留在所属仓库，版本用 commit/blob 和 SHA-256 固定。

本目录可被 GitHub Actions 或私有工作台调用。LongCat 等模型密钥只从 Actions secrets 或运行环境读取，绝不写入仓库。

本地回归：

```bash
python3 -m unittest discover -s tools/content_flow -p 'test_*.py' -v
```
