
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn
import asyncio
import numpy as np
import torch
from torchaudio.transforms import Resample
import os
import sys
import wave
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import BinaryIO, Optional, List
from urllib.parse import urlsplit
import uuid

# Add project root to sys.path to ensure modules can be imported if needed
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from model_setup import ASR_FILES, TTS_FILES, PROJECT_ROOT, ModelSetup
from model_loader import GLMASRModel
from audio_utils import bytes_to_float32_tensor
from tts_service import tts_engine, recording_manager, Recording, ClonedAudio, RECORDINGS_DIR, TTS_OUTPUTS_DIR


# Silero VAD
from silero_vad import load_silero_vad, get_speech_timestamps

# Global instances
model_instance = None
vad_model = None
asr_lock = asyncio.Lock()
clone_lock = asyncio.Lock()

def save_recording(audio_data: np.ndarray, sample_rate: int = 16000, transcript: str = "") -> str:
    """保存录音为WAV文件
    
    Args:
        audio_data: 音频数据
        sample_rate: 采样率
        transcript: 转写文本（可选）
    """
    os.makedirs(RECORDINGS_DIR, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"recording_{timestamp}_{uuid.uuid4().hex[:8]}.wav"
    filepath = os.path.join(RECORDINGS_DIR, filename)
    
    # 转换为16位整数
    audio_int16 = (audio_data * 32767).astype(np.int16)
    
    with wave.open(filepath, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())
    
    # 计算音频时长
    duration = len(audio_data) / sample_rate
    
    # 注册到录音管理器
    rec_id = filename.replace('.wav', '')
    recording = Recording(
        id=rec_id,
        filename=filename,
        filepath=filepath,
        created_at=datetime.now().isoformat(),
        duration=duration,
        prompt_text=transcript.strip()  # 保存转写文本
    )
    try:
        recording_manager.add_recording(recording)
    except Exception:
        Path(filepath).unlink(missing_ok=True)
        raise
    
    print(f"Recording saved: {filepath}")
    return filepath

def load_asr(checkpoint: Path):
    global model_instance, vad_model
    vad_model = load_silero_vad()
    model_instance = GLMASRModel(str(checkpoint))


model_setups = {
    "asr": ModelSetup(ASR_FILES, load_asr),
    "tts": ModelSetup(TTS_FILES, lambda path: tts_engine.load_models(checkpoint_dir=path)),
}
app = FastAPI()
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])


def same_origin(headers) -> bool:
    origin = headers.get("origin")
    return not origin or urlsplit(origin).netloc == headers.get("host")


@app.middleware("http")
async def check_local_origin(request, call_next):
    if request.method not in {"GET", "HEAD", "OPTIONS"} and not same_origin(request.headers):
        return JSONResponse({"detail": "请从本地应用页面操作。"}, status_code=403)
    return await call_next(request)


@app.get("/api/models")
async def get_models():
    return {name: setup.status() for name, setup in model_setups.items()}


@app.post("/api/models/{name}/prepare", status_code=202)
async def prepare_model(name: str):
    setup = model_setups.get(name)
    if setup is None:
        raise HTTPException(status_code=404, detail="未知模型")
    setup.start()
    return setup.status()


async def transcribe(tensor: torch.Tensor) -> str:
    async with asr_lock:
        return await run_in_threadpool(model_instance.transcribe, tensor)

@app.websocket("/ws/transcribe")
async def websocket_endpoint(websocket: WebSocket):
    if not same_origin(websocket.headers):
        await websocket.close(code=1008)
        return
    if model_setups["asr"].state != "ready":
        await websocket.close(code=1013)
        return
    await websocket.accept()
    print("Client connected")
    
    SAMPLE_RATE = 16000
    recording_buffer = []  # 用于保存完整录音
    
    # VAD 参数
    MIN_CHUNK_DURATION = 2.0      # 最小触发时长（秒）
    MAX_CHUNK_DURATION = 8.0      # 最大触发时长（秒），超过强制转录
    SILENCE_THRESHOLD = 0.5       # 静音持续时长（秒）触发转录
    
    MIN_SAMPLES = int(MIN_CHUNK_DURATION * SAMPLE_RATE)
    MAX_SAMPLES = int(MAX_CHUNK_DURATION * SAMPLE_RATE)
    SILENCE_SAMPLES = int(SILENCE_THRESHOLD * SAMPLE_RATE)
    
    audio_buffer = []
    transcript_parts = []
    silence_counter = 0  # 连续静音帧计数
    resampler = None
    
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                raise WebSocketDisconnect(message.get("code", 1000))
            
            # 处理JSON控制信号
            if "text" in message:
                try:
                    control = json.loads(message["text"])
                    if control.get("type") == "start":
                        rate = control.get("sample_rate", SAMPLE_RATE)
                        if not isinstance(rate, int) or not 8000 <= rate <= 192000:
                            await websocket.close(code=1003)
                            return
                        resampler = Resample(rate, SAMPLE_RATE) if rate != SAMPLE_RATE else None
                        print("Recording started")
                        recording_buffer = []
                        audio_buffer = []
                        transcript_parts = []
                        silence_counter = 0
                        continue
                    elif control.get("type") == "stop":
                        print("Recording stopped")
                        if recording_buffer:
                            tail = await transcribe(torch.cat(audio_buffer)) if audio_buffer else ""
                            if tail:
                                transcript_parts.append(tail)
                            full_audio = torch.cat(recording_buffer).numpy()
                            save_recording(full_audio, SAMPLE_RATE, " ".join(transcript_parts))
                            recording_buffer = []
                            audio_buffer = []
                            if tail:
                                await websocket.send_text(tail)
                        await websocket.send_json({"type": "stopped"})
                        continue
                except json.JSONDecodeError:
                    pass
            
            # 处理二进制音频数据
            if message.get("bytes"):
                data = message["bytes"]
                tensor_chunk = bytes_to_float32_tensor(data)
                if resampler is not None:
                    tensor_chunk = resampler(tensor_chunk)
                audio_buffer.append(tensor_chunk)
                recording_buffer.append(tensor_chunk)  # 累积用于保存
                
                current_tensor = torch.cat(audio_buffer)
                current_samples = current_tensor.numel()
                
                # 使用 VAD 检测当前 chunk 是否有语音
                # VAD 期望输入为 (samples,) 且值在 [-1, 1]
                chunk_for_vad = tensor_chunk.clone()
                if chunk_for_vad.abs().max() > 0:
                    chunk_for_vad = chunk_for_vad / chunk_for_vad.abs().max()
                
                # 检测语音活动
                speech_timestamps = get_speech_timestamps(
                    chunk_for_vad, 
                    vad_model,
                    sampling_rate=SAMPLE_RATE,
                    threshold=0.5,
                    min_silence_duration_ms=100,
                    min_speech_duration_ms=50
                )
                
                has_speech = len(speech_timestamps) > 0
                
                if has_speech:
                    silence_counter = 0
                else:
                    silence_counter += tensor_chunk.numel()
                
                # 触发转录条件：
                # 1. 累积超过最小时长 且 检测到静音超过阈值
                # 2. 或累积超过最大时长（强制转录）
                should_transcribe = False
                
                if current_samples >= MIN_SAMPLES and silence_counter >= SILENCE_SAMPLES:
                    should_transcribe = True
                    print(f"Trigger: silence detected ({silence_counter/SAMPLE_RATE:.2f}s)")
                elif current_samples >= MAX_SAMPLES:
                    should_transcribe = True
                    print(f"Trigger: max duration reached ({current_samples/SAMPLE_RATE:.2f}s)")
                
                if should_transcribe:
                    print(f"Transcribing {current_samples/SAMPLE_RATE:.2f}s audio...")
                    text = await transcribe(current_tensor)
                    
                    if text:
                        transcript_parts.append(text)
                        await websocket.send_text(text)
                    
                    audio_buffer = []
                    silence_counter = 0
                
    except WebSocketDisconnect:
        print("Client disconnected")
        # 客户端断开时也保存录音
        if recording_buffer:
            full_audio = torch.cat(recording_buffer).numpy()
            save_recording(full_audio, SAMPLE_RATE, " ".join(transcript_parts))
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        await websocket.close()


# ============== TTS 相关 API ==============

class CloneVoiceRequest(BaseModel):
    """语音克隆请求"""
    recording_id: str
    prompt_text: str
    syn_text: str


class UpdatePromptTextRequest(BaseModel):
    """更新提示文本请求"""
    prompt_text: str


# 挂载静态文件目录
app.mount("/audio/recordings", StaticFiles(directory=RECORDINGS_DIR), name="recordings")
app.mount("/audio/tts", StaticFiles(directory=TTS_OUTPUTS_DIR), name="tts_outputs")


@app.get("/api/recordings")
async def get_recordings():
    """获取所有录音列表"""
    recordings = recording_manager.get_all_recordings()
    return {"recordings": recordings}


IMPORT_FORMATS = {
    ".wav": "wav", ".mp3": "mp3", ".m4a": "mov", ".mp4": "mov", ".aac": "aac",
    ".amr": "amr", ".flac": "flac", ".ogg": "ogg", ".webm": "matroska",
}
MAX_IMPORT_BYTES = 32 * 1024 * 1024
MAX_IMPORT_SECONDS = 300


def decode_imported_audio(source: BinaryIO, input_format: str, output_path: Path) -> float:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise HTTPException(status_code=503, detail="服务端未找到 FFmpeg，暂时无法导入音频。")

    input_path = output_path.with_name("source")
    with input_path.open("wb") as target:
        shutil.copyfileobj(source, target)

    try:
        subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
             "-protocol_whitelist", "file", "-f", input_format, "-i", str(input_path),
             "-map", "0:a:0", "-map_metadata", "-1", "-ac", "1", "-ar", "24000",
             "-c:a", "pcm_s16le", "-t", str(MAX_IMPORT_SECONDS + 1), str(output_path)],
            check=True, timeout=45, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=422, detail="无法读取音轨，请确认文件可播放且有声音。") from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=422, detail="音频转换超时，请裁剪后再导入。") from exc

    with wave.open(str(output_path), "rb") as audio:
        duration = audio.getnframes() / audio.getframerate()
    if not duration or duration > MAX_IMPORT_SECONDS:
        raise HTTPException(status_code=422, detail="请导入时长大于 0 且不超过 5 分钟的音频。")
    return duration


@app.post("/api/recordings", status_code=201)
async def import_recording(file: UploadFile):
    source_filename = Path((file.filename or "").replace("\\", "/")).name
    input_format = IMPORT_FORMATS.get(Path(source_filename).suffix.lower())
    if not input_format:
        raise HTTPException(status_code=415, detail="支持 WAV、MP3、M4A、MP4、AAC、AMR、FLAC、OGG 和 WebM。")
    if file.size is not None and file.size > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="音频文件最多 32 MB。")

    recording_dir = Path(recording_manager.recordings_dir)
    recording_id = f"imported_{uuid.uuid4().hex}"
    filepath = recording_dir / f"{recording_id}.wav"
    with TemporaryDirectory(prefix=".audio-import-", dir=recording_dir.parent) as directory:
        decoded_path = Path(directory) / "recording.wav"
        duration = await run_in_threadpool(decode_imported_audio, file.file, input_format, decoded_path)
        recording = Recording(
            id=recording_id,
            filename=filepath.name,
            filepath=str(filepath),
            created_at=datetime.now().isoformat(),
            duration=duration,
            source_filename=source_filename,
        )
        decoded_path.replace(filepath)
        try:
            recording_manager.add_recording(recording)
        except Exception:
            filepath.unlink(missing_ok=True)
            raise
    return recording


@app.get("/api/recordings/{recording_id}")
async def get_recording(recording_id: str):
    """获取单个录音详情"""
    recording = recording_manager.get_recording(recording_id)
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")
    return recording


@app.put("/api/recordings/{recording_id}/prompt_text")
async def update_prompt_text(recording_id: str, request: UpdatePromptTextRequest):
    """更新录音的提示文本"""
    recording = recording_manager.get_recording(recording_id)
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")
    recording_manager.update_prompt_text(recording_id, request.prompt_text)
    return {"success": True}


@app.delete("/api/recordings/{recording_id}")
async def delete_recording(recording_id: str):
    """删除录音"""
    success = recording_manager.delete_recording(recording_id)
    if not success:
        raise HTTPException(status_code=404, detail="Recording not found")
    return {"success": True}


# 存储克隆任务的进度
clone_tasks_progress = {}


@app.post("/api/clone_voice")
async def clone_voice(request: CloneVoiceRequest):
    """启动语音克隆任务"""
    recording = recording_manager.get_recording(request.recording_id)
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")
    
    # 检查 TTS 模型是否已加载
    if not tts_engine.is_loaded:
        raise HTTPException(status_code=503, detail="TTS model not loaded. Please wait for initialization.")
    
    # 生成任务 ID
    task_id = str(uuid.uuid4())
    clone_tasks_progress[task_id] = {"progress": 0, "message": "准备中...", "status": "running"}
    
    # 启动异步任务
    asyncio.create_task(_run_clone_task(
        task_id,
        request.recording_id,
        recording.filepath,
        request.prompt_text,
        request.syn_text
    ))
    
    return {"task_id": task_id}


async def _run_clone_task(task_id: str, recording_id: str, prompt_speech_path: str, prompt_text: str, syn_text: str):
    """执行语音克隆任务"""
    try:
        # 生成输出路径
        output_filename = f"clone_{recording_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
        output_path = os.path.join(TTS_OUTPUTS_DIR, output_filename)
        
        def progress_callback(progress: int, message: str):
            clone_tasks_progress[task_id] = {
                "progress": progress,
                "message": message,
                "status": "running"
            }
        
        # 在线程池中运行（因为 TTS 推理是同步的）
        async with clone_lock:
            await run_in_threadpool(
                tts_engine.clone_voice,
                prompt_speech_path,
                prompt_text,
                syn_text,
                output_path,
                progress_callback,
            )
        
        # 保存克隆音频记录
        cloned = ClonedAudio(
            id=str(uuid.uuid4()),
            filename=output_filename,
            filepath=output_path,
            text=syn_text,
            created_at=datetime.now().isoformat()
        )
        recording_manager.add_cloned_audio(recording_id, cloned)
        
        clone_tasks_progress[task_id] = {
            "progress": 100,
            "message": "完成!",
            "status": "completed",
            "output_url": f"/audio/tts/{output_filename}",
            "cloned_audio": {
                "id": cloned.id,
                "filename": cloned.filename,
                "text": cloned.text,
                "created_at": cloned.created_at
            }
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        clone_tasks_progress[task_id] = {
            "progress": 0,
            "message": str(e),
            "status": "error"
        }


@app.get("/api/clone_voice/{task_id}/progress")
async def get_clone_progress(task_id: str):
    """获取克隆任务进度"""
    if task_id not in clone_tasks_progress:
        raise HTTPException(status_code=404, detail="Task not found")
    return clone_tasks_progress[task_id]


@app.get("/api/cloned_voices")
async def get_cloned_voices():
    """获取所有克隆音频列表（扁平化）"""
    result = []
    for recording in recording_manager.get_all_recordings():
        if recording.get("cloned_audios"):
            for cloned in recording["cloned_audios"]:
                result.append({
                    "id": cloned["id"],
                    "filename": cloned["filename"],
                    "text": cloned["text"],
                    "created_at": cloned["created_at"],
                    "source_recording": {
                        "id": recording["id"],
                        "filename": recording["filename"],
                        "prompt_text": recording.get("prompt_text", "")
                    }
                })
    # 按创建时间倒序
    result.sort(key=lambda x: x["created_at"], reverse=True)
    return {"cloned_voices": result}


@app.delete("/api/cloned_voices/{voice_id}")
async def delete_cloned_voice(voice_id: str):
    """删除单个克隆音频"""
    for rec_id, recording in recording_manager.recordings.items():
        for i, cloned in enumerate(recording.cloned_audios):
            if cloned["id"] == voice_id:
                # 删除文件
                filepath = cloned.get("filepath")
                if filepath and os.path.exists(filepath):
                    os.remove(filepath)
                # 从列表移除
                recording.cloned_audios.pop(i)
                recording_manager._save_metadata()
                return {"success": True}
    raise HTTPException(status_code=404, detail="Cloned voice not found")


@app.get("/api/tts/status")
async def get_tts_status():
    """获取 TTS 引擎状态"""
    return {
        "loaded": tts_engine.is_loaded,
        "device": str(tts_engine.flow.device if tts_engine.is_loaded else "N/A")
    }


@app.post("/api/tts/load")
async def load_tts_model():
    """加载 TTS 模型"""
    setup = model_setups["tts"]
    setup.start()
    if setup.task is not None:
        await asyncio.shield(setup.task)
    if setup.state != "ready":
        raise HTTPException(status_code=500, detail=setup.error)
    return {"success": True, "message": "Model loaded successfully"}


FRONTEND_DIST = PROJECT_ROOT / "asr-python" / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)

