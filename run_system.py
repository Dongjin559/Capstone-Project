import subprocess
import time
import sys

def main():
    print("==================================================")
    print("🚀 LuvLog 라이프스타일 통합 분석 시스템 가동 🚀")
    print("==================================================")
    print(">> 💡 [안내] 안드로이드 에뮬레이터에서 '모니터링 시작'을 미리 눌러두세요!")
    
    recording_processes = []
    server_proc = None
    
    try:
        # 0. 📡 모바일 서버 기동 (모바일 데이터를 받기 위해 가장 먼저 켜져야 함)
        print("\n[0/3] 📡 모바일 로그 수신용 PC 서버를 백그라운드에서 기동합니다...")
        server_proc = subprocess.Popen([sys.executable, "mobile_server.py"])
        time.sleep(1) # 서버가 완전히 켜질 때까지 1초 대기

        # 1. 💻 랩탑 로거 실행
        print("[1/3] 💻 랩탑 로거를 백그라운드에서 기동합니다...")
        # ⚠️ 스크립트 파일명을 정확히 적어주세요
        laptop_proc = subprocess.Popen([sys.executable, "laptop_logger.py"])
        recording_processes.append(laptop_proc)
        
        # 2. 🎥 카메라 영상 분석 실행
        print("[2/3] 🎥 카메라 영상 분석을 백그라운드에서 기동합니다...")
        # ⚠️ 스크립트 파일명을 정확히 적어주세요
        camera_proc = subprocess.Popen([sys.executable, "homecam_live.py"])
        recording_processes.append(camera_proc)
        
        print("\n==================================================")
        print("🟢 시스템이 실시간으로 신체 자세와 PC 활동을 기록 중입니다.")
        print("📱 스마트폰(에뮬레이터)으로도 자유롭게 활동해 주세요.")
        print("==================================================")
        
        # 사용자가 수집을 마칠 때까지 대기
        input("\n⏹️ 기록을 종료하려면 터미널을 클릭하고 [Enter] 키를 누르세요...")

    except KeyboardInterrupt:
        print("\n>> 사용자에 의해 중단 요청됨.")
    
    finally:
        # 3. 🛑 로깅(기록) 프로그램들만 먼저 종료
        print("\n[3/3] 💻 실시간 PC/카메라 수집을 종료하고 데이터를 정제합니다...")
        for proc in recording_processes:
            if proc.poll() is None:
                proc.terminate()
                proc.wait()
        
        # 💡 핵심: 서버는 아직 살아있어야 모바일에서 보내는 데이터를 받을 수 있습니다!
        print("\n>> 💡 [안내] 이제 안드로이드 앱에서 '모니터링 종료' 버튼을 눌러주세요!")
        input(">> 📱 [수신 완료] 메시지가 떴다면 [Enter] 키를 눌러 다음으로 넘어가세요...")
        
        # 4. 🛑 모바일 데이터를 다 받았으니 이제 서버도 종료
        if server_proc and server_proc.poll() is None:
            print(">> 📡 통신 완료! PC 서버를 안전하게 종료합니다.")
            server_proc.terminate()
            server_proc.wait()

        time.sleep(1)

        # ==========================================
        # 5. 후처리 파이프라인 가동 (병합 -> 그래프 -> AI)
        # ==========================================
        try:
            print("\n--------------------------------------------------")
            print("🔗 [단계 1] 3종 데이터(자세/PC/모바일) 병합 중...")
            subprocess.run([sys.executable, "merge_logs.py"], check=True)
            
            print("\n📊 [단계 2] 통합 라이프스타일 대시보드 그래프 생성 중...")
            print(">> 💡 [안내] 그래프 창을 끄면 로컬 AI 분석 코멘트 단계로 넘어갑니다.")
            subprocess.run([sys.executable, "visualize_logs.py"], check=True)
            
            print("\n🤖 [단계 3] 로컬 AI(gemma2) 종합 분석 리포트 생성 중...")
            subprocess.run([sys.executable, "analyze_log_ollama.py"], check=True)
            
            
            print("\n🎉 모든 분석이 성공적으로 마무리되었습니다! 🎉")
            print("==================================================")

        except subprocess.CalledProcessError as e:
            print(f"\n❌ 분석 도중 오류가 발생했습니다: {e}")

if __name__ == "__main__":
    main()