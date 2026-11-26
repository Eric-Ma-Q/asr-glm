# GLM-ASR 本地语音工作台

在浏览器录音、实时转写、管理音频和克隆语音。模型首次使用时可在页面下载，之后可以离线推理。录音、转写和生成的音频保存在本机。

## Windows 和 macOS 安装

- Windows 10/11 x64，支持 CPU 和配置了 CUDA 的 NVIDIA GPU
- macOS 14 或更新版本，Apple Silicon（M 系列），使用 CPU 推理。Intel Mac 和 Metal 加速尚未验证。
- 需要 Git、[Miniforge](https://github.com/conda-forge/miniforge) 和 Node.js 22.12+。Windows 请从 Miniforge Prompt 运行 Conda 命令。
- 两个模型下载合计约 13.4 GB。若同时使用两个模型，建议准备 32 GB 以上内存和至少 20 GB 可用磁盘空间。CPU 上语音克隆可能需要较长时间。

以下命令适用于两种系统。

```sh
git clone https://github.com/Eric-Ma-Q/asr-glm.git
cd asr-glm
conda create -n asr-glm -c conda-forge python=3.11 pynini=2.1.5 ffmpeg
conda activate asr-glm
python -m pip install -r asr-python/backend/requirements.txt
npm --prefix asr-python/frontend ci
npm --prefix asr-python/frontend run build
python asr-python/backend/main.py
```

在浏览器打开 [127.0.0.1:8000](http://127.0.0.1:8000)。应用监听本机回环地址。停止时，在启动终端按 Ctrl+C。

如果 npm 的 `os` 或 `cpu` 被配置为其他平台，可在安装时显式覆盖。例如 Windows x64 使用 `npm --prefix asr-python/frontend ci --os=win32 --cpu=x64`。

Windows 如需启用 NVIDIA CUDA，可在安装项目依赖前，从 [PyTorch 2.9.1 官方安装指引](https://pytorch.org/get-started/previous-versions/#v291) 选择与驱动匹配的 CUDA 版本，先安装同版本的 `torch` 和 `torchaudio`。

## 下载与使用

| 模型 | 用途 | 下载量 |
| --- | --- | --- |
| GLM-ASR-Nano-2512 | 实时转录 | 约 4.5 GB |
| GLM-TTS | 语音克隆 | 约 8.9 GB |

1. 在首页或「模型管理」点击对应模型的「一键下载」。可按需下载其中一个。页面会显示当前文件、下载进度和加载状态。
2. 模型完成加载后，进入「实时转录」并允许浏览器使用麦克风。点击停止后，录音和转写会出现在「录音管理」。
3. 克隆语音时，先加载 GLM-TTS，再选择一段你拥有使用权限的录音，填写录音对应的原文和要生成的文本。
4. 下载中断后点击「重试」，可复用已完成的文件并续传未完成的文件。重启后点击「加载模型」即可复用本机缓存。

ASR 权重进入 Hugging Face 缓存的 `asr-glm/` 子目录，可用 `HF_HOME` 指定缓存位置。TTS 权重保存在 `GLM-TTS/ckpt/`，说话人编码器保存在 `GLM-TTS/frontend/campplus.onnx`。已有兼容文件可直接复用。下载来源为 Hugging Face 和 GLM-TTS 的上游 GitHub 仓库，下载完成后程序会校验权重的 SHA-256。

录音及其转写存在 `asr-python/backend/recordings/`，合成音频存在 `asr-python/backend/tts_outputs/`。可以用 `GLM_ASR_DATA_DIR` 指定另一处存储位置。Git 忽略这些数据目录、音频和模型文件。

## 模型版本

- 截至 2026-11-26，Z.ai 公开发布的 ASR 模型仍为 GLM-ASR-Nano-2512。2025 年 12 月原生 Transformers 适配更换了 checkpoint 布局，2026 年 4 月补充了评测。本项目固定到兼容现有转写适配器的官方修订版 `91967ea`。[ASR 发布历史](https://huggingface.co/zai-org/GLM-ASR-Nano-2512/commits/main)
- GLM-TTS 使用官方修订版 `b3feb69`。本项目让语音分词器、音频特征提取和 vocoder 走同一设备路径，macOS 使用 CPU。[TTS 发布历史](https://huggingface.co/zai-org/GLM-TTS/commits/main)
- Apple Silicon 另有社区维护的 ASR MLX 量化版，可在独立的 MLX 工具中使用。[GLM-ASR-Nano-2512 MLX 4-bit](https://huggingface.co/mlx-community/GLM-ASR-Nano-2512-4bit)

## 开发与测试

前端热更新可运行 `npm --prefix asr-python/frontend run dev`，另开终端启动后端，开发页通过 Vite 代理连到本机后端。

```sh
python -m pip install httpx
python -m unittest discover -s asr-python/backend/tests -v
npm --prefix asr-python/frontend run lint
```

上游代码与许可证保留在 [GLM-ASR](GLM-ASR/LICENSE) 和 [GLM-TTS](GLM-TTS/LICENSE) 目录。上游示例音频可从各自的源码仓库获取。
