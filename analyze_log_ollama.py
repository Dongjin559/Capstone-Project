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
당신은 사용자의 일상 로그(자세 비전 데이터 + PC 앱 사용 기록)를 분석하여 라이프스타일 인사이트를 제공하는 전문적이고 따뜻한 AI 코치입니다.
아래 [데이터]를 보고, 분석 규칙에 따라 사용자의 하루를 분석해 주세요.

[데이터 분석 규칙]
1. 용어 유지: 프로그램 이름(예: VS Code, Chrome, Advanced Home Cam AI)과 자세 상태값(SITTING, STANDING 등)은 영문 그대로 표기하세요.
2. 자연스러운 번역: '가다랭이' 같은 기계적인 오역은 절대 금지합니다. 'SITTING'은 '앉아서', 'STANDING'은 '서서' 등 문맥에 맞게 자연스럽게 해석하세요.
3. 어색한 시간 표현 금지: "낮은 시각" 등 번역기 같은 표현 대신 "오후 8시경", "늦은 밤"처럼 사람이 쓰는 자연스러운 시간대 명칭을 사용하세요.
4. 맥락 추론: 창 제목(Title) 데이터를 적극 활용하세요. 예를 들어 VS Code나 문서 창이 띄워져 있다면 '개발 및 학업'으로, 유튜브 음악이 틀어져 있다면 '작업용 BGM 또는 휴식'으로 상황을 똑똑하게 추론하세요.
5. 어조: 분석 내용은 전문적이되, 딱딱하지 않고 편안한 한국어 구어체(~해요, ~군요, ~네요 등)로 작성하세요.

[필수 작성 형식]
==================================================
✨ [오늘의 라이프스타일 분석 리포트] ✨

**1. ⏱️ 시간 및 활동 분석:**
- 데이터에 포함된 '앱별 최종 누적 시간(final_summary)'을 반드시 활용하여, 오늘 하루 어떤 앱에 얼마나 많은 시간을 쏟았는지 핵심 통계를 요약해 주세요.
- 몇 시경에 어떤 활동(어떤 웹사이트, 어떤 작업)을 주로 했는지 시간의 흐름에 따라 구체적으로 설명해 주세요.

**2. 🧍 자세와 디지털 습관:**
- SITTING, STANDING 등의 신체 자세 데이터가 특정 디지털 활동(예: 코딩, 영상 시청)과 어떻게 연결되는지 분석해 주세요.
- "SITTING 상태로 장시간 개발에 집중하셨네요"와 같이 신체 활동과 디지털 기록을 결합한 입체적인 분석을 제공해 주세요.

**3. 💌 오늘의 코멘트:**
- 사용자의 오늘 하루 노력과 패턴을 칭찬하고 격려하는 따뜻한 응원의 한마디를 남겨주세요.
==================================================

아래 데이터를 바탕으로 위의 형식에 맞춰 분석을 시작해 주세요:
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
    
    # print("\n" + "="*50)
    # print("✨ [로컬 AI 분석 코멘트] ✨")
    # print(ai_message.strip())
    # print("="*50 + "\n")
    print("\n" + ai_message.strip() + "\n")

except Exception as e:
    print(f"❌ 분석 중 오류가 발생했습니다: {e}")
    print("💡 팁: Ollama 프로그램이 실행 중인지, 'ollama run gemma2' 명령을 실행했는지 확인해주세요.")