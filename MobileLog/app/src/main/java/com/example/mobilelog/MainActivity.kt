package com.example.mobilelog

import android.app.AppOpsManager
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.os.Process
import android.provider.Settings
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp

/**
 * 변경 요약
 * 1) 실제 수집 로직은 LogCollectionService(Foreground Service)로 이동 → 화면이 꺼져도 계속 수집
 * 2) MainActivity는 서비스 시작/종료 트리거 + 서버 주소 설정 UI 역할만 담당
 */
class MainActivity : ComponentActivity() {

    private var isMonitoring by mutableStateOf(false)

    private val notificationPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Android 13+ 는 알림 권한이 없으면 Foreground Service 알림이 보이지 않는다
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            notificationPermissionLauncher.launch(android.Manifest.permission.POST_NOTIFICATIONS)
        }

        setContent {
            MaterialTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    MainScreen(
                        isMonitoring = isMonitoring,
                        onStartClick = { startService() },
                        onStopClick = { stopService() }
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
        var serverUrl by remember { mutableStateOf(AppConfig.getServerBaseUrl(context)) }

        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(16.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(text = "📱 모바일 실시간 로그 수집기")

            Spacer(modifier = Modifier.height(20.dp))

            // 서버 주소 외부화: 하드코딩 대신 여기서 바로 수정 가능
            OutlinedTextField(
                value = serverUrl,
                onValueChange = {
                    serverUrl = it
                    AppConfig.setServerBaseUrl(context, it)
                },
                label = { Text("서버 주소 (예: http://192.168.0.229:5000)") },
                modifier = Modifier.fillMaxWidth()
            )

            Spacer(modifier = Modifier.height(20.dp))

            Button(onClick = {
                if (!hasUsageStatsPermission(context)) {
                    requestUsageStatsPermission(context)
                } else {
                    Log.d("MobileLog", "이미 권한이 허용되어 있습니다.")
                }
            }) {
                Text(text = "1. 사용 정보 접근 권한 설정하기")
            }

            Spacer(modifier = Modifier.height(20.dp))

            if (!isMonitoring) {
                Button(onClick = onStartClick) {
                    Text(text = "▶️ 모니터링 시작")
                }
            } else {
                Button(onClick = onStopClick) {
                    Text(text = "분석 종료")
                }
                Spacer(modifier = Modifier.height(16.dp))
                Text(text = "⏳ 백그라운드에서도 계속 수집 중 (알림 확인)", color = MaterialTheme.colorScheme.primary)
            }
        }
    }

    private fun startService() {
        isMonitoring = true
        val intent = Intent(this, LogCollectionService::class.java).apply {
            action = LogCollectionService.ACTION_START
        }
        startForegroundService(intent)
    }

    private fun stopService() {
        isMonitoring = false
        val intent = Intent(this, LogCollectionService::class.java).apply {
            action = LogCollectionService.ACTION_STOP
        }
        startService(intent)
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
}
