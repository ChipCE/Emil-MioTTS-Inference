import wave
import io

def concatenate_wavs(wav_bytes_list: list[bytes]) -> bytes:
    if not wav_bytes_list:
        return b""
    if len(wav_bytes_list) == 1:
        return wav_bytes_list[0]
        
    out_buffer = io.BytesIO()
    with wave.open(out_buffer, 'wb') as out_wav:
        for i, wav_bytes in enumerate(wav_bytes_list):
            with wave.open(io.BytesIO(wav_bytes), 'rb') as in_wav:
                if i == 0:
                    out_wav.setparams(in_wav.getparams())
                out_wav.writeframes(in_wav.readframes(in_wav.getnframes()))
    return out_buffer.getvalue()

# We need some wav bytes to test
with open("test_jp.wav", "rb") as f:
    b = f.read()

res = concatenate_wavs([b, b])
print(len(b), len(res))
