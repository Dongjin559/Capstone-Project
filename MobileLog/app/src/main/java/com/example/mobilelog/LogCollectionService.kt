package com.example.mobilelog

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * 화면(Activity)이 꺼지거나 앱이 백그라운드로 가도 로그 수집이 끊기지 않도록
 * Foreground Service로 분리한 버전.
 *
 * 최종 리포트는 AI 분석/영상 데이터 결합을 염두에 두고 다음 구조로 만든다:
 * - apps: 앱마다 하나의 레코드를 갖는 배열 (dict-of-dict 대신 배열 → 스키마 고정, DataFrame 변환 용이)
 * - timeline: 앱 전환 구간을 순서대로 담은 배열, epoch_ms 포함 (영상 프레임과 정확히 매칭 가능)
 */
class LogCollectionService : Service() {

    companion object {
        const val ACTION_START = "com.example.mobilelog.action.START"
        const val ACTION_STOP = "com.example.mobilelog.action.STOP"

        private const val CHANNEL_ID = "mobile_log_channel"
        private const val NOTIFICATION_ID = 1001
        private const val UPLOAD_INTERVAL_MS = 30_000L
        private const val POLL_INTERVAL_MS = 3000L // 0.5초 폴링 → 3초로 완화 (배터리 절약)
    }

    private val serviceJob = SupervisorJob()
    private val serviceScope = CoroutineScope(Dispatchers.Default + serviceJob)
    private var monitoringJob: Job? = null

    private lateinit var eventProcessor: UsageEventProcessor
    private lateinit var appNameResolver: AppNameResolver
    private var accumulator = SessionAccumulator()

    private var sessionStartTime: Long = 0L
    private var lastPollTime: Long = 0L

    override fun onCreate() {
        super.onCreate()
        eventProcessor = UsageEventProcessor(this)
        appNameResolver = AppNameResolver(this)
        createNotificationChannelIfNeeded()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> startMonitoring()
            ACTION_STOP -> stopMonitoringAndReport()
        }
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun startMonitoring() {
        if (monitoringJob?.isActive == true) return // 중복 시작 방지

        startForeground(NOTIFICATION_ID, buildNotification("모니터링 중..."))

        // 지난 세션에서 전송 실패해 큐에 쌓여있던 로그가 있으면 우선 재전송 시도
        serviceScope.launch { LogUploader.flushQueue(this@LogCollectionService) }

        sessionStartTime = System.currentTimeMillis()
        lastPollTime = sessionStartTime
        accumulator = SessionAccumulator()
        serviceScope.launch { LogUploader.notifyServerConnected(this@LogCollectionService) }

        monitoringJob = serviceScope.launch {
            var lastUploadTime = sessionStartTime
            while (isActive) {
                delay(POLL_INTERVAL_MS)
                val now = System.currentTimeMillis()
                // 이벤트 기반 정확 계산: 직전 폴링 이후 ~ 지금까지 구간만 조회
                eventProcessor.processEvents(lastPollTime, now, accumulator)
                lastPollTime = now
                if (now - lastUploadTime >= UPLOAD_INTERVAL_MS) {
                    val snapshot = eventProcessor.snapshot(now, accumulator)
                    LogUploader.uploadWithRetry(
                        this@LogCollectionService,
                        buildLogPayload(now, snapshot, inProgress = true),
                    )
                    lastUploadTime = now
                }
            }
        }
    }

    private fun buildLogPayload(now: Long, source: SessionAccumulator, inProgress: Boolean): String {
        val isoFormat = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.getDefault())
        val sessionIdFormat = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.getDefault())
        val appsJsonArray = JSONArray()
        for ((packageName, durationMs) in source.durationsMs) {
            if (durationMs > 0) {
                appsJsonArray.put(JSONObject().apply {
                    put("package", packageName)
                    put("app_name", appNameResolver.resolve(packageName))
                    put("total_duration_sec", (durationMs / 1000).toInt())
                    put("launch_count", source.launchCounts[packageName] ?: 0)
                })
            }
        }

        val timelineJsonArray = JSONArray()
        for (entry in TimelineCleaner.clean(source.timeline)) {
            val startEpochMs = entry.getLong("start_epoch_ms")
            val endEpochMs = entry.getLong("end_epoch_ms")
            entry.put("start_iso", isoFormat.format(Date(startEpochMs)))
            entry.put("end_iso", isoFormat.format(Date(endEpochMs)))
            timelineJsonArray.put(entry)
        }

        val mobileLogEntry = JSONObject().apply {
            put("session_id", sessionIdFormat.format(Date(sessionStartTime)))
            put("source", "mobile")
            put("session_start_iso", isoFormat.format(Date(sessionStartTime)))
            put("session_start_epoch_ms", sessionStartTime)
            put("session_end_iso", isoFormat.format(Date(now)))
            put("session_end_epoch_ms", now)
            put("total_monitoring_seconds", ((now - sessionStartTime) / 1000).toInt())
            put("apps", appsJsonArray)
            put("timeline", timelineJsonArray)
            if (inProgress) put("in_progress", true)
        }
        return JSONArray().put(mobileLogEntry).toString()
    }

    private fun stopMonitoringAndReport() {
        monitoringJob?.cancel()

        val now = System.currentTimeMillis()
        // 마지막 구간 이벤트 반영 + 현재 열려있는 세션(아직 BACKGROUND 안 찍힌 앱) 마감
        eventProcessor.processEvents(lastPollTime, now, accumulator)
        eventProcessor.finalizeOpenSession(now, accumulator)
        val finalPayload = buildLogPayload(now, accumulator, inProgress = false)

        val totalSessionSeconds = ((now - sessionStartTime) / 1000).toInt()

        val isoFormat = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.getDefault())
        val sessionIdFormat = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.getDefault())

        // apps: 앱마다 하나의 레코드를 갖는 배열 (package / app_name / total_duration_sec / launch_count)
        val appsJsonArray = JSONArray()
        for ((packageName, durationMs) in accumulator.durationsMs) {
            // 초 단위로 반올림하기 전, 실제 사용 여부(ms > 0)로 먼저 필터링
            // (초 단위로만 거르면 500ms처럼 1초 미만 사용이 apps에서만 통째로 빠지는
            //  불일치가 생김 - timeline엔 남는데 apps엔 없는 문제)
            if (durationMs > 0) {
                val totalSec = (durationMs / 1000).toInt()
                appsJsonArray.put(
                    JSONObject().apply {
                        put("package", packageName)
                        put("app_name", appNameResolver.resolve(packageName))
                        put("total_duration_sec", totalSec)
                        put("launch_count", accumulator.launchCounts[packageName] ?: 0)
                    }
                )
            }
        }

        // timeline: 짧게 깜빡이는 노이즈(같은 앱 반복 전환 등)를 병합/필터링한 뒤 배열로 구성
        val cleanedTimeline = TimelineCleaner.clean(accumulator.timeline)
        val timelineJsonArray = JSONArray()
        for (entry in cleanedTimeline) {
            val startEpochMs = entry.getLong("start_epoch_ms")
            val endEpochMs = entry.getLong("end_epoch_ms")
            entry.put("start_iso", isoFormat.format(Date(startEpochMs)))
            entry.put("end_iso", isoFormat.format(Date(endEpochMs)))
            timelineJsonArray.put(entry)
        }

        val mobileLogEntry = JSONObject().apply {
            put("session_id", sessionIdFormat.format(Date(sessionStartTime)))
            put("source", "mobile")
            put("session_start_iso", isoFormat.format(Date(sessionStartTime)))
            put("session_start_epoch_ms", sessionStartTime)
            put("session_end_iso", isoFormat.format(Date(now)))
            put("session_end_epoch_ms", now)
            put("total_monitoring_seconds", totalSessionSeconds)
            put("apps", appsJsonArray)
            put("timeline", timelineJsonArray)
        }

        val finalJsonArray = JSONArray().put(mobileLogEntry)

        serviceScope.launch {
            val uploaded = LogUploader.uploadWithRetry(this@LogCollectionService, finalPayload)
            if (uploaded) {
                LogUploader.requestServerShutdown(this@LogCollectionService)
            }
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
        }
    }

    override fun onDestroy() {
        serviceJob.cancel()
        super.onDestroy()
    }

    private fun createNotificationChannelIfNeeded() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "모바일 로그 수집",
                NotificationManager.IMPORTANCE_LOW
            )
            val manager = getSystemService(NotificationManager::class.java)
            manager?.createNotificationChannel(channel)
        }
    }

    private fun buildNotification(content: String): Notification {
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("📱 모바일 로그 수집기")
            .setContentText(content)
            .setSmallIcon(android.R.drawable.ic_menu_recent_history)
            .setOngoing(true)
            .build()
    }
}
