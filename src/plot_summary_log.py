import json
import matplotlib.pyplot as plt

# 🔥 수정됨: 기본 파일 읽기 경로를 'data/state_log.json'으로 변경
def plot_bar_chart(file_path='data/state_log.json'):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            state_logs = json.load(f)
    except FileNotFoundError:
        # 🔥 수정됨: 에러 메시지에 변경된 경로 안내 추가
        print(f"❌ 파일을 찾을 수 없습니다. ({file_path} 경로를 확인하세요.)")
        return

    # 1. 활동별 총 시간 계산
    summary = {'SITTING': 0, 'STANDING': 0, 'LYING': 0, 'UNKNOWN': 0}
    for item in state_logs:
        act = item['activity']
        if act in summary:
            summary[act] += item['stay_time']

    # 2. 그래프 데이터 준비
    activities = list(summary.keys())
    durations = list(summary.values())
    colors = ['#4CAF50', '#FFC107', '#2196F3', '#9E9E9E']

    # 3. 막대 그래프 그리기
    fig, ax = plt.subplots(figsize=(8, 6))
    bars = ax.bar(activities, durations, color=colors)

    ax.set_ylabel("Total Time (Seconds)")
    ax.set_title("Total Duration by Activity")

    # 막대 위에 시간 표시
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height, f'{height:.1f}s', ha='center', va='bottom')

    plt.tight_layout()
    
    # 🔥 보너스 추가: 화면에 보여주기 직전에 'data' 폴더에 고화질 이미지(dashboard.png)로 자동 저장!
    plt.savefig('data/dashboard.png', dpi=300)
    print(">> 📊 그래프 이미지가 'data/dashboard.png'로 성공적으로 저장되었습니다.")
    
    plt.show()

if __name__ == "__main__":
    plot_bar_chart()