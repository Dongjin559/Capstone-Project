import json
from openai import OpenAI
import re # 코드 맨 위쪽에 추가

# 1. Ollama 연결 설정 (API 키는 로컬이므로 아무 값이나 넣어도 무관함)
client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

# 2. 데이터 불러오기
try:
    with open('data/final_log.json', 'r', encoding='utf-8') as f:
        log_data = json.load(f)
except FileNotFoundError:
    print("❌ final_log.json 파일이 없습니다. 병합 스크립트를 먼저 실행하세요.")
    exit()

# 2.5 모바일 패키지명 변환 (Mapping)
app_mapping = {
    "com.android.vending": "Google Play 스토어",
    "com.android.chrome": "크롬 브라우저",
    "com.google.android.youtube": "유튜브",
    "com.kakao.talk": "카카오톡",
    "studio64": "안드로이드 스튜디오",
    "SITTING": "앉은 자세",
    "sitting": "앉은 자세",
    "STANDING": "서 있는 자세",
    "standing": "서 있는 자세",
    "LYING" : '누워 있는 자세'
}

# JSON 문자열로 바꾸기 전에 변환 (간단한 문자열 치환)
json_str = json.dumps(log_data, ensure_ascii=False)
for package, readable_name in app_mapping.items():
    json_str = json_str.replace(package, readable_name)
    
# 프롬프트에 넣을 때는 변환된 json_str을 사용
json_str = re.sub(r'C:\\[^\s\)]+', '', json_str)
# 3. 프롬프트 세팅
prompt = f"""
당신은 사용자의 일상 로그(자세 비전 데이터 + PC 앱 사용 기록 + 모바일 앱 사용 기록)를 분석하여 라이프스타일 인사이트를 제공하는 전문적이고 팩트 폭격을 서슴지 않는 엄격한 AI 코치입니다.
아래 [데이터]를 보고, 분석 규칙에 따라 사용자의 하루를 분석해 주세요.

[데이터 분석 규칙]
1. 용어 유지: 프로그램/앱 이름(예: VS Code, Chrome, MainActivity, YouTube)은 영문 그대로 표기하세요.
2. 자세 데이터의 한국어화: 자세 상태값은 절대 영어 원문으로 노출하지 말고, 문맥에 맞게 '앉아서', '서서' 등 자연스러운 한국어로 변환하세요.
3. 어색한 시간 표현 금지: "오후 8시경", "늦은 밤"처럼 사람이 쓰는 자연스러운 시간대 명칭을 사용하세요.
4. 맥락 추론: 창 제목(Title) 및 패키지명 데이터를 적극 활용하여 상황을 똑똑하게 추론하세요.
5. 어조: 분석 내용은 전문적이되, 딱딱하지 않고 편안한 한국어 구어체(~해요, ~군요, ~네요 등)로 작성하세요.
6. 문장 길이: 절대 길고 복잡하게 쓰지 마세요. 핵심만 짚어서 짧고 간결한 문장으로 끊어 쓰세요. 비유적이거나 감성적인 표현은 절대 금지합니다.
7. 기기 구분 명확화 (매우 중요): '안드로이드 스튜디오', 'python', 'chrome', 'VS Code' 그리고 관련된 웹사이트 제목이나 유튜브 영상 제목은 무조건 [PC 활동]입니다. 이를 [모바일 활동] 쪽에 절대 섞어 쓰지 마세요.
8. 인사이트 도출: 단순히 "앉아서 개발했다"로 끝내지 말고, "장시간 앉아 계셨으니 가벼운 스트레칭을 추천합니다" 등 건강/생산성 관점의 조언(Insight)을 덧붙이세요.
9. 내용 중복 및 어색한 인사 금지: 코멘트 마지막 문장은 반드시 토씨 하나 틀리지 말고 "오늘 하루도 수고 많으셨습니다. 푹 쉬세요." 라고만 출력하세요. 다른 인사말이나 외국어는 절대 금지합니다.


[필수 작성 형식]
==================================================
✨ [오늘의 라이프스타일 분석 리포트] ✨

**1. ⏱️ 시간 및 활동 분석:**
- 데이터에 포함된 '앱별 최종 누적 시간(final_summary)'을 활용하여 핵심 통계를 요약해 주세요.
- 💻 **PC 활동:** 몇 시경에 어떤 PC 프로그램(웹사이트, 작업 등)을 주로 했는지 설명해 주세요.
- 📱 **모바일 활동:** 몇 시경에 스마트폰에서 어떤 모바일 앱을 주로 사용했는지 별도로 구분하여 설명해 주세요.

**2. 🧍 자세와 디지털 습관:**
- 신체 자세 데이터가 PC 및 모바일 활동과 어떻게 연결되는지 분석해 주세요.
- (예시) "앉은 상태로 장시간 PC에서 개발에 집중하시고, 이후 모바일을 확인하셨네요"와 같이 신체 활동과 디지털 기록을 결합해 주세요.

**3. 💌 오늘의 코멘트:**
- 데이터를 기반으로 잘한 점은 가볍게 인정하되, 아쉬운 점(예: 과도하게 긴 착석 시간, 업무 중 잦은 모바일 딴짓 등)을 객관적이고 따끔하게 지적(팩트 폭격)하세요.
- 무조건적인 칭찬과 격려로만 채우는 것을 절대 금지하며, 사용자가 내일 더 나은 생산성과 건강을 유지할 수 있도록 실질적이고 단호한 개선 방향을 제시해 주세요.
- 마지막 마무리는 '오늘 하루도 수고 많으셨습니다.', '푹 쉬세요.' 등으로 자연스럽게 끝맺으세요.
==================================================

아래 데이터를 바탕으로 위의 형식에 맞춰 분석을 시작해 주세요:
[데이터]
{json_str}
⚠️ 최우선 규칙(CRITICAL): 데이터가 길거나 영어로 되어 있더라도, 최종 분석 리포트는 **무조건 100% 자연스러운 한국어(Korean)**로만 작성해야 합니다! 영어로 답하지 마세요.
"""
ai_model = "qwen2.5:3b"
print(f">> 🤖 로컬 AI({ai_model})가 데이터를 분석 중입니다. 잠시만 기다려주세요...")

# 4. 분석 실행 (스트리밍 방식 적용)
try:
    response = client.chat.completions.create(
        model="qwen2.5:3b",   # gemma2 or gemma2:2b(경량화 버전), qwen2.5:3b
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        stream=True  # 🔥 핵심: 한 글자씩 실시간으로 받아오기
    )
    
    print("\n" + "="*50)
    #print("✨ [오늘의 라이프스타일 분석 리포트] ✨")
    
    # AI가 주는 답변 조각(chunk)을 실시간으로 화면에 출력
    for chunk in response:
        if chunk.choices[0].delta.content is not None:
            print(chunk.choices[0].delta.content, end="", flush=True)
            
    print("\n" + "="*50 + "\n")

except Exception as e:
    print(f"\n❌ 분석 중 오류가 발생했습니다: {e}")
    print("💡 팁: Ollama 프로그램이 실행 중인지 확인해주세요.")