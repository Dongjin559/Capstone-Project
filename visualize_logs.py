import json
import matplotlib.pyplot as plt
import platform
from matplotlib import rc

# 💡 마법의 코드: 충돌을 막기 위해 외부 라이브러리 없이 운영체제 폰트를 직접 끌어옵니다.
system_os = platform.system()
if system_os == 'Windows':
    rc('font', family='Malgun Gothic')
elif system_os == 'Darwin':
    rc('font', family='AppleGothic')
else:
    rc('font', family='NanumGothic')

# 마이너스(-) 기호 깨짐 방지
plt.rcParams['axes.unicode_minus'] = False

def draw_dashboard():
    print(">>  통합 라이프스타일 대시보드를 생성합니다...")
    
    try:
        with open('final_log.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print("❌ final_log.json 파일이 없습니다.")
        return

    # 1. 데이터 파싱
    timeline = data.get("timeline_data", [])
    posture_counts = {}
    for item in timeline:
        posture = item.get("physical_posture", "Unknown")
        time_sec = item.get("stay_time_sec", 0)
        posture_counts[posture] = posture_counts.get(posture, 0) + time_sec

    laptop_summary = data.get("laptop_final_summary") or {}
    laptop_apps = laptop_summary.get("final_accumulated_durations_sec", {})

    mobile_summary = data.get("mobile_final_summary") or {}
    mobile_apps = mobile_summary.get("final_accumulated_durations_sec", {})

    # 2. 1행 3열의 멋진 통합 그래프(Figure) 생성
    fig, axes = plt.subplots(1, 3, figsize=(15, 6))
    fig.suptitle(' 통합 라이프스타일 분석 대시보드 ', fontsize=18, fontweight='bold')

    # [그래프 1] 신체 자세 비율 (파이 차트)
    if posture_counts:
        axes[0].pie(posture_counts.values(), labels=posture_counts.keys(), autopct='%1.1f%%', startangle=90, colors=['#ff9999','#66b3ff','#99ff99','#ffcc99'])
        axes[0].set_title(' 신체 자세 비율')
    else:
        axes[0].text(0.5, 0.5, '자세 데이터 없음', ha='center', va='center')

    # [그래프 2] PC 앱 사용량 (바 차트)
    if laptop_apps:
        axes[1].bar(laptop_apps.keys(), laptop_apps.values(), color='#66b3ff')
        axes[1].set_title(' PC 앱 누적 사용 (초)')
        axes[1].tick_params(axis='x', rotation=45)
    else:
        axes[1].text(0.5, 0.5, 'PC 데이터 없음', ha='center', va='center')

    # [그래프 3] 모바일 앱 사용량 (바 차트)
    if mobile_apps:
        axes[2].bar(mobile_apps.keys(), mobile_apps.values(), color='#99ff99')
        axes[2].set_title(' 모바일 앱 누적 사용 (초)')
        axes[2].tick_params(axis='x', rotation=45)
    else:
        axes[2].text(0.5, 0.5, '모바일 데이터 없음', ha='center', va='center')

    # 레이아웃 예쁘게 다듬고 파일로도 자동 저장!
    plt.tight_layout()
    plt.savefig('dashboard.png', dpi=300)
    plt.show() # 화면에 그래프 띄우기

if __name__ == "__main__":
    draw_dashboard()