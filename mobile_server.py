from flask import Flask, request, jsonify
import json

app = Flask(__name__)

# 안드로이드에서 데이터를 쏘아 보낼 주소 (엔드포인트)
@app.route('/upload_mobile_log', methods=['POST'])
def upload_log():
    data = request.json
    if data:
        # 받은 데이터를 VS Code 폴더에 'mobile_log.json'으로 저장!
        with open('mobile_log.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(">> 📱 [수신 완료] 모바일 로그가 mobile_log.json으로 저장되었습니다!")
        return jsonify({"status": "success"}), 200

    return jsonify({"status": "error", "message": "No data"}), 400

if __name__ == '__main__':
    print(">> 🚀 모바일 로그 수신 서버가 켜졌습니다. 대기 중...")
    # 0.0.0.0으로 열어야 안드로이드 에뮬레이터에서 PC로 접근 가능
    app.run(host='0.0.0.0', port=5000, debug=True)