import json
import matplotlib.pyplot as plt
import platform
import sys
import traceback
from matplotlib import rc

system_os = platform.system()
if system_os == 'Windows':
    rc('font', family='Malgun Gothic')
elif system_os == 'Darwin':
    rc('font', family='AppleGothic')
else:
    rc('font', family='NanumGothic')

plt.rcParams['axes.unicode_minus'] = False

def draw_dashboard():
    try:
        print(">> [대시보드] 그래프 생성을 시작합니다...")
        
        try:
            with open('data/final_log.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            print("❌ data/final_log.json 파일이 없습니다.")
            return

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

        fig, axes = plt.subplots(1, 3, figsize=(15, 6))
        fig.suptitle('통합 라이프스타일 분석 대시보드', fontsize=18, fontweight='bold')

        # [그래프 1]
        if posture_counts:
            # 🔥 색상 갯수 오버플로우 방지를 위해 colors 속성 제거 (Matplotlib 기본 색상 자동 할당)
            axes[0].pie(posture_counts.values(), labels=posture_counts.keys(), autopct='%1.1f%%', startangle=90)
            axes[0].set_title('신체 자세 비율')
        else:
            axes[0].text(0.5, 0.5, '자세 데이터 없음', ha='center', va='center')

        # [그래프 2]
        if laptop_apps:
            axes[1].bar(list(laptop_apps.keys()), list(laptop_apps.values()), color='#66b3ff')
            axes[1].set_title('PC 앱 누적 사용 (초)')
            axes[1].tick_params(axis='x', rotation=45)
        else:
            axes[1].text(0.5, 0.5, 'PC 데이터 없음', ha='center', va='center')

        # [그래프 3]
        if mobile_apps:
            axes[2].bar(list(mobile_apps.keys()), list(mobile_apps.values()), color='#99ff99')
            axes[2].set_title('모바일 앱 누적 사용 (초)')
            axes[2].tick_params(axis='x', rotation=45)
        else:
            axes[2].text(0.5, 0.5, '모바일 데이터 없음', ha='center', va='center')

        plt.tight_layout()
        plt.savefig('data/dashboard.png', dpi=300)
        print(">> 📸 대시보드 이미지가 'data/dashboard.png'로 저장되었습니다.")
        plt.show()

    # 🔥 에러가 나면 이유 없이 죽지 말고, 무슨 에러인지 명확히 출력하도록 설정!
    except Exception as e:
        print(f"\n❌ [대시보드 크래시] 원인: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    draw_dashboard()