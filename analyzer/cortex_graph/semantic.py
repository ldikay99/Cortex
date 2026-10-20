"""Optional local semantic retrieval with static embeddings (model2vec).

Everything here is best effort: without the `semantic` extra, without the model or without network on first
use, `encoder()` returns None and recall keeps working in the deterministic lexical mode.
"""
import hashlib
import os
import threading
import time

import numpy as np

DEFAULT_MODEL = 'minishlab/potion-base-8M'
REVISIONS = {
    'minishlab/potion-retrieval-32M': '6fc8051fab2a1e0ee76689cf08c853792ac285e7',
    'minishlab/potion-base-8M': 'bf8b056651a2c21b8d2565580b8569da283cab23',
    'minishlab/potion-base-32M': '1e5a03f8eeb2c98b928fbbd846f22f816360919f',
    'minishlab/potion-multilingual-128M': '73908c3438cf03b6a01bcb9611d62b23d0726f08',
}
FILES = ['config.json', 'model.safetensors', 'tokenizer.json', 'modules.json']
OFF = frozenset({'', '0', 'off', 'none', 'no', 'false', 'lexical', 'lexico'})
RETRY = 600
FOLDER = 'embeddings'

lock = threading.Lock()
loaded = {}
failed = {}


def configured():
    raw = os.environ.get('CORTEX_EMBED_MODEL')
    raw = DEFAULT_MODEL if raw is None else raw.strip()
    return None if raw.lower() in OFF else raw


def parse(spec):
    repo, _, revision = spec.partition('@')
    return repo, revision or REVISIONS.get(repo)


class Encoder:
    def __init__(self, name, model):
        self.name = name
        self.model = model

    def __call__(self, texts):
        vectors = self.model.encode(list(texts), use_multiprocessing=False, show_progress_bar=False)
        vectors = np.asarray(vectors, dtype=np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.where(norms > 0, norms, 1)


def load(spec):
    from model2vec import StaticModel
    if os.path.isdir(spec):
        return Encoder(os.path.abspath(spec), StaticModel.from_pretrained(spec, force_download=False))
    repo, revision = parse(spec)
    from huggingface_hub import snapshot_download
    try:
        from huggingface_hub.utils import disable_progress_bars
        disable_progress_bars()
    except ImportError:
        pass
    try:
        path = snapshot_download(repo, revision=revision, allow_patterns=FILES, local_files_only=True)
    except Exception:
        path = snapshot_download(repo, revision=revision, allow_patterns=FILES)
    return Encoder(f'{repo}@{revision or "main"}', StaticModel.from_pretrained(path, force_download=False))


def encoder():
    spec = configured()
    if spec is None:
        return None
    with lock:
        if spec in loaded:
            return loaded[spec]
        if time.monotonic() - failed.get(spec, -RETRY) < RETRY:
            return None
        try:
            enc = load(spec)
        except Exception:
            failed[spec] = time.monotonic()
            return None
        loaded[spec] = enc
        return enc


def digest(name, fingerprint, texts):
    h = hashlib.sha256()
    for part in (name, str(fingerprint or '')):
        h.update(part.encode('utf-8', 'replace'))
        h.update(b'\0')
    for text in texts:
        h.update(text.encode('utf-8', 'replace'))
        h.update(b'\0')
    return h.hexdigest()[:32]


def vectors(enc, texts, folder, fingerprint=None):
    key = digest(enc.name, fingerprint, texts)
    path = os.path.join(folder, FOLDER, f'{key}.npy') if folder else None
    if path and os.path.isfile(path):
        try:
            cached = np.load(path, allow_pickle=False)
            if cached.shape[0] == len(texts):
                return cached.astype(np.float32)
        except (OSError, ValueError):
            pass
    out = np.concatenate([enc(texts[start:start + 4096]) for start in range(0, len(texts), 4096)]).astype(np.float16)
    if path:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = f'{path}.{os.getpid()}.tmp'
            with open(tmp, 'wb') as fh:
                np.save(fh, out, allow_pickle=False)
            os.replace(tmp, path)
            for old in os.listdir(os.path.dirname(path)):
                if old.endswith('.npy') and old != os.path.basename(path):
                    try:
                        os.remove(os.path.join(os.path.dirname(path), old))
                    except OSError:
                        pass
        except OSError:
            pass
    return out.astype(np.float32)


def attach(model, texts, folder, fingerprint=None):
    enc = encoder()
    if enc is None or not texts:
        return False
    try:
        model.attach(vectors(enc, texts, folder, fingerprint), enc)
    except Exception:
        return False
    return model.vectors is not None
