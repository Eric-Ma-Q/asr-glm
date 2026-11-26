
import torch
import torchaudio
import numpy as np
import io

def bytes_to_float32_tensor(audio_bytes: bytes) -> torch.Tensor:
    """
    Convert raw PCM bytes (int16 or float32) to a float32 tensor.
    Assumes incoming audio is 16kHz mono, 32-bit float or 16-bit int.
    Adjust based on frontend sending format.
    Here we assume frontend sends float32 (4 bytes per sample).
    """
    # Assuming float32 input from frontend
    audio_np = np.frombuffer(audio_bytes, dtype=np.float32)
    return torch.from_numpy(audio_np.copy())

def resample_audio(audio_tensor: torch.Tensor, orig_sr: int, target_sr: int) -> torch.Tensor:
    if orig_sr == target_sr:
        return audio_tensor
    resampler = torchaudio.transforms.Resample(orig_sr, target_sr)
    return resampler(audio_tensor)
