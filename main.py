import torch
import librosa
import numpy as np
from transformers import WhisperProcessor, WhisperForConditionalGeneration, AutomaticSpeechRecognitionPipeline

# 1. Load audio using librosa (doesn't require FFmpeg)
audio_path = "./VODs/【LNG】2015⧸06⧸28 我不是暴龍.mp4"
waveform, sample_rate = librosa.load(audio_path, sr=None)          

# 2. Preprocess
# librosa already returns mono audio, but let's ensure it's the right shape
if len(waveform.shape) > 1:
    waveform = np.mean(waveform, axis=0)

# Resample to 16kHz if needed
if sample_rate != 16_000:
    waveform = librosa.resample(waveform, orig_sr=sample_rate, target_sr=16_000)
    sample_rate = 16_000

# 3. Load Model
processor = WhisperProcessor.from_pretrained("MediaTek-Research/Breeze-ASR-25")
model = WhisperForConditionalGeneration.from_pretrained("MediaTek-Research/Breeze-ASR-25").to("cuda").eval()

# 4. Build Pipeline
asr_pipeline = AutomaticSpeechRecognitionPipeline(
    model=model,
    tokenizer=processor.tokenizer,
    feature_extractor=processor.feature_extractor,
    chunk_length_s=0
)

# 6. Inference
output = asr_pipeline(waveform, return_timestamps=True)  
print("Result:", output["text"])
