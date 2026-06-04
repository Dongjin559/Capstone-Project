import json
import openai

# 1. API 키 설정
client = openai.OpenAI(api_key="sk-...") # 본인의 OpenAI API 키 입력

# 2. 데이터 불러오기
try:
    with open('data/final_log.json', 'r', encoding='utf-8') as f:
        log_data = json.load(f)
except FileNotFoundError:
    print("❌ final_log.json 파일이 없습니다.")
    exit()

# 3. 프롬프트 설정
prompt = f"""
당신은 사용자의 신체 활동과 디지털 기록을 바탕으로 라이프스타일을 분석해주는 조수입니다.
제공된 로그 데이터를 분석하여 다음 조건에 맞게 답변해주세요:
1. 오늘 보낸 시간을 3줄 요약.
2. 자세와 앱 사용의 상관관계 분석.
3. 친근하고 부드러운 톤의 조언.

[데이터]
{json.dumps(log_data, indent=2, ensure_ascii=False)}
"""

print(">> 🤖 GPT가 데이터를 분석 중입니다...")

try:
    # 4. GPT-4o-mini 호출
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    
    print("\n" + "="*50)
    print("✨ [GPT 분석 코멘트] ✨")
    print(response.choices[0].message.content.strip())
    print("="*50 + "\n")

except Exception as e:
    print(f"❌ 분석 오류: {e}")