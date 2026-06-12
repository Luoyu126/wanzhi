import pyaudio
import json
from vosk import Model, KaldiRecognizer

model = Model("/home/pi/wanzhi/models/vosk-model")
recognizer = KaldiRecognizer(model, 16000)

p = pyaudio.PyAudio()

# 打印详细信息
print("所有输入设备：")
for i in range(p.get_device_count()):
    info = p.get_device_info_by_index(i)
    if info['maxInputChannels'] > 0:
        print(f"  {i}: {info['name']} (输入通道: {int(info['maxInputChannels'])})")

# 方式1：使用默认设备（去掉 input_device_index 参数）
stream = p.open(format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                frames_per_buffer=4000)

print("\n丸智已启动，说点什么...")

while True:
    data = stream.read(4000)
    if recognizer.AcceptWaveform(data):
        result = json.loads(recognizer.Result())
        text = result.get("text", "")
        if text:
            print(f"识别: {text}")