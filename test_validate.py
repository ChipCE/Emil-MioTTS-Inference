from elevenlab_endpoint.schemas import TTSRequestBody
import json

data = {
    "text":"hello",
    "model_id":"eleven_flash_v2_5",
    "voice_settings":{
        "stability":0.5,
        "similarity_boost":0.75,
        "style":0,
        "use_speaker_boost":True,
        "speed":1.0}
}
try:
    obj = TTSRequestBody.model_validate(data)
    print("Valid Pydantic v2!")
except Exception as e:
    print(f"Error v2: {e}")
