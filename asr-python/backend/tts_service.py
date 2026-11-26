# TTS Service - GLM-TTS 语音克隆服务
import os
import sys
import json
import torch
import soundfile
import asyncio
from typing import Optional, Callable, List, Dict
from datetime import datetime
from dataclasses import dataclass, asdict
from pathlib import Path
from tempfile import NamedTemporaryFile
import uuid
from model_setup import SPEAKER_ENCODER, TTS_FILES

# 添加 GLM-TTS 到路径
GLMTTS_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "GLM-TTS"))
sys.path.insert(0, GLMTTS_PATH)

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = Path(os.environ.get("GLM_ASR_DATA_DIR", BACKEND_DIR)).resolve()
RECORDINGS_DIR = str(DATA_DIR / "recordings")
TTS_OUTPUTS_DIR = str(DATA_DIR / "tts_outputs")

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


@dataclass
class Recording:
    """录音记录"""
    id: str
    filename: str
    filepath: str
    created_at: str
    duration: float  # 秒
    prompt_text: str = ""  # 录音内容文本
    cloned_audios: List[Dict] = None  # 克隆生成的音频列表
    source_filename: Optional[str] = None
    
    def __post_init__(self):
        if self.cloned_audios is None:
            self.cloned_audios = []


@dataclass
class ClonedAudio:
    """克隆生成的音频"""
    id: str
    filename: str
    filepath: str
    text: str  # 合成的文本
    created_at: str


class RecordingManager:
    """录音管理器"""
    
    def __init__(self):
        self.recordings_dir = RECORDINGS_DIR
        self.tts_outputs_dir = TTS_OUTPUTS_DIR
        self.metadata_file = os.path.join(RECORDINGS_DIR, "metadata.json")
        os.makedirs(self.recordings_dir, exist_ok=True)
        os.makedirs(self.tts_outputs_dir, exist_ok=True)
        self._load_metadata()
        
    def _load_metadata(self):
        """加载元数据"""
        if os.path.exists(self.metadata_file):
            with open(self.metadata_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.recordings = {
                    k: Recording(**v) for k, v in data.items()
                }
        else:
            self.recordings = {}
            # 扫描现有录音
            self._scan_existing_recordings()
            
    def _scan_existing_recordings(self):
        """扫描现有录音文件"""
        for filename in os.listdir(self.recordings_dir):
            if filename.endswith('.wav'):
                filepath = os.path.join(self.recordings_dir, filename)
                rec_id = filename.replace('.wav', '')
                
                # 获取音频时长
                try:
                    import wave
                    with wave.open(filepath, 'rb') as wf:
                        frames = wf.getnframes()
                        rate = wf.getframerate()
                        duration = frames / float(rate)
                except:
                    duration = 0
                    
                # 获取创建时间
                created_at = datetime.fromtimestamp(
                    os.path.getctime(filepath)
                ).isoformat()
                
                self.recordings[rec_id] = Recording(
                    id=rec_id,
                    filename=filename,
                    filepath=filepath,
                    created_at=created_at,
                    duration=duration
                )
        self._save_metadata()
                
    def _save_metadata(self):
        """保存元数据"""
        data = {}
        for k, v in self.recordings.items():
            rec_dict = asdict(v)
            data[k] = rec_dict
        metadata_path = Path(self.metadata_file)
        temp_file = NamedTemporaryFile(dir=metadata_path.parent, mode='w', encoding='utf-8', delete=False)
        temp_path = Path(temp_file.name)
        try:
            with temp_file as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            temp_path.replace(metadata_path)
        finally:
            temp_path.unlink(missing_ok=True)

    def add_recording(self, recording: Recording):
        self.recordings[recording.id] = recording
        try:
            self._save_metadata()
        except Exception:
            del self.recordings[recording.id]
            raise
            
    def get_all_recordings(self) -> List[Dict]:
        """获取所有录音"""
        return [asdict(r) for r in self.recordings.values()]
        
    def get_recording(self, rec_id: str) -> Optional[Recording]:
        """获取单个录音"""
        return self.recordings.get(rec_id)
        
    def update_prompt_text(self, rec_id: str, prompt_text: str):
        """更新录音的提示文本"""
        if rec_id in self.recordings:
            self.recordings[rec_id].prompt_text = prompt_text
            self._save_metadata()
            
    def add_cloned_audio(self, rec_id: str, cloned: ClonedAudio):
        """添加克隆音频记录"""
        if rec_id in self.recordings:
            self.recordings[rec_id].cloned_audios.append(asdict(cloned))
            self._save_metadata()
            
    def delete_recording(self, rec_id: str) -> bool:
        """删除录音"""
        if rec_id in self.recordings:
            rec = self.recordings[rec_id]
            # 删除原始录音文件
            if os.path.exists(rec.filepath):
                os.remove(rec.filepath)
            # 删除克隆的音频
            for cloned in rec.cloned_audios:
                if os.path.exists(cloned['filepath']):
                    os.remove(cloned['filepath'])
            del self.recordings[rec_id]
            self._save_metadata()
            return True
        return False


class TTSEngine:
    """GLM-TTS 语音合成引擎"""
    
    def __init__(self):
        self.frontend = None
        self.text_frontend = None
        self.llm = None
        self.flow = None
        self.sample_rate = 24000
        self.is_loaded = False

    def load_models(self, sample_rate: int = 24000, use_phoneme: bool = False, *, checkpoint_dir: Path | None = None):
        """加载 TTS 模型"""
        if self.is_loaded:
            return
        
        from cosyvoice.cli.frontend import TTSFrontEnd, SpeechTokenizer, TextFrontEnd
        from utils import tts_model_util, yaml_util
        from transformers import AutoTokenizer, LlamaForCausalLM
        from llm.glmtts import GLMTTS
        from utils.audio import mel_spectrogram
        from functools import partial
        from accelerate import init_empty_weights

        print("Loading GLM-TTS models...")
        self.sample_rate = sample_rate
        checkpoint_dir = checkpoint_dir or TTS_FILES.local_dir

        # Load Speech Tokenizer
        _model, _feature_extractor = yaml_util.load_speech_tokenizer(checkpoint_dir / "speech_tokenizer", DEVICE)
        speech_tokenizer = SpeechTokenizer(_model, _feature_extractor)

        # Load Frontends
        if sample_rate == 24000:
            feat_extractor = partial(
                mel_spectrogram, sampling_rate=sample_rate, hop_size=480,
                n_fft=1920, num_mels=80, win_size=1920, fmin=0, fmax=8000, center=False
            )
        else:
            raise ValueError(f"Unsupported sample_rate: {sample_rate}")

        glm_tokenizer = AutoTokenizer.from_pretrained(
            checkpoint_dir / "vq32k-phoneme-tokenizer", trust_remote_code=True, local_files_only=True
        )
        tokenize_fn = lambda text: glm_tokenizer.encode(text)

        self.frontend = TTSFrontEnd(
            tokenize_fn,
            speech_tokenizer,
            feat_extractor,
            str(SPEAKER_ENCODER),
            os.path.join(GLMTTS_PATH, "frontend", "spk2info.pt"),
            DEVICE,
        )
        normalizer_cache = DATA_DIR / "normalizer_cache"
        normalizer_cache.mkdir(parents=True, exist_ok=True)
        self.text_frontend = TextFrontEnd(use_phoneme, cache_dir=str(normalizer_cache))

        # Load LLM
        llama_path = checkpoint_dir / "llm"
        with init_empty_weights():
            self.llm = GLMTTS(
                llama_cfg_path=str(llama_path / "config.json"),
                mode="PRETRAIN",
                spk_prompt_dict_path=os.path.join(GLMTTS_PATH, "configs", "spk_prompt_dict.yaml"),
            )
        self.llm.llama = LlamaForCausalLM.from_pretrained(
            llama_path, torch_dtype=torch.float32, device_map={"": DEVICE}, local_files_only=True
        )
        self.llm.eval()
        self.llm.llama_embedding = self.llm.llama.model.embed_tokens

        special_token_ids = self._get_special_token_ids(tokenize_fn)
        self.llm.set_runtime_vars(special_token_ids=special_token_ids)

        # Load Flow
        flow_ckpt = checkpoint_dir / "flow" / "flow.pt"
        flow_config = checkpoint_dir / "flow" / "config.yaml"
        flow = yaml_util.load_flow_model(flow_ckpt, flow_config, DEVICE)
        self.flow = tts_model_util.Token2Wav(
            flow, sample_rate=sample_rate, device=DEVICE, hift_path=checkpoint_dir / "hift" / "hift.pt"
        )

        self.is_loaded = True
        print("GLM-TTS models loaded successfully!")
        
    def _get_special_token_ids(self, tokenize_fn):
        _special_token_ids = {
            "ats": "\u003c|audio_0|\u003e",
            "ate": "\u003c|audio_32767|\u003e",
            "boa": "\u003c|begin_of_audio|\u003e",
            "eoa": "\u003c|user|\u003e",
            "pad": "\u003c|endoftext|\u003e",
        }
        
        special_token_ids = {}
        endoftext_id = tokenize_fn("\u003c|endoftext|\u003e")[0]
        
        for k, v in _special_token_ids.items():
            __ids = tokenize_fn(v)
            if len(__ids) != 1:
                raise AssertionError(f"Token '{k}' ({v}) encoded to multiple tokens: {__ids}")
            if __ids[0] < endoftext_id:
                raise AssertionError(f"Token '{k}' ({v}) ID {__ids[0]} is smaller than endoftext ID {endoftext_id}")
            special_token_ids[k] = __ids[0]
            
        return special_token_ids
    
    @torch.inference_mode()
    def clone_voice(
        self, 
        prompt_speech_path: str,
        prompt_text: str,
        syn_text: str,
        output_path: str,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> str:
        """
        克隆语音
        
        Args:
            prompt_speech_path: 提示音频路径
            prompt_text: 提示音频对应的文本
            syn_text: 要合成的文本
            output_path: 输出文件路径
            progress_callback: 进度回调 (progress: 0-100, message: str)
            
        Returns:
            输出文件路径
        """
        if not self.is_loaded:
            raise RuntimeError("TTS models not loaded. Call load_models() first.")
            
        from utils import seed_util

        if progress_callback:
            progress_callback(10, "正在处理提示音频...")

        # 文本归一化
        prompt_text_norm = self.text_frontend.text_normalize(prompt_text)
        syn_text_norm = self.text_frontend.text_normalize(syn_text)

        if progress_callback:
            progress_callback(20, "正在提取语音特征...")

        # 提取特征
        prompt_text_token = self.frontend._extract_text_token(prompt_text_norm + " ")
        prompt_speech_token = self.frontend._extract_speech_token([prompt_speech_path])
        speech_feat = self.frontend._extract_speech_feat(prompt_speech_path, sample_rate=self.sample_rate)
        embedding = self.frontend._extract_spk_embedding(prompt_speech_path)

        cache_speech_token = [prompt_speech_token.squeeze().tolist()]
        flow_prompt_token = torch.tensor(cache_speech_token, dtype=torch.int32).to(DEVICE)

        if progress_callback:
            progress_callback(40, "正在生成语音...")

        # 初始化缓存
        cache = {
            "cache_text": [prompt_text_norm],
            "cache_text_token": [prompt_text_token],
            "cache_speech_token": cache_speech_token,
            "use_cache": True,
        }

        # 生成语音
        seed_util.set_seed(0)
        tts_speech = self._generate_speech(
            syn_text_norm,
            cache,
            embedding,
            flow_prompt_token,
            speech_feat,
            progress_callback
        )

        if progress_callback:
            progress_callback(90, "正在保存音频...")

        # 保存音频
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        soundfile.write(output_path, tts_speech.cpu().numpy().T, self.sample_rate)

        if progress_callback:
            progress_callback(100, "完成!")

        return output_path
    
    def _generate_speech(
        self,
        syn_text: str,
        cache: dict,
        embedding,
        flow_prompt_token,
        speech_feat,
        progress_callback: Optional[Callable] = None
    ):
        """生成语音的核心逻辑"""
        outputs = []
        short_text_list = self.text_frontend.split_by_len(syn_text)
        total_segments = len(short_text_list)
        
        for idx, tts_text in enumerate(short_text_list):
            tts_text_tn = self.text_frontend.text_normalize(tts_text)
            tts_text_token = self.frontend._extract_text_token(tts_text_tn)
            
            # 获取提示
            cache_text_token = cache["cache_text_token"]
            cache_speech_token = cache["cache_speech_token"]
            
            if len(cache_text_token) > 1:
                prompt_text_token, prompt_speech_token = self._get_cached_prompt(
                    cache, tts_text_token
                )
            else:
                prompt_text_token = cache_text_token[0].to(DEVICE)
                prompt_speech_token = torch.tensor(
                    [cache_speech_token[0]], dtype=torch.int32
                ).to(DEVICE)
            
            # LLM 推理
            token_list = self._llm_forward(
                prompt_text_token, tts_text_token, prompt_speech_token
            )
            
            # Flow 推理
            output = self._flow_forward(
                token_list, flow_prompt_token, speech_feat, embedding
            )
            
            # 更新缓存
            cache["cache_text"].append(tts_text_tn)
            cache["cache_text_token"].append(tts_text_token)
            cache["cache_speech_token"].append(token_list)
            
            outputs.append(output)
            
            if progress_callback:
                progress = 40 + int(50 * (idx + 1) / total_segments)
                progress_callback(progress, f"正在生成语音片段 {idx + 1}/{total_segments}...")
        
        return torch.cat(outputs, dim=1)
    
    def _get_cached_prompt(self, cache, synth_text_token):
        """从缓存构建提示"""
        MAX_SEQ_LEN = 750
        cache_text_token = cache["cache_text_token"]
        cache_speech_token = cache["cache_speech_token"]
        
        def __len_cache_speech_token():
            return sum(map(len, cache_speech_token))
        
        # 估计比例
        text_len = sum(t.shape[1] for t in cache_text_token)
        ta_ratio = __len_cache_speech_token() / (text_len if text_len > 0 else 1.0)
        
        synth_len_estim = int(ta_ratio * synth_text_token.shape[1])
        
        # 剪枝
        while __len_cache_speech_token() + synth_len_estim > MAX_SEQ_LEN:
            if len(cache_speech_token) <= 1:
                break
            cache["cache_text"].pop(1)
            cache_text_token.pop(1)
            cache_speech_token.pop(1)
        
        # 构建文本提示
        prompt_text_tokens = []
        for t in cache_text_token:
            prompt_text_tokens.extend(t.squeeze().tolist())
        prompt_text_token = torch.tensor([prompt_text_tokens]).to(DEVICE)
        
        # 构建语音提示
        speech_tokens = []
        for s in cache_speech_token:
            speech_tokens.extend(s)
        prompt_speech_token = torch.tensor([speech_tokens], dtype=torch.int32).to(DEVICE)
        
        return prompt_text_token, prompt_speech_token
    
    def _llm_forward(self, prompt_text_token, tts_text_token, prompt_speech_token):
        """LLM 前向推理"""
        def _get_len(token):
            assert token.ndim == 2 and token.shape[0] == 1
            return torch.tensor([token.shape[1]], dtype=torch.int32).to(token.device)
        
        tts_speech_token = self.llm.inference(
            text=tts_text_token,
            text_len=_get_len(tts_text_token),
            prompt_text=prompt_text_token,
            prompt_text_len=_get_len(prompt_text_token),
            prompt_speech_token=prompt_speech_token,
            prompt_speech_token_len=_get_len(prompt_speech_token),
            beam_size=1,
            sampling=30,  # 降低以提高稳定性 (原25)
            sample_method="ras",
            spk=None,
        )
        return tts_speech_token[0].tolist()
    
    def _flow_forward(self, token_list, prompt_speech_tokens, speech_feat, embedding):
        """Flow 前向推理"""
        wav, _ = self.flow.token2wav_with_cache(
            token_list,
            n_timesteps=20,  # 增加以提升音质 (原10)
            prompt_token=prompt_speech_tokens,
            prompt_feat=speech_feat,
            embedding=embedding,
        )
        return wav.detach().cpu()


# 全局实例
tts_engine = TTSEngine()
recording_manager = RecordingManager()
