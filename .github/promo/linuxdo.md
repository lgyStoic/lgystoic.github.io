# LinuxDo（linux.do）· 分享 / 开发调优 节点

**标题**：离职后用 GitHub Pages 搭了个个人平台：每日 AI 雷达、深圳活动清单、从租电脑到订 ChatGPT Plus 的三步指南

**正文**：

没服务器没域名，全压在 GitHub 上，Actions 当后端：

- **每日雷达**：29 个源（OpenAI、DeepMind、HF Papers、PyTorch、Qwen、几位博主、GitHub Releases）每天 08:00 抓一遍，去重后交给模型排优先级、写一句话摘要，静态页 + RSS。模型挂了退化成规则。
- **活动清单**：深圳 / 广州 / 香港 AI 聚会、黑客松、比赛，50 多个源，按日期排。
- **上手指南**：写给刚离职想开始用 AI 工具的人，三步：
  1. 租一台电脑过渡（芝麻租赁 MacBook Air M3 299/月、云电脑、Colab 免费 T4、按小时 GPU 怎么选）
  2. Clash Verge Rev 从买订阅到手机端一条链接通用
  3. 国内订 ChatGPT Plus：Visa 全币种卡 + Play 改区，不用海外手机号、不用虚拟卡
- **状态页**：每个源的健康度、失败连击、自动禁用。

纯静态 HTML + 一个 Python 构建脚本，源码公开。指南里有几处推荐链接，都标了「推荐」。

站：https://lgystoic.github.io/?utm_source=linuxdo
指南：https://lgystoic.github.io/guides/?utm_source=linuxdo
仓库：https://github.com/lgyStoic/lgystoic.github.io

欢迎挑错，尤其是信息源和活动源还缺什么。
