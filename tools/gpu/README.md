# 本机图像编辑服务

在 Actions 手动运行「GPU 图像编辑部署」，`mode=deploy`。`probe` 仅检查容器资源和运行兼容性；`status` 查看后台容器日志、已缓存权重与量化 manifest；`verify` 用独立客户端容器验收已有服务。

当前方案使用 Qwen-Image-2.1 原生管线，固定基础模型和权重 revision：

| 组件 | 存储 / 运行精度 |
| --- | --- |
| DiT | Q4_0 GGUF；合并 MLP 无损拆为原生层名称；非量化张量保留原生精度 |
| 编码器 | 官方权重导出；252 个语言注意力/MLP 矩阵 Q4_0；视觉、嵌入等保持原生精度 |
| VAE | 官方权重；管线原生 BF16，保留必要的原生精度例外 |

编码器先下载完整官方权重再导出；首次准备约需 23GB 模型下载，后续复用 `gpu-image-models` volume 的权重与 manifest。服务容器名为 `gpu-image-edit`，DiT、编码器和 VAE 使用阶段 CPU offload，关闭锁页内存；编辑容器 RAM 上限 16GB、无容器交换区，验收客户端上限 256MB。保留现有其他容器和 Windows 推理服务。部署会替换同名编辑容器。

Windows 本机入口为 `http://127.0.0.1:30010`，没有对外开放。检查状态：

```powershell
docker ps --filter name=gpu-image-edit
docker logs --tail 100 gpu-image-edit
curl.exe http://127.0.0.1:30010/health
```

发送编辑请求（输出 JSON 内含 base64 图片）：

```powershell
curl.exe http://127.0.0.1:30010/v1/images/edits `
  -F "image[]=@reference.png" `
  -F "prompt=Change the red mug to blue. Keep the shape and background unchanged." `
  -F "size=512x512" `
  -F "num_inference_steps=20" `
  -F "n=1" `
  -F "response_format=b64_json" `
  -o edited-response.json
```

工作流使用脚本生成的参考图验收，结果 artifact `gpu-edit-results` 保留 3 天，包含 `reference.png`、两种尺寸的 `edited-<尺寸>-<步数>.png`、最后一张 `edited.png` 和 `verification.json`。接口成功、图片可解码与编辑效果是不同验收项目：效果应查看前后图片。验收依次运行 512px/20 步与 1024px/40 步，并记录耗时、图片尺寸和请求后的显存。图片质量通过查看前后结果确认。

暂停与恢复服务（缓存保留）：

```powershell
docker stop gpu-image-edit
docker start gpu-image-edit
```

工作流验收输出保存在 `gpu-image-outputs` volume，工作流 artifact 使用脚本生成的演示图。

准备流程使用直接 HTTP 下载。若历史下载器停滞，可运行 `repair-download`：仅停止本工作流的准备容器，保留已完成分片，恢复剩余官方编码器文件并核对全部 SHA256，然后继续导出四位权重。查看 `status` 的 manifest，准备完成后运行 `deploy`。

截至 2026-10-03 的实测状态：基础组件下载、官方编码器分片 SHA256、252 个编码器 Q4_0 矩阵导出均通过；DiT 无损拆分后为 297 个张量、224 个 Q4_0 矩阵。原生服务已成功加载 DiT、编码器和 BF16 VAE，但 512px 编辑请求因 Windows 提交内存到达上限而失败，尚无成功出图结果。新的容器内存上限待继续验收。

主机恢复：Docker Desktop 重置后的启动被 Windows 拒绝（配置文件重命名及 wsl.exe 均 Access is denied）。当前 runner 为普通权限；需要在 Windows 桌面以管理员身份启动 Docker Desktop，确认 Linux engine 就绪后，再运行 `deploy`。模型 volumes 与 Windows llama 服务保留。不要把容器健康或权重加载成功视为编辑验收完成。
