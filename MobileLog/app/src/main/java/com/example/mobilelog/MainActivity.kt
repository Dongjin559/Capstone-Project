package com.example.mobilelog

import android.app.AppOpsManager
import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.os.Process
import android.provider.Settings
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlinx.coroutines.Dispatchers
import java.net.HttpURLConnection
import java.net.URL

class MainActivity : ComponentActivity() {

    // 실시간 모니터링을 위한 상태 변수들
    private var monitoringJob: Job? = null
    private var isMonitoring by mutableStateOf(false)
    private var sessionStartTime: Long = 0

    // 노트북 로거처럼 실시간으로 앱별 사용 시간을 소수점(초) 단위로 누적할 맵
    private val mobileAppDurationTracker = mutableMapOf<String, Double>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    MainScreen(
                        isMonitoring = isMonitoring,
                        onStartClick = { startMonitoring() },
                        onStopClick = { stopMonitoring() }
                    )
                }
            }
        }
    }

    @Composable
    fun MainScreen(
        isMonitoring: Boolean,
        onStartClick: () -> Unit,
        onStopClick: () -> Unit
    ) {
        val context = LocalContext.current

        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(16.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(text = "📱 모바일 실시간 로그 수집기")

            Spacer(modifier = Modifier.height(30.dp))

            Button(onClick = {
                if (!hasUsageStatsPermission(context)) {
                    requestUsageStatsPermission(context)
                } else {
                    Log.d("MobileLog", "이미 권한이 허용되어 있습니다.")
                }
            }) {
                Text(text = "1. 사용 정보 접근 권한 설정하기")
            }

            Spacer(modifier = Modifier.height(30.dp))

            if (!isMonitoring) {
                Button(onClick = onStartClick) {
                    Text(text = "▶️ 모니터링 시작")
                }
            } else {
                Button(onClick = onStopClick) {
                    Text(text = "⏹️ 모니터링 종료 및 최종 리포트 출력")
                }
                Spacer(modifier = Modifier.height(16.dp))
                Text(text = "⏳ 실시간 감시 중... (Logcat 확인)", color = MaterialTheme.colorScheme.primary)
            }
        }
    }

    // [실시간 감시 시작] 노트북 로거의 log_laptop_usage()와 같은 역할
    private fun startMonitoring() {
        isMonitoring = true
        sessionStartTime = System.currentTimeMillis()
        mobileAppDurationTracker.clear() // 이전 세션 기록 초기화

        Log.d("MobileLog", "==================================================")
        Log.d("MobileLog", "🚀 모바일 실시간 모니터링 세션을 시작합니다.")
        Log.d("MobileLog", "==================================================")

        var lastCheckedTime = System.currentTimeMillis()

        // 0.5초마다 현재 화면에 켜진 최상단 앱을 감시하는 루프 기동
        monitoringJob = lifecycleScope.launch {
            while (isActive) {
                val now = System.currentTimeMillis()
                val currentForegroundApp = getForegroundPackageName(this@MainActivity)

                // 시간 경과 계산 (초 단위)
                val elapsedSec = (now - lastCheckedTime) / 1000.0

                if (currentForegroundApp != null && currentForegroundApp != "unknown" && currentForegroundApp != "idle") {
                    // 맵에 실시간으로 초 단위 누적량 저장
                    val currentDuration = mobileAppDurationTracker.getOrDefault(currentForegroundApp, 0.0)
                    mobileAppDurationTracker[currentForegroundApp] = currentDuration + elapsedSec
                }

                lastCheckedTime = now
                delay(500) // 0.5초 주기로 정밀하게 스캔
            }
        }
    }

    // [실시간 감시 종료] 노트북 로거의 record_final_summary()와 같은 역할
    private fun stopMonitoring() {
        monitoringJob?.cancel()
        isMonitoring = false

        val totalSessionSeconds = ((System.currentTimeMillis() - sessionStartTime) / 1000).toInt()
        val currentTime = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault()).format(Date())

        // JSON 데이터 구조 표준화 구조 생성
        val finalJsonArray = JSONArray()
        val appDurationsJson = JSONObject()
        val appDurationsReadableJson = JSONObject()

        // 소수점으로 기록된 초 단위를 정수형태 및 읽기 좋은 포맷으로 가공
        for ((packageName, durationInSec) in mobileAppDurationTracker) {
            val totalSec = durationInSec.toInt()
            if (totalSec > 0) {
                appDurationsJson.put(packageName, totalSec)
                appDurationsReadableJson.put(packageName, "${totalSec}초")
            }
        }

        // 최종 모바일 요약 리포트 오브젝트 조립
        val mobileLogEntry = JSONObject().apply {
            put("timestamp", currentTime)
            put("trigger", "mobile_final_summary")
            put("source", "mobile")
            put("total_monitoring_seconds", totalSessionSeconds)
            put("final_accumulated_durations_sec", appDurationsJson)
            put("final_accumulated_durations_readable", appDurationsReadableJson)
        }

        finalJsonArray.put(mobileLogEntry)

        // Logcat에 최종 출력! 이 값을 가져가시면 됩니다.
        Log.d("MobileLog_JSON", "==================================================")
        Log.d("MobileLog_JSON", "📋 [모바일 최종 분석 리포트 생성 완료]")
        Log.d("MobileLog_JSON", finalJsonArray.toString(4))
        Log.d("MobileLog_JSON", "==================================================")

        lifecycleScope.launch(Dispatchers.IO) {
            sendLogToServer(finalJsonArray.toString())
        }
    }

    // 현재 최상단(Foreground)에 켜져 있는 앱의 패키지명을 찾아내는 헬퍼 함수
    private fun getForegroundPackageName(context: Context): String? {
        val usageStatsManager = context.getSystemService(Context.USAGE_STATS_SERVICE) as UsageStatsManager
        val now = System.currentTimeMillis()

        // 최근 10초 이내의 통계 이벤트를 가져와서 분석
        val stats = usageStatsManager.queryEvents(now - 10000, now)
        val event = UsageEvents.Event()
        var lastForegroundApp: String? = null

        while (stats.hasNextEvent()) {
            stats.getNextEvent(event)
            // 앱이 화면에 나타난 이벤트(MOVE_TO_FOREGROUND)를 추적
            if (event.eventType == UsageEvents.Event.MOVE_TO_FOREGROUND) {
                lastForegroundApp = event.packageName
            }
        }

        // 런처(홈화면)나 자기 자신은 무의미하므로 필터링
        if (lastForegroundApp == context.packageName || lastForegroundApp?.contains("launcher") == true) {
            return "idle"
        }

        return lastForegroundApp ?: "idle"
    }

    private fun hasUsageStatsPermission(context: Context): Boolean {
        val appOps = context.getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
        val mode = appOps.checkOpNoThrow(
            AppOpsManager.OPSTR_GET_USAGE_STATS,
            Process.myUid(),
            context.packageName
        )
        return mode == AppOpsManager.MODE_ALLOWED
    }

    private fun requestUsageStatsPermission(context: Context) {
        val intent = Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS)
        context.startActivity(intent)
    }

    // [맨 아래에 추가할 기능 로직 4] 생성된 JSON을 PC 서버로 발사하는 함수
    private fun sendLogToServer(jsonString: String) {
        try {
            // 💡 중요: 10.0.2.2는 안드로이드 에뮬레이터가 '내 노트북'을 부르는 특수 IP 주소입니다!
            val url = URL("http://10.0.2.2:5000/upload_mobile_log")
            val conn = url.openConnection() as HttpURLConnection
            conn.requestMethod = "POST"
            conn.setRequestProperty("Content-Type", "application/json; charset=UTF-8")
            conn.doOutput = true

            val os = conn.outputStream
            os.write(jsonString.toByteArray(Charsets.UTF_8))
            os.close()

            if (conn.responseCode == HttpURLConnection.HTTP_OK) {
                Log.d("MobileLog", "✅ PC 서버로 전송 대성공!")
            } else {
                Log.d("MobileLog", "❌ 전송 실패: 에러 코드 ${conn.responseCode}")
            }
            conn.disconnect()
        } catch (e: Exception) {
            Log.e("MobileLog", "서버 전송 중 통신 에러: ${e.message}")
        }
    }
} // <-- MainActivity 닫히는 괄호