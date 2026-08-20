from ollama import chat
from PIL import Image
import io

# 실제 사진 경로로 수정
IMAGE_PATH = r"C:\Users\user\OneDrive\Desktop\reading.jpg"

# 이미지 열기 및 크기 조절
image = Image.open(IMAGE_PATH)

# 너무 큰 이미지는 축소
image.thumbnail((1024, 1024))

# JPEG 형식의 바이트 데이터로 변환
buffer = io.BytesIO()
image.convert("RGB").save(buffer, format="JPEG")
image_bytes = buffer.getvalue()

print(">> 이미지 불러오기 성공")
print(f">> 이미지 크기: {image.size}")

# Qwen2.5-VL 분석
response = chat(
    model="qwen2.5vl-8k",
    messages=[
        {
            "role": "user",
            "content": "이 이미지를 보고 무엇이 보이는지 아주 짧게 설명해주세요.",
            "images": [image_bytes]
        }
    ],
    options={
        "num_ctx": 8192,
        "temperature": 0.2
    }
)

print("\n========== Qwen2.5-VL 분석 결과 ==========\n")
print(response.message.content)