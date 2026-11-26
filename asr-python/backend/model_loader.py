import torch
from transformers import (
    AutoConfig,
    AutoModelForCausalLM,
    AutoTokenizer,
    WhisperFeatureExtractor,
)

# Config from inference.py
WHISPER_FEAT_CFG = {
    "chunk_length": 30,
    "feature_extractor_type": "WhisperFeatureExtractor",
    "feature_size": 128,
    "hop_length": 160,
    "n_fft": 400,
    "n_samples": 480000,
    "nb_max_frames": 3000,
    "padding_side": "right",
    "padding_value": 0.0,
    "processor_class": "WhisperProcessor",
    "return_attention_mask": False,
    "sampling_rate": 16000,
}

def get_audio_token_length(seconds, merge_factor=2):
    def get_T_after_cnn(L_in, dilation=1):
        for padding, kernel_size, stride in ((1, 3, 1), (1, 3, 2)):
            L_out = L_in + 2 * padding - dilation * (kernel_size - 1) - 1
            L_out = 1 + L_out // stride
            L_in = L_out
        return L_out
    
    mel_len = int(seconds * 100)
    audio_len_after_cnn = get_T_after_cnn(mel_len)
    audio_token_num = (audio_len_after_cnn - merge_factor) // merge_factor + 1
    audio_token_num = min(audio_token_num, 1500 // merge_factor)
    return audio_token_num

class GLMASRModel:
    def __init__(self, checkpoint_dir: str, device: str = None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.dtype = torch.bfloat16 if self.device == "cuda" and torch.cuda.is_bf16_supported() else torch.float32
        print(f"Loading model on {self.device}...")
        
        self.tokenizer = AutoTokenizer.from_pretrained(checkpoint_dir, trust_remote_code=True, local_files_only=True)
        self.feature_extractor = WhisperFeatureExtractor(**WHISPER_FEAT_CFG)
        
        self.config = AutoConfig.from_pretrained(checkpoint_dir, trust_remote_code=True, local_files_only=True)
        self.model = AutoModelForCausalLM.from_pretrained(
            checkpoint_dir,
            config=self.config,
            torch_dtype=self.dtype,
            trust_remote_code=True,
            local_files_only=True,
        ).to(self.device)
        self.model.eval()
        print("Model loaded.")

    def transcribe(self, audio_tensor: torch.Tensor, max_new_tokens=128):
        """
        audio_tensor: 1D Tensor (samples,) at 16000Hz
        """
        # Ensure audio is correct shape and ready
        if audio_tensor.dim() == 1:
            audio_tensor = audio_tensor.unsqueeze(0) # (1, samples)
        
        # Build prompt logic adapted from inference.py
        
        tokens = []
        tokens += self.tokenizer.encode("<|user|>")
        tokens += self.tokenizer.encode("\n")

        audios = []
        audio_offsets = []
        audio_length = []
        
        chunk_seconds = 30
        chunk_size = chunk_seconds * self.feature_extractor.sampling_rate
        
        wav = audio_tensor # (1, L)
        
        # Split into chunks
        for start in range(0, wav.shape[1], chunk_size):
            chunk = wav[:, start : start + chunk_size]
            mel = self.feature_extractor(
                chunk.numpy()[0], # pass 1D numpy array
                sampling_rate=self.feature_extractor.sampling_rate,
                return_tensors="pt",
                padding="max_length",
            )["input_features"]
            
            audios.append(mel)
            seconds = chunk.shape[1] / self.feature_extractor.sampling_rate
            num_tokens = get_audio_token_length(seconds, self.config.merge_factor)
            
            tokens += self.tokenizer.encode("<|begin_of_audio|>")
            audio_offsets.append(len(tokens))
            tokens += [0] * num_tokens
            tokens += self.tokenizer.encode("<|end_of_audio|>")
            audio_length.append(num_tokens)

        if not audios:
            return ""

        tokens += self.tokenizer.encode("<|user|>")
        tokens += self.tokenizer.encode("\nPlease transcribe this audio into text")
        tokens += self.tokenizer.encode("<|assistant|>")
        tokens += self.tokenizer.encode("\n")

        batch = {
            "input_ids": torch.tensor([tokens], dtype=torch.long),
            "audios": torch.cat(audios, dim=0),
            "audio_offsets": [audio_offsets],
            "audio_length": [audio_length],
            "attention_mask": torch.ones(1, len(tokens), dtype=torch.long),
        }
        
        # Prepare inputs
        input_ids = batch["input_ids"].to(self.device)
        attention_mask = batch["attention_mask"].to(self.device)
        audios_batch = batch["audios"].to(device=self.device, dtype=self.dtype)
        
        model_inputs = {
            "inputs": input_ids,
            "attention_mask": attention_mask,
            "audios": audios_batch,
            "audio_offsets": batch["audio_offsets"],
            "audio_length": batch["audio_length"],
        }
        
        prompt_len = input_ids.size(1)
        
        with torch.inference_mode():
            generated = self.model.generate(
                **model_inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
            )
            
        transcript_ids = generated[0, prompt_len:].cpu().tolist()
        transcript = self.tokenizer.decode(transcript_ids, skip_special_tokens=True).strip()
        
        return transcript

