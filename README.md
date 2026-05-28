# 거주 공간 내 활동 패턴 분석 시스템

본 프로젝트는 컴퓨터 비전 기술을 활용하여 사용자의 일상 활동을 실시간으로 추적하고, 이를 디지털 로그와 통합하여 종합적인 라이프스타일 분석을 제공하는 시스템입니다.

## 🚀 주요 기능
- **실시간 활동 추적:** MediaPipe와 YOLOv8을 활용하여 사용자의 물리적 자세 및 동작(앉음, 서있음, 보행 등)을 실시간으로 인식합니다.
- **라이프스타일 로그 통합:** 비전 데이터와 디지털 사용 로그를 매칭하여 사용자의 일일 활동 패턴을 데이터화합니다.
- **데이터 시각화 및 분석:** 수집된 데이터를 바탕으로 활동성 분석 및 개선 방향을 제시하는 요약 보고서를 제공합니다.

## 🛠 기술 스택
- **언어:** Python, Java, Kotlin
- **AI/ML:** YOLOv8, MediaPipe (Human Pose Estimation)
- **Mobile:** Android (Jetpack Compose)
- **개발 환경:** Git, GitHub, VS Code

## 📂 프로젝트 구조
```text
Capstone-Project/
├── aa/                           # (추가적인 데이터 또는 설정 폴더)
├── .gitignore                    # Git 버전 관리 제외 파일 설정
├── README.md                     # 프로젝트 설명서
├── analyze_log_gemini.py         # Gemini API를 활용한 라이프스타일 로그 분석
├── analyze_log_gpt.py            # GPT API를 활용한 라이프스타일 로그 분석
├── analyze_log_ollama.py         # Ollama(로컬 LLM)를 활용한 라이프스타일 로그 분석
├── dashboard.png                 # 시스템 분석 결과 대시보드 스크린샷
├── homecam.py                    # 홈캠 기반 신체 활동 추적 비전 시스템
├── homecam_live.py               # 홈캠 실시간 영상 처리 및 활동 로깅
├── laptop_logger.py              # PC(노트북) 기기 사용 시간 및 활동 기록 수집기
├── merge_logs.py                 # 다중 소스(모바일, PC, 홈캠) 로그 데이터 병합 처리
├── mobile_server.py              # 안드로이드 앱과 통신하여 모바일 로그를 수신하는 서버
├── plot_summary_log.py           # 분석된 라이프스타일 요약 데이터 그래프 생성
├── requirements.txt              # 파이썬 실행을 위한 필수 라이브러리 목록
├── run_system.py                 # 통합 시스템 전체 실행 진입점 (Main)
└── visualize_logs.py             # 수집/병합된 로그 데이터 시각화 도구
