import json
import requests
import time

# 1. API 키 설정 (본인의 키로 변경하세요)
GOOGLE_API_KEY = "AIzaSyD7Wtjh0Fbd-USOwi9sNrcW-ooLInSZcYc"

# 2. 데이터 불러오기
try:
    with open('data/final_log.json', 'r', encoding='utf-8') as f:
        log_data = json.load(f)
except FileNotFoundError:
    print("❌ final_log.json 파일이 없습니다. 병합 스크립트를 먼저 실행하세요.")
    exit()

# 3. AI에게 지시할 프롬프트 세팅
prompt = f"""
당신은 사용자의 신체 활동과 디지털 기록을 바탕으로 라이프스타일을 분석해주는 똑똑한 조수입니다.
아래 제공된 JSON 데이터는 사용자가 오늘 책상 앞에서 보낸 자세(SITTING, STANDING 등)와 
그 시간에 노트북으로 어떤 프로그램을 썼는지 기록한 통합 로그입니다.

이 데이터를 분석해서 다음 조건에 맞게 답변해주세요:
1. 사용자가 오늘 어떤 식으로 시간을 보냈는지 3줄 이내로 핵심만 요약할 것.
2. 자세와 노트북 사용(예: 코딩, 음악 감상, 웹서핑 등)의 상관관계를 가볍게 짚어줄 것.
3. 딱딱한 기계 말투가 아니라, 친근하고 부드러운 톤으로 조언이나 격려의 코멘트를 덧붙일 것.

[사용자 통합 로그 데이터]
{json.dumps(log_data, indent=2, ensure_ascii=False)}
"""

print(">> 🤖 AI가 데이터를 분석하고 있습니다. 잠시만 기다려주세요...")

# 4. REST API를 통한 호출 (서버 과부하 대비 재시도 로직 포함)
url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GOOGLE_API_KEY}"
headers = {"Content-Type": "application/json"}
payload = {"contents": [{"parts": [{"text": prompt}]}]}

max_retries = 3
success = False

for i in range(max_retries):
    try:
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code == 200:
            result = response.json()
            ai_message = result['candidates'][0]['content']['parts'][0]['text']
            
            print("\n" + "="*50)
            print("✨ [AI 분석 코멘트] ✨")
            print(ai_message.strip())
            print("="*50 + "\n")
            success = True
            break
        else:
            response.raise_for_status()
            
    except Exception as e:
        if i < max_retries - 1:
            print(f"⚠️ 서버가 바쁘네요... {i+1}번째 재시도 중입니다 (3초 대기)")
            time.sleep(3)
        else:
            print(f"❌ AI 분석 중 최종 오류가 발생했습니다: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"상세 에러: {e.response.text}")

if not success:
    print("시스템 분석을 완료하지 못했습니다.")