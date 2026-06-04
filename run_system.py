import subprocess
import time
import sys
import os
import glob

def main():
    print("==================================================")
    print("🚀 라이프스타일 통합 분석 시스템 가동 🚀")
    print("==================================================")
    
    print(">> 🧹 이전 테스트 로그와 시스템 찌꺼기를 초기화합니다...")
    # 1. 이전 JSON 로그들 삭제
    for f_path in glob.glob("data/*_log.json"):
        try:
            os.remove(f_path)
        except Exception:
            pass
            
    # 2. 좀비 멈춤 신호(플래그) 파일 삭제
    if os.path.exists("data/stop_flag.txt"):
        try:
            os.remove("data/stop_flag.txt")
        except Exception:
            pass
    
    print(">> 💡 [안내] 안드로이드 에뮬레이터에서 '모니터링 시작'을 미리 눌러두세요!")
    
    recording_processes = []
    server_proc = None
    
    try:
        print("\n[0/3] 📡 모바일 로그 수신용 PC 서버를 백그라운드에서 기동합니다...")
        server_proc = subprocess.Popen([sys.executable, "src/mobile_server.py"])
        time.sleep(1)

        print("[1/3] 💻 랩탑 로거를 백그라운드에서 기동합니다...")
        laptop_proc = subprocess.Popen([sys.executable, "src/laptop_logger.py"])
        recording_processes.append(laptop_proc)
        
        print("[2/3] 🎥 카메라 영상 분석을 백그라운드에서 기동합니다...")
        camera_proc = subprocess.Popen([sys.executable, "src/homecam_live.py"])
        recording_processes.append(camera_proc)
        
        print("\n==================================================")
        print("🟢 시스템이 실시간으로 신체 자세와 PC 활동을 기록 중입니다.")
        print("📱 스마트폰(에뮬레이터)으로도 자유롭게 활동해 주세요.")
        print("==================================================")
        
        input("\n⏹️ 기록을 종료하려면 터미널을 클릭하고 [Enter] 키를 누르세요...")

    except KeyboardInterrupt:
        print("\n>> 사용자에 의해 중단 요청됨.")
    
    finally:
        print("\n[3/3] 💻 실시간 데이터 저장을 위해 안전 종료를 시도합니다. (약 3초 대기)...")
        
        # 로거들에게 하던 일을 멈추고 로그를 저장하라고 신호(flag)를 보냅니다.
        with open("data/stop_flag.txt", "w") as f:
            f.write("stop")
            
        time.sleep(3)

        # 혹시라도 안 꺼진 프로세스들만 종료
        for proc in recording_processes:
            if proc.poll() is None:
                proc.terminate()
                proc.wait()
                
        # 깃발 수거
        if os.path.exists("data/stop_flag.txt"):
            os.remove("data/stop_flag.txt")
        
        print("\n>> 💡 [안내] 이제 안드로이드 앱에서 '모니터링 종료' 버튼을 눌러주세요!")
        input(">> 📱 [수신 완료] 메시지가 떴다면 [Enter] 키를 눌러 다음으로 넘어가세요...")
        
        if server_proc and server_proc.poll() is None:
            print(">> 📡 통신 완료! PC 서버를 안전하게 종료합니다.")
            server_proc.terminate()
            server_proc.wait()

        time.sleep(1)

        try:
            print("\n--------------------------------------------------")
            print("🔗 [단계 1] 3종 데이터(자세/PC/모바일) 병합 중...")
            subprocess.run([sys.executable, "src/merge_logs.py"], check=True)
            
            # 🔥 핵심 변경 부분: 대시보드를 비동기(Popen)로 실행합니다!
            print("\n📊 [단계 2] 통합 라이프스타일 대시보드 그래프를 화면에 띄웁니다...")
            dash_proc = subprocess.Popen([sys.executable, "src/visualize_logs.py"])
            
            # 그래프 창이 화면에 뜰 시간을 1~2초 정도 살짝 벌어줍니다.
            time.sleep(2)
            
            # 그래프가 떠 있는 상태에서 즉시 AI 분석을 시작합니다.
            print("\n🤖 [단계 3] 대시보드를 띄워둔 채로 로컬 AI 종합 분석 리포트를 생성합니다...")
            subprocess.run([sys.executable, "src/analyze_log_ollama.py"], check=True)
            
            print("\n🎉 모든 분석이 성공적으로 마무리되었습니다! 🎉")
            print(">> 💡 [안내] 띄워져 있는 대시보드 그래프 창을 닫으면 시스템이 완전히 종료됩니다.")
            print("==================================================")
            
            # 🔥 사용자가 그래프를 충분히 감상하고 창을 'X' 버튼으로 닫을 때까지 
            # 프로그램이 종료되지 않고 얌전히 대기하게 만듭니다.
            dash_proc.wait()

        except subprocess.CalledProcessError as e:
            print(f"\n❌ 분석 도중 오류가 발생했습니다: {e}")

if __name__ == "__main__":
    main()