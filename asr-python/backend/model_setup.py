"""Download the pinned model files and load the local runtime on demand."""

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import requests
from huggingface_hub import hf_hub_url, try_to_load_from_cache
from huggingface_hub.constants import HF_HUB_CACHE
from huggingface_hub.utils import WeakFileLock

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SPEAKER_ENCODER = PROJECT_ROOT / "GLM-TTS" / "frontend" / "campplus.onnx"


@dataclass(frozen=True)
class ModelAsset:
    path: Path
    url: str
    size: int
    sha256: str | None = None

    def present(self) -> bool:
        return self.path.is_file() and self.path.stat().st_size == self.size

    def download(self, progress: Callable[[int], None]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        partial = self.path.with_name(f".{self.path.name}.part")
        with WeakFileLock(str(partial) + ".lock"):
            if self.present():
                return
            offset = partial.stat().st_size if partial.is_file() else 0
            if offset > self.size:
                partial.unlink()
                offset = 0
            if offset < self.size:
                self._transfer(partial, offset, progress)
            if partial.stat().st_size != self.size:
                raise RuntimeError("模型文件下载不完整")
            if self.sha256:
                with partial.open("rb") as downloaded:
                    digest = hashlib.file_digest(downloaded, "sha256").hexdigest()
                if digest != self.sha256:
                    partial.unlink()
                    raise RuntimeError("模型文件 SHA-256 校验失败")
            partial.replace(self.path)

    def _transfer(self, partial: Path, offset: int, progress: Callable[[int], None]) -> None:
        headers = {"Accept-Encoding": "identity"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        with requests.get(self.url, headers=headers, stream=True, timeout=(15, 30)) as source:
            source.raise_for_status()
            if source.status_code == 200:
                offset = 0
            elif source.headers.get("Content-Range") != f"bytes {offset}-{self.size - 1}/{self.size}":
                raise RuntimeError("模型文件续传响应异常")
            progress(offset)
            with partial.open("ab" if offset else "wb") as target:
                for block in source.iter_content(1024 * 1024):
                    offset += len(block)
                    if offset > self.size:
                        raise RuntimeError("模型文件大小与发布清单不符")
                    target.write(block)
                    progress(offset)


@dataclass(frozen=True)
class ModelFiles:
    repo: str
    revision: str
    files: dict[str, int]
    local_dir: Path
    hashes: dict[str, str] = field(default_factory=dict)
    asset: ModelAsset | None = None

    @property
    def size(self) -> int:
        return sum(self.files.values()) + (self.asset.size if self.asset else 0)

    def download_files(self):
        for name, size in self.files.items():
            url = hf_hub_url(self.repo, name, revision=self.revision)
            yield name, ModelAsset(self.local_dir / name, url, size, self.hashes.get(name))
        if self.asset:
            yield self.asset.path.name, self.asset

    def installed_dir(self) -> Path | None:
        if self.asset and not self.asset.present():
            return None
        if all(
            (path := self.local_dir / name).is_file() and path.stat().st_size == size
            for name, size in self.files.items()
        ):
            return self.local_dir

        roots = set()
        for name, size in self.files.items():
            cached = try_to_load_from_cache(self.repo, name, revision=self.revision)
            if not isinstance(cached, str):
                return None
            path = Path(cached)
            if not path.is_file() or path.stat().st_size != size:
                return None
            roots.add(path.parents[len(Path(name).parts) - 1])
        return roots.pop() if len(roots) == 1 else None

    def download(self, progress: Callable[[str, int], None]) -> Path:
        done = 0
        for name, file in self.download_files():
            progress(name, done)
            if not file.present():
                file.download(lambda offset: progress(name, done + offset))
            done += file.size
            progress(name, done)
        installed = self.installed_dir()
        if installed is None:
            raise RuntimeError("模型文件不完整")
        return installed


# The native Transformers conversion changed the checkpoint layout in December 2025.
# This revision matches the bundled ASR adapter and existing local caches.
ASR_FILES = ModelFiles(
    "zai-org/GLM-ASR-Nano-2512",
    "91967eab799804ab256a3819a085b92378906eb2",
    {
        "chat_template.jinja": 334,
        "config.json": 3079,
        "configuration_glmasr.py": 1362,
        "modeling_audio.py": 18339,
        "modeling_glmasr.py": 5707,
        "tokenizer.json": 6834995,
        "tokenizer_config.json": 3779,
        "model.safetensors": 4524872840,
    },
    Path(HF_HUB_CACHE) / "asr-glm" / "GLM-ASR-Nano-2512-91967ea",
    {"model.safetensors": "f1a7e953150d134cce1a1199d6f18060cb99ee8a9d8e13673ff3bd840da0c096"},
)

TTS_FILES = ModelFiles(
    "zai-org/GLM-TTS",
    "b3feb691fa4cf590eec4418f6275f95220e58844",
    {
        "flow/config.yaml": 180,
        "flow/flow.pt": 901331642,
        "hift/hift.pt": 83390254,
        "llm/config.json": 674,
        "llm/generation_config.json": 111,
        "llm/model.safetensors.index.json": 20919,
        "llm/model-00001-of-00002.safetensors": 4999976928,
        "llm/model-00002-of-00002.safetensors": 1208089016,
        "speech_tokenizer/config.json": 1941,
        "speech_tokenizer/preprocessor_config.json": 340,
        "speech_tokenizer/model.safetensors": 1628135704,
        "vq32k-phoneme-tokenizer/tokenizer_config.json": 6368796,
        "vq32k-phoneme-tokenizer/tokenization_chatglm.py": 8990,
        "vq32k-phoneme-tokenizer/tokenizer.model": 1044856,
    },
    PROJECT_ROOT / "GLM-TTS" / "ckpt",
    {
        "flow/flow.pt": "532fb30348a9a8df727c8b4b142b3e7a272d5a4f2e2d7b70576c60662943b143",
        "hift/hift.pt": "3386cc880324d4e98e05987b99107f49e40ed925b8ecc87c1f4939432d429879",
        "llm/model-00001-of-00002.safetensors": "12adf2b0ea8be7a39ea5d5aa2d3658556602b1d979a382d41e3cd79b546d7b30",
        "llm/model-00002-of-00002.safetensors": "5f07a39df2aff4b4f5b68494d98584e4cc319fc7561d9823d6408979f25f5e32",
        "speech_tokenizer/model.safetensors": "78e3a3542b8e111a2ecb363056c643dafdef3624eacce3af587693421a55e38e",
        "vq32k-phoneme-tokenizer/tokenizer.model": "3c16309bf80bf496e823cad3a9e77967746d5f0ac55afd1755717ec9f9cc1ce0",
    },
    ModelAsset(
        SPEAKER_ENCODER,
        "https://raw.githubusercontent.com/zai-org/GLM-TTS/8c598f98ca5256b4efee37eb5d10a13c2a38af24/frontend/campplus.onnx",
        28303423,
        "a6ac6a63997761ae2997373e2ee1c47040854b4b759ea41ec48e4e42df0f4d73",
    ),
)


class ModelSetup:
    def __init__(self, files: ModelFiles, load: Callable[[Path], None]):
        self.files = files
        self.load = load
        self.task: asyncio.Task | None = None
        self.progress = ("", 0)
        self.state = "idle"
        self.error = None

    def status(self) -> dict:
        filename, done = self.progress
        installed = self.state in {"loading", "ready"} or self.files.installed_dir() is not None
        state = "installed" if installed and self.state == "idle" else self.state
        return {
            "state": state,
            "installed": installed,
            "file": filename,
            "downloaded_bytes": self.files.size if installed else done,
            "total_bytes": self.files.size,
            "error": self.error,
        }

    def start(self) -> None:
        if self.state == "ready" or (self.task and not self.task.done()):
            return
        self.error = None
        self.state = "loading" if self.files.installed_dir() else "downloading"
        self.task = asyncio.create_task(self._prepare())

    def _download_progress(self, name: str, done: int) -> None:
        self.progress = (name, done)

    async def _prepare(self) -> None:
        try:
            path = self.files.installed_dir()
            if path is None:
                path = await asyncio.to_thread(self.files.download, self._download_progress)
            self.state = "loading"
            await asyncio.to_thread(self.load, path)
            self.state = "ready"
        except Exception as exc:
            logger = logging.getLogger(__name__)
            if self.state == "downloading":
                logger.error("Model download failed for %s (%s)", self.files.repo, type(exc).__name__)
                self.error = "下载失败，请检查网络、可用磁盘空间和目录权限后重试。"
            else:
                logger.exception("Model load failed for %s", self.files.repo)
                self.error = str(exc).splitlines()[0] if str(exc).strip() else type(exc).__name__
            self.state = "error"
