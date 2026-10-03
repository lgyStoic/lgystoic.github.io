"""Prepare native-name 4bit components and run a private image-edit service."""
import argparse
import base64
import gc
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.request

ROOT = Path('/models')
BASE = ROOT / 'Qwen-Image-2.1'
REVISION = 'd26bb61231c349cf6b7896fa83353113880e1ba3'
DIT_REVISION = 'cc11433936a06e9765f7c0c0b1f0436cfd2b9856'
DIT = ROOT / 'qwen_image_2.1-Q4_0.gguf'
ENCODER = ROOT / 'qwen_image_2.1-encoder-Q4_0.gguf'


def prepare():
    from huggingface_hub import hf_hub_download, snapshot_download
    import gguf
    import numpy as np
    import torch
    from safetensors import safe_open

    ROOT.mkdir(parents=True, exist_ok=True)
    snapshot_download('Qwen/Qwen-Image-2.1', revision=REVISION,
                      local_dir=str(BASE), allow_patterns=['*.json', 'processor/*',
                      'scheduler/*', 'text_encoder/*.json', 'transformer/*.json', 'vae/*'])
    if not DIT.exists():
        source = hf_hub_download('leejet/Qwen-Image-2.1-GGUF',
                                'qwen_image_2.1-Q4_0.gguf', revision=DIT_REVISION)
        # Cache and export share one volume; hardlinks avoid a second large copy.
        os.link(Path(source).resolve(), DIT)
    if not ENCODER.exists():
        snapshot_download('Qwen/Qwen-Image-2.1', revision=REVISION,
                          local_dir=str(BASE), allow_patterns=['text_encoder/*'])
        output = ENCODER.with_suffix('.partial.gguf')
        writer = gguf.GGUFWriter(str(output), 'qwen3vl', use_temp_file=True)
        writer.add_name('Qwen-Image-2.1 native encoder Q4_0')
        count = 0
        files = sorted((BASE / 'text_encoder').glob('*.safetensors'))
        if not files:
            raise RuntimeError('Missing official encoder safetensors')
        for file in files:
            with safe_open(str(file), framework='pt', device='cpu') as weights:
                for name in weights.keys():
                    tensor = weights.get_tensor(name)
                    quantize = tensor.ndim == 2 and re.search(
                        r'language_model\.layers\.\d+\.(self_attn|mlp)\..*\.weight$', name)
                    if quantize:
                        data = gguf.quantize(tensor.float().numpy(), gguf.GGMLQuantizationType.Q4_0)
                        writer.add_tensor(name, data, raw_dtype=gguf.GGMLQuantizationType.Q4_0)
                        count += 1
                    elif tensor.dtype == torch.bfloat16:
                        data = tensor.view(torch.uint16).numpy()
                        writer.add_tensor(name, data, raw_dtype=gguf.GGMLQuantizationType.BF16)
                    else:
                        data = tensor.numpy()
                        writer.add_tensor(name, data)
                    print('ENCODER', name, tuple(tensor.shape), 'Q4_0' if quantize else str(tensor.dtype), flush=True)
                    del data, tensor
            gc.collect()
        if count != 252:
            raise RuntimeError(f'Expected 252 encoder attention/MLP matrices, got {count}')
        writer.write_header_to_file()
        writer.write_kv_data_to_file()
        writer.write_tensors_to_file(progress=True)
        writer.close()
        output.replace(ENCODER)
    report = {}
    for path in [DIT, ENCODER]:
        reader = gguf.GGUFReader(str(path))
        q4 = [x.name for x in reader.tensors if x.tensor_type == gguf.GGMLQuantizationType.Q4_0]
        if not q4:
            raise RuntimeError(f'No Q4_0 matrices in {path}')
        report[path.name] = {'bytes': path.stat().st_size, 'tensors': len(reader.tensors), 'q4_matrices': len(q4)}
        del reader
    report['base_revision'] = REVISION
    report['dit_revision'] = DIT_REVISION
    report['vae_runtime_dtype'] = 'bf16 (native precision exceptions retained)'
    (ROOT / 'manifest.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2), flush=True)


def serve():
    command = ['sglang', 'serve', '--model-path', str(BASE), '--model-id', 'Qwen-Image-2.1',
               '--host', '0.0.0.0', '--port', '30010', '--attention-backend', 'torch_sdpa',
               '--component-weights-paths.transformer', str(DIT),
               '--component-weights-paths.text_encoder', str(ENCODER),
               '--performance-mode', 'manual', '--text-encoder-cpu-offload', 'true']
    print('SERVE:', ' '.join(command), flush=True)
    os.execvp(command[0], command)


def verify():
    from PIL import Image, ImageDraw
    import requests
    url = 'http://127.0.0.1:30010'
    deadline = time.monotonic() + 1200
    while time.monotonic() < deadline:
        try:
            response = requests.get(url + '/health', timeout=10)
            if response.ok:
                break
        except requests.RequestException:
            pass
        time.sleep(10)
    else:
        raise RuntimeError('Image service did not become healthy within 20 minutes')
    out = Path('/outputs')
    out.mkdir(exist_ok=True)
    reference = out / 'reference.png'
    canvas = Image.new('RGB', (512, 512), 'white')
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((140, 140, 320, 370), radius=24, fill='red')
    draw.arc((270, 170, 385, 330), 270, 90, fill='red', width=25)
    draw.ellipse((140, 120, 320, 170), fill='#aa0000')
    canvas.save(reference)
    cases = []
    for size, steps in [('512x512', 20), ('1024x1024', 40)]:
        start = time.monotonic()
        with reference.open('rb') as image:
            response = requests.post(url + '/v1/images/edits',
                                     files={'image[]': ('reference.png', image, 'image/png')},
                                     data={'prompt': 'Change the red mug to blue. Keep the mug shape and white background unchanged.',
                                           'size': size, 'num_inference_steps': str(steps),
                                           'n': '1', 'response_format': 'b64_json'}, timeout=1200)
        if not response.ok:
            print('EDIT_ERROR:', response.status_code, response.text[:2000], flush=True)
        response.raise_for_status()
        result = response.json()
        payload = base64.b64decode(result['data'][0]['b64_json'], validate=True)
        target = out / f'edited-{size}-{steps}.png'
        target.write_bytes(payload)
        (out / 'edited.png').write_bytes(payload)
        with Image.open(target) as edited:
            edited.load()
            if edited.size != tuple(map(int, size.split('x'))):
                raise RuntimeError(f'Unexpected output size: {edited.size}')
        report = {'elapsed_seconds': round(time.monotonic() - start, 2),
                  'reference': reference.name, 'output': target.name, 'bytes': len(payload),
                  'endpoint': '/v1/images/edits', 'steps': steps, 'size': size}
        cases.append(report)
        (out / 'verification.json').write_text(json.dumps({'cases': cases}, indent=2))
        print(json.dumps(report, indent=2), flush=True)
        subprocess.run(['nvidia-smi', '--query-gpu=memory.used,memory.free', '--format=csv'], check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['prepare', 'serve', 'verify'])
    mode = parser.parse_args().mode
    globals()[mode]()
