# 后端结构

本文档记录后端项目的结构和变更。

## 1. 目录结构
```text
asr-python/backend/
├── main.py          # FastAPI 应用入口 & WebSocket/REST 路由
├── model_loader.py  # GLM-ASR 模型加载与内存推理封装
├── audio_utils.py   # 音频数据转换工具 (Bytes -> Tensor)
├── tts_service.py   # GLM-TTS 语音克隆服务
├── requirements.txt # 依赖列表
├── recordings/      # 录音保存目录（自动创建）
└── tts_outputs/     # TTS 克隆音频输出目录（自动创建）
```

## 2. 变更记录

### 2.1 实时流式后端
基于 FastAPI 实现 WebSocket 接口，利用内存驻留模型进行实时转录。
- **入口**: `ws://localhost:8000/ws/transcribe`
- **逻辑**: 
    1. 接收前端 Float32 PCM 数据流。
    2. 缓存至 3秒 (可配置) 长度。
    3. 调用 `GLMASRModel` 进行推理。
    4. 返回文本。

更新: 2025-12-13

### 2.2 实时转录调优参数
列出关键参数以供调优参考：

#### 核心参数 (main.py)
- `CHUNK_DURATION_THRESHOLD`: 默认为 **3.0** 秒。
  - **影响**: 控制触发推理的缓冲时长。较小值提升实时性但可能降低准确率；较大值相反。

#### 模型参数 (model_loader.py)
- `WHISPER_FEAT_CFG['chunk_length']`: 默认 **30** 秒。Whisper 特征提取窗口。
- `max_new_tokens`: 默认 **128**。单次推理最大生成长度。
- `SAMPLE_RATE`: 固定 **16000** Hz。

更新: 2025-12-13

### 2.3 录音保存功能
支持在每次录音会话结束时保存音频为 WAV 文件。

#### 工作流程
1. 前端开始录音 → 发送 `{"type": "start"}` JSON 信号
2. 前端传输音频 → 发送 Float32 PCM 二进制数据
3. 前端停止录音 → 发送 `{"type": "stop"}` JSON 信号
4. 后端收到 stop → 保存累积音频为 WAV 文件

#### 文件存储
- **目录**: `asr-python/backend/recordings/`
- **文件名格式**: `recording_YYYYMMDD_HHMMSS.wav`
- **格式**: 16kHz、16-bit、单声道 WAV

#### 相关函数
- `save_recording(audio_data, sample_rate)`: 保存音频数据为 WAV 文件

更新: 2025-12-13

### 2.4 录音管理 REST API
提供录音列表管理功能。

#### 接口列表
| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/recordings` | 获取所有录音列表 |
| `GET` | `/api/recordings/{id}` | 获取单个录音详情 |
| `PUT` | `/api/recordings/{id}/prompt_text` | 更新录音的提示文本 |
| `DELETE` | `/api/recordings/{id}` | 删除录音 |

#### 静态文件服务
- `/audio/recordings/{filename}`: 访问原始录音文件
- `/audio/tts/{filename}`: 访问 TTS 克隆音频

#### 相关模块
- `tts_service.RecordingManager`: 录音元数据管理（自动扫描录音目录）
- `tts_service.Recording`: 录音数据结构

更新: 2025-12-13

### 2.5 GLM-TTS 语音克隆服务
集成 GLM-TTS 实现零样本语音克隆功能。

#### 核心模块
- **文件**: `tts_service.py`
- **类**: `TTSEngine` - TTS 模型加载与推理
- **类**: `RecordingManager` - 录音元数据管理

#### 接口列表
| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/tts/status` | 获取 TTS 引擎状态 |
| `POST` | `/api/tts/load` | 手动加载 TTS 模型 |
| `POST` | `/api/clone_voice` | 启动语音克隆任务（异步） |
| `GET` | `/api/clone_voice/{task_id}/progress` | 获取克隆任务进度 |

#### 克隆流程
1. 调用 `/api/clone_voice` 提交任务，返回 `task_id`
2. 轮询 `/api/clone_voice/{task_id}/progress` 获取进度
3. 完成后返回 `output_url` 可直接播放

#### 请求格式
```json
{
  "recording_id": "录音ID",
  "prompt_text": "录音中说的话（用于音色提取）",
  "syn_text": "要合成的新文本"
}
```

#### 依赖
- GLM-TTS 项目（仓库根目录下的 `GLM-TTS/`）
- 预训练模型（`GLM-TTS/ckpt/`）
- transformers==4.45.0（兼容性要求）

#### 硬件要求
- 显存: 8GB+ (推荐 12GB)
- GPU: NVIDIA RTX 3060 或更高

更新: 2025-12-13

### 2.6 克隆音频管理 API
提供克隆音频的独立管理接口。

#### 接口列表
| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/cloned_voices` | 获取所有克隆音频列表（扁平化） |
| `DELETE` | `/api/cloned_voices/{voice_id}` | 删除单个克隆音频 |

#### 响应格式
`GET /api/cloned_voices` 返回示例：
```json
{
  "cloned_voices": [
    {
      "id": "uuid",
      "filename": "clone_xxx.wav",
      "text": "合成的文本",
      "created_at": "2025-12-13T16:28:39",
      "source_recording": {
        "id": "recording_xxx",
        "filename": "recording_xxx.wav",
        "prompt_text": "原始录音的文本"
      }
    }
  ]
}
```

#### 说明
- 返回数据按创建时间倒序排列
- 每条克隆音频包含其来源录音的信息
- 删除克隆音频时会同时删除对应的 WAV 文件

更新: 2025-12-13

### 2.7 转写文本自动保存
录音保存时可同时保存转写文本。

#### 工作流程
1. 前端发送 `{"type": "stop", "transcript": "转写文本内容"}` 信号
2. 后端从信号中提取 `transcript` 字段
3. 调用 `save_recording(audio_data, sample_rate, transcript)` 保存录音和文本
4. 文本保存到录音的 `prompt_text` 字段

#### 相关函数
- `save_recording(audio_data, sample_rate, transcript)`: 新增 `transcript` 参数
- WebSocket `stop` 信号处理: 新增 `transcript` 字段解析

#### 数据结构
`Recording` 的 `prompt_text` 字段现在用于存储：
- 实时转写自动保存的文本
- 用户手动编辑的文本（通过 `PUT /api/recordings/{id}/prompt_text` 更新）

更新: 2025-12-13

