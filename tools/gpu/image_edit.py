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
DIT_SOURCE = ROOT / 'qwen_image_2.1-Q4_0.gguf'
DIT = ROOT / 'qwen_image_2.1-native-Q4_0.gguf'
ENCODER = ROOT / 'qwen_image_2.1-encoder-Q4_0.gguf'


def prepare():
    os.environ.setdefault('HF_HUB_DISABLE_XET', '1')
    from huggingface_hub import hf_hub_download, snapshot_download
    import gguf
    import numpy as np
    import torch
    from safetensors import safe_open

    ROOT.mkdir(parents=True, exist_ok=True)
    snapshot_download('Qwen/Qwen-Image-2.1', revision=REVISION,
                      local_dir=str(BASE), allow_patterns=['*.json', 'processor/*',
                      'scheduler/*', 'text_encoder/*.json', 'transformer/*.json', 'vae/*'])
    if not DIT_SOURCE.exists():
        source = hf_hub_download('leejet/Qwen-Image-2.1-GGUF',
                                'qwen_image_2.1-Q4_0.gguf', revision=DIT_REVISION)
        # Cache and export share one volume; hardlinks avoid a second large copy.
        os.link(Path(source).resolve(), DIT_SOURCE)
    normalize_dit()
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


def normalize_dit():
    """Split fused MLP rows into the native layer names without requantizing."""
    if DIT.exists():
        return
    import gguf
    reader = gguf.GGUFReader(str(DIT_SOURCE))
    output = DIT.with_suffix('.partial.gguf')
    writer = gguf.GGUFWriter(str(output), 'qwen_image', use_temp_file=True)
    writer.add_name('Native diffusion Q4_0 (lossless fused MLP split)')
    count = 0
    for tensor in reader.tensors:
        if tensor.name.endswith('.img_mlp.gate_up.weight'):
            if tensor.tensor_type != gguf.GGMLQuantizationType.Q4_0 or tensor.data.shape[0] % 2:
                raise RuntimeError(f'Unexpected fused MLP layout: {tensor.name}')
            half = tensor.data.shape[0] // 2
            for suffix, data in [('gate_layer', tensor.data[:half]), ('proj', tensor.data[half:])]:
                name = tensor.name.replace('gate_up.weight', suffix + '.weight')
                writer.add_tensor(name, data, raw_dtype=tensor.tensor_type)
            count += 1
        else:
            writer.add_tensor(tensor.name, tensor.data, raw_dtype=tensor.tensor_type)
    if count != 32:
        raise RuntimeError(f'Expected 32 fused MLP matrices, got {count}')
    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_tensors_to_file(progress=True)
    writer.close()
    output.replace(DIT)
    print('DIT_NATIVE_LAYOUT: split 32 fused MLP matrices without requantization', flush=True)


def repair_download():
    """Resume stalled encoder shards with byte ranges and official SHA256."""
    import hashlib
    import shutil
    from concurrent.futures import ThreadPoolExecutor
    import requests

    shards = [
        ('model-00001-of-00004.safetensors', 4998056552, 'dde00291b5f7fb92013895310a3da0ddba78674df9f10d505d375243dc01fc6f'),
        ('model-00002-of-00004.safetensors', 4915962464, '9047faccc0a6d98496a52d55f27be1c94a9c259d1e283fbea0128d054a948d42'),
        ('model-00003-of-00004.safetensors', 4915962496, '8c54187654c0176b73ae73785bf791dc9a14c9df7fb4310083a09d42048cb57e'),
        ('model-00004-of-00004.safetensors', 2704357976, '5311532aaaeae3259eb6a7b2c600636be1159adf7ded35f53579f7d0e7d43cdd'),
    ]
    directory = BASE / 'text_encoder'
    directory.mkdir(parents=True, exist_ok=True)
    cache = BASE / '.cache/huggingface/download/text_encoder'

    def digest(path):
        checksum = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(16 * 2**20), b''):
                checksum.update(block)
        return checksum.hexdigest()

    def download(item):
        name, expected_size, expected_hash = item
        destination = directory / name
        if destination.exists() and destination.stat().st_size == expected_size and digest(destination) == expected_hash:
            print('HTTP_ALREADY_VERIFIED:', name, flush=True)
            return
        temporary = directory / (name + '.http.incomplete')
        backups = []
        if not temporary.exists():
            candidates = sorted(cache.glob(f'*.{expected_hash}.*.incomplete'), key=lambda p: p.stat().st_size, reverse=True)
            if candidates:
                source = candidates[0]
                stat = source.stat()
                if stat.st_blocks * 512 >= stat.st_size and stat.st_size <= expected_size:
                    shutil.copyfile(source, temporary)
                    backup = Path(str(source) + '.xet-backup')
                    source.rename(backup)
                    backups.append(backup)
                    print('HTTP_RESUME_PREFIX:', name, stat.st_size, flush=True)
        for attempt in range(6):
            offset = temporary.stat().st_size if temporary.exists() else 0
            if offset < expected_size:
                url = f'https://huggingface.co/Qwen/Qwen-Image-2.1/resolve/{REVISION}/text_encoder/{name}?http_resume={time.time_ns()}'
                headers = {'Range': f'bytes={offset}-'} if offset else {}
                try:
                    with requests.get(url, headers=headers, stream=True, timeout=(20, 60)) as response:
                        if response.status_code not in (200, 206):
                            raise RuntimeError(f'HTTP transfer rejected: {name}, status={response.status_code}')
                        if response.status_code == 206:
                            content_range = response.headers.get('Content-Range', '')
                            if not content_range.startswith(f'bytes {offset}-') or not content_range.endswith(f'/{expected_size}'):
                                raise RuntimeError(f'Unexpected byte range for {name}')
                        elif offset:
                            offset = 0
                        mode = 'ab' if offset else 'wb'
                        downloaded = offset
                        next_report = offset + 256 * 2**20
                        with temporary.open(mode) as stream:
                            for block in response.iter_content(chunk_size=8 * 2**20):
                                stream.write(block)
                                downloaded += len(block)
                                if downloaded > expected_size:
                                    raise RuntimeError(f'Oversized encoder download: {name}')
                                if downloaded >= next_report:
                                    print('HTTP_PROGRESS:', name, downloaded, expected_size, flush=True)
                                    next_report = downloaded + 256 * 2**20
                except requests.RequestException as error:
                    print('HTTP_RETRY:', name, attempt + 1, type(error).__name__, flush=True)
                    time.sleep(min(2 ** attempt, 30))
                    continue
            if temporary.stat().st_size == expected_size and digest(temporary) == expected_hash:
                temporary.replace(destination)
                for backup in backups:
                    backup.unlink(missing_ok=True)
                print('HTTP_SHA256_VERIFIED:', name, expected_hash, flush=True)
                return
            print('HTTP_RETRY_HASH:', name, flush=True)
            # A damaged prefix must never become a model checkpoint.
            temporary.unlink(missing_ok=True)
        raise RuntimeError(f'Could not recover official encoder shard: {name}')

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(download, shards))
    os.environ['HF_HUB_DISABLE_XET'] = '1'
    prepare()


def serve():
    # This image's SGLang completeness check only recognizes conventional
    # weight suffixes. The actual transformer and encoder weights are GGUF
    # files passed through --component-weights-paths below.
    for component, source in [('transformer', DIT), ('text_encoder', ENCODER)]:
        if not source.is_file():
            raise FileNotFoundError(f'Missing {component} GGUF weights: {source}')
        component_dir = BASE / component
        component_dir.mkdir(exist_ok=True)
        link = component_dir / source.name
        if link.is_symlink() and link.resolve() != source:
            link.unlink()
        if not link.exists():
            link.symlink_to(source)
        if link.resolve() != source:
            raise RuntimeError(f'Unexpected {component} weight link: {link}')

    completeness_check = Path('/sgl-workspace/sglang/python/sglang/multimodal_gen/runtime/utils/hf_diffusers_utils.py')
    original = completeness_check.read_text()
    before = '    "*.ckpt",\n)\n'
    after = '    "*.ckpt",\n    "*.gguf",\n)\n'
    if before in original:
        if original.count(before) != 1:
            raise RuntimeError('Unexpected SGLang weight pattern layout')
        atomic_source_patch(completeness_check, original.replace(before, after, 1))
    elif after not in original:
        marker = original.find('_WEIGHT_FILE_PATTERNS')
        raise RuntimeError(f'SGLang weight pattern layout changed: path={completeness_check}, bytes={len(original)}, excerpt={original[marker:marker + 240]!r}')

    # The BF16-only fused-QKV fast path cannot read quantized layer weights.
    dit_source = completeness_check.parent.parent / 'models/dits/qwen_image21.py'
    original = dit_source.read_text()
    before = '        q, k, v = self.to_q.weight, self.to_k.weight, self.to_v.weight'
    after = ('        if not all(hasattr(layer, "weight") for layer in '
             '(self.to_q, self.to_k, self.to_v)):\n'
             '            return None\n' + before)
    if after not in original:
        if original.count(before) != 1:
            raise RuntimeError('SGLang QKV packing layout changed')
        atomic_source_patch(dit_source, original.replace(before, after, 1))

    command = ['sglang', 'serve', '--model-path', str(BASE), '--model-id', 'Qwen-Image-2.1',
               '--host', '0.0.0.0', '--port', '30010', '--attention-backend', 'torch_sdpa',
               '--component-weights-paths.transformer', str(DIT),
               '--component-weights-paths.text_encoder', str(ENCODER),
               '--performance-mode', 'manual', '--text-encoder-cpu-offload', 'true']
    print('SERVE:', ' '.join(command), flush=True)
    os.execvp(command[0], command)


def atomic_source_patch(path, content):
    temporary = path.with_suffix('.compat.tmp')
    temporary.write_text(content)
    if temporary.stat().st_size != len(content.encode()):
        raise RuntimeError(f'Incomplete compatibility write: {path}')
    temporary.replace(path)


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
    parser.add_argument('mode', choices=['prepare', 'repair_download', 'serve', 'verify'])
    mode = parser.parse_args().mode
    globals()[mode]()
