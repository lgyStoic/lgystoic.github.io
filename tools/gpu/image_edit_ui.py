"""Password-protected Gradio client for the running image-edit service."""

from __future__ import annotations

import base64
import os
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path

import gradio as gr
import requests


MODEL_URL = os.getenv("IMAGE_EDIT_MODEL_URL", "http://gpu-image-edit:30010").rstrip("/")
MAX_REFERENCES = 10


def _paths(items):
    paths = []
    for item in items or []:
        value = item[0] if isinstance(item, (list, tuple)) else item
        if value:
            paths.append(Path(value))
    return paths


def edit_images(items, prompt, size, steps, seed):
    references = _paths(items)
    prompt = (prompt or "").strip()
    if not references:
        raise gr.Error("请至少上传一张参考图。")
    if len(references) > MAX_REFERENCES:
        raise gr.Error(f"最多支持 {MAX_REFERENCES} 张参考图。")
    if not prompt:
        raise gr.Error("请填写编辑指令。")

    session = requests.Session()
    session.trust_env = False
    started = time.monotonic()
    with ExitStack() as stack:
        files = []
        for path in references:
            handle = stack.enter_context(path.open("rb"))
            suffix = path.suffix.lower()
            content_type = "image/png" if suffix == ".png" else "image/jpeg"
            files.append(("image[]", (path.name, handle, content_type)))
        response = session.post(
            MODEL_URL + "/v1/images/edits",
            files=files,
            data={
                "prompt": prompt,
                "size": size,
                "num_inference_steps": str(int(steps)),
                "seed": str(int(seed)),
                "n": "1",
                "response_format": "b64_json",
            },
            timeout=1200,
        )
    if not response.ok:
        detail = response.text[:800]
        raise gr.Error(f"模型请求失败（HTTP {response.status_code}）：{detail}")

    try:
        payload = base64.b64decode(response.json()["data"][0]["b64_json"], validate=True)
    except (KeyError, IndexError, ValueError) as exc:
        raise gr.Error("模型返回了无法识别的图片数据。") from exc
    output_dir = Path(tempfile.gettempdir()) / "qwen-image-ui"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"edit-{time.time_ns()}.png"
    output.write_bytes(payload)
    elapsed = time.monotonic() - started
    info = (
        f"完成：{len(references)} 张参考图 · {size} · {int(steps)} 步 · "
        f"seed {int(seed)} · {elapsed:.2f} 秒 · {len(payload) / 1024:.0f} KiB"
    )
    return str(output), info


def health():
    session = requests.Session()
    session.trust_env = False
    try:
        response = session.get(MODEL_URL + "/health", timeout=8)
        response.raise_for_status()
        return "模型在线，可以生成。"
    except requests.RequestException as exc:
        return f"模型不可用：{exc}"


with gr.Blocks(title="5090 图像编辑台") as demo:
    gr.Markdown(
        "# 5090 图像编辑台\n"
        "上传 1–10 张参考图，提示词里可用“图 1、图 2”说明各自用途。"
    )
    status = gr.Markdown(health())
    with gr.Row():
        with gr.Column(scale=5):
            references = gr.Gallery(
                label="参考图（按上传顺序编号）",
                type="filepath",
                interactive=True,
                columns=4,
                height=360,
            )
            prompt = gr.Textbox(
                label="编辑指令",
                lines=5,
                placeholder="例如：使用图 1 作为西湖背景，把图 2 的人物放在前景，生成自然光艺术照……",
            )
            with gr.Row():
                size = gr.Dropdown(
                    ["512x512", "768x768", "1024x1024", "1344x768", "768x1344"],
                    value="768x768",
                    label="输出尺寸",
                )
                steps = gr.Slider(4, 50, value=20, step=1, label="推理步数")
            seed = gr.Number(value=42, precision=0, label="Seed")
            run = gr.Button("开始生成", variant="primary")
        with gr.Column(scale=5):
            result = gr.Image(label="生成结果", type="filepath", format="png", height=640)
            details = gr.Markdown("等待生成。")
    run.click(
        edit_images,
        inputs=[references, prompt, size, steps, seed],
        outputs=[result, details],
        api_name="edit",
    )


if __name__ == "__main__":
    username = os.environ.get("GRADIO_USERNAME", "lgystoic")
    password = os.environ["GRADIO_PASSWORD"]
    demo.queue(default_concurrency_limit=1, max_size=8).launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=os.getenv("GRADIO_SHARE", "true").lower() == "true",
        auth=(username, password),
        theme=gr.themes.Soft(),
        show_error=True,
    )
