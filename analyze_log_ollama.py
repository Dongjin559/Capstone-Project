import json
from openai import OpenAI

# 1. Ollama 연결 설정 (API 키는 로컬이므로 아무 값이나 넣어도 무관함)
client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

# 2. 데이터 불러오기
try:
    with open('final_log.json', 'r', encoding='utf-8') as f:
        log_data = json.load(f)
except FileNotFoundError:
    print("❌ final_log.json 파일이 없습니다. 병합 스크립트를 먼저 실행하세요.")
    exit()

# 3. 프롬프트 세팅
prompt = f"""
당신은 사용자의 데이터를 분석하는 똑똑한 AI 조수야.
아래 [데이터]를 보고, 시간과 활동 내용을 분석해줘.

[데이터 분석 규칙]
1. 프로그램 이름(Spotify, Advanced Home Cam AI 등)과 자세 상태값(SITTING, STANDING)은 데이터에 적힌 그대로 영어로 표기해.
2. '가다랭이' 같은 이상한 단어는 절대 쓰지 마. SITTING은 '앉아있는', STANDING은 '서 있는'으로 자연스럽게 해석해.
3. 말투는 편안한 한국어 구어체로 작성해.

[필수 작성 형식]
1. 시간과 활동 분석: 언제(시간대) 어떤 프로그램을 얼마나 사용했는지 구체적으로 설명해줘.
2. 자세와 습관: 데이터에 적힌 자세(SITTING/STANDING)를 사용하여 그 자세가 어떤 활동과 연결되는지 분석해줘.
3. 응원 한마디: 사용자의 오늘 하루를 격려하는 따뜻한 멘트를 남겨줘.

[데이터]
{json.dumps(log_data, indent=2, ensure_ascii=False)}
"""

print(">> 🤖 로컬 AI(gemma2)가 데이터를 분석 중입니다. 잠시만 기다려주세요...")

# 4. 분석 실행
try:
    response = client.chat.completions.create(
        model="gemma2", # 미리 다운로드한 모델명
        messages=[{"role": "user", "content": prompt}]
    )
    
    ai_message = response.choices[0].message.content
    
    print("\n" + "="*50)
    print("✨ [로컬 AI 분석 코멘트] ✨")
    print(ai_message.strip())
    print("="*50 + "\n")

except Exception as e:
    print(f"❌ 분석 중 오류가 발생했습니다: {e}")
    print("💡 팁: Ollama 프로그램이 실행 중인지, 'ollama run gemma2' 명령을 실행했는지 확인해주세요.")