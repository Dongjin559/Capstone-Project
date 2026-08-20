from ollama import chat

IMAGE_PATH = r"C:\Users\user\Desktop\실제사진파일.jpg"

prompt = """
이 이미지를 보고 사람의 주요 활동을 분석해주세요.

다음 7가지 중 가장 적절한 행동 하나를 선택하세요.

1. 독서
2. PC 사용
3. 휴대폰 사용
4. 식사
5. 휴식
6. 이동
7. 기타

판단할 때 사람의 자세, 주변 물체, 손의 위치와 전체적인 상황을 종합적으로 고려하세요.

다음 형식으로 답변하세요.

활동: [하나의 활동]
근거: [판단한 이유를 한 문장으로 설명]
"""

response = chat(
    model="qwen2.5vl:3b",
    messages=[
        {
            "role": "user",
            "content": prompt,
            "images": [IMAGE_PATH]
        }
    ],
    options={
        "num_ctx": 8192
    }
)

print("\n========== Qwen2.5-VL 분석 결과 ==========\n")
print(response.message.content)