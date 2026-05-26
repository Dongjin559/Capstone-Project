import subprocess
import time
import sys

print("🚀 통합 시스템 작동을 시작합니다...\n")

try:
    # 1. 랩탑 로거 실행
    print(">> [1/5] 노트북 사용 기록 추적기(laptop_logger.py) 실행 중...")
    logger_process = subprocess.Popen([sys.executable, "-u", "laptop_logger.py"])
    time.sleep(1)

    # 2. 홈캠 라이브 실행
    print(">> [2/5] 카메라 분석(homecam_live.py)을 시작합니다.")
    print("   (종료하시려면 팝업된 카메라 영상 창을 클릭하고 'q'를 누르세요.)")
    print("-" * 50)
    subprocess.run([sys.executable, "homecam_live.py"])
    
    print("-" * 50)
    print(">> [3/5] 카메라 분석이 종료되었습니다. 노트북 로거를 중지합니다.")
    logger_process.terminate()
    logger_process.wait()

    # 3. 데이터 병합
    print(">> [4/5] 데이터 병합(merge_logs.py)을 시작합니다...")
    subprocess.run([sys.executable, "merge_logs.py"])
    
    # 4. AI 분석 실행
    print("\n>> [5/5] AI 종합 분석(analyze_log_ollama.py)을 시작합니다...")
    subprocess.run([sys.executable, "analyze_log_ollama.py"])

    # 5. 그래프 시각화 (새로 추가!)
    print("\n>> [추가] 분석 그래프(plot_activity.py)를 출력합니다...")
    subprocess.run([sys.executable, "plot_summary_log.py"])

    print("\n🎉 모든 작업이 완료되었습니다!")

except Exception as e:
    print(f"\n❌ 실행 중 오류 발생: {e}")
    if 'logger_process' in locals():
        logger_process.terminate()