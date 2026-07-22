from flask import Flask, request, jsonify
import json
import os
from datetime import datetime

app = Flask(__name__)

DATA_DIR = os.path.join('data', 'mobile_log')
LATEST_FILE = os.path.join(DATA_DIR, 'mobile_log.json')


@app.route('/upload_mobile_log', methods=['POST'])
def upload_log():
    # Content-Type이 이상하거나 JSON 파싱이 안 돼도 예외 대신 None을 반환
    data = request.get_json(silent=True)

    if not data:
        return jsonify({"status": "error", "message": "No data"}), 400

    try:
        # data/mobile_log 폴더가 없으면 자동 생성
        os.makedirs(DATA_DIR, exist_ok=True)

        # 1) 최신 로그는 항상 같은 파일에 덮어써서 "최신 상태"를 바로 확인 가능하게 유지
        with open(LATEST_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        # 2) 세션별 기록도 타임스탬프 파일명으로 남겨서 이전 기록이 사라지지 않게 보존
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        session_file = os.path.join(DATA_DIR, f'mobile_log_{timestamp}.json')
        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        print(f">> 📱 [수신 완료] 모바일 로그 저장됨: {session_file}")
        return jsonify({"status": "success"}), 200

    except OSError as e:
        print(f">> ❌ 파일 저장 중 에러: {e}")
        return jsonify({"status": "error", "message": "Failed to save log"}), 500


if __name__ == '__main__':
    print(">> 🚀 모바일 로그 수신 서버가 켜졌습니다. 대기 중...")
    # 0.0.0.0으로 열어야 같은 네트워크의 모바일 기기에서 PC로 접근 가능
    app.run(host='0.0.0.0', port=5000, debug=True)