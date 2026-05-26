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
├── homecam_live.py    # [핵심] 컴퓨터 비전 기반 실시간 활동 추적 코드(라이브)
├── analyze_log.py     # [핵심] 수집된 활동 로그 데이터 가공 및 분석 엔진
├── requirements.txt   # 의존성 라이브러리 목록
├── README.md          # 프로젝트 설명 문서
└── .gitignore         # 가상환경 및 불필요 파일 제외 설정