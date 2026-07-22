package com.example.mobilelog

import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.Context
import org.json.JSONObject

/**
 * 여러 종류의 로그 데이터를 한 번에 모아서 들고 다니기 위한 누적 컨테이너.
 * - durationsMs: 앱별 총 사용시간(ms)
 * - launchCounts: 앱별 포그라운드 전환(실행) 횟수
 * - timeline: 앱을 켜서 언제까지 썼는지, epoch(ms) 기준으로 순서대로 기록한 타임라인
 *   (epoch를 쓰면 영상 프레임 타임스탬프와 문자열 파싱 없이 바로 매칭 가능)
 */
class SessionAccumulator {
    val durationsMs: MutableMap<String, Long> = mutableMapOf()
    val launchCounts: MutableMap<String, Int> = mutableMapOf()
    val timeline: MutableList<JSONObject> = mutableListOf()
}

/**
 * UsageEvents의 MOVE_TO_FOREGROUND / MOVE_TO_BACKGROUND 이벤트 쌍을 기반으로
 * 앱별 정확한 사용 시간(ms) + 실행 횟수 + 전환 타임라인을 계산하는 클래스.
 */
class UsageEventProcessor(private val context: Context) {

    // 현재 포그라운드로 파악된 앱과, 그 앱이 포그라운드로 전환된 시각(다음 폴링에도 이어서 사용)
    private var currentForegroundApp: String? = null
    private var foregroundStartTimestamp: Long = 0L

    private val myPackageName = context.packageName
    private val appNameResolver = AppNameResolver(context)

    /**
     * [sinceTime, untilTime) 구간의 이벤트를 조회해 acc(누적 컨테이너)에 반영한다.
     * 호출자는 매 폴링마다 sinceTime = 직전 폴링의 untilTime 을 넘겨서
     * 이벤트가 유실되거나 중복 계산되지 않도록 한다.
     */
    fun processEvents(sinceTime: Long, untilTime: Long, acc: SessionAccumulator) {
        if (sinceTime >= untilTime) return

        val usageStatsManager =
            context.getSystemService(Context.USAGE_STATS_SERVICE) as UsageStatsManager
        val events = usageStatsManager.queryEvents(sinceTime, untilTime)
        val event = UsageEvents.Event()

        while (events.hasNextEvent()) {
            events.getNextEvent(event)

            // 런처(홈 화면)나 자기 자신은 실질적인 "앱 사용"이 아니므로 무시
            if (event.packageName == myPackageName || event.packageName?.contains("launcher") == true) {
                continue
            }

            when (event.eventType) {
                UsageEvents.Event.MOVE_TO_FOREGROUND -> {
                    // 이전 앱이 BACKGROUND 이벤트 없이 새 앱에 자리를 내준 경우를 대비해
                    // 새 앱이 뜨는 시점 기준으로 이전 앱 시간을 우선 정산
                    closeCurrentSession(event.timeStamp, acc)

                    currentForegroundApp = event.packageName
                    foregroundStartTimestamp = event.timeStamp

                    // 실행 횟수: 포그라운드로 새로 전환될 때마다 +1
                    val app = event.packageName
                    acc.launchCounts[app] = (acc.launchCounts[app] ?: 0) + 1
                }

                UsageEvents.Event.MOVE_TO_BACKGROUND -> {
                    if (event.packageName == currentForegroundApp) {
                        closeCurrentSession(event.timeStamp, acc)
                    }
                }
            }
        }
    }

    /**
     * 모니터링 종료 시점 등, "지금 이 순간까지"의 사용 시간을 마감 처리할 때 호출.
     */
    fun finalizeOpenSession(now: Long, acc: SessionAccumulator) {
        closeCurrentSession(now, acc)
    }

    private fun closeCurrentSession(endTime: Long, acc: SessionAccumulator) {
        val app = currentForegroundApp ?: return
        val elapsed = endTime - foregroundStartTimestamp

        if (elapsed > 0) {
            acc.durationsMs[app] = (acc.durationsMs[app] ?: 0L) + elapsed

            // 타임라인은 epoch(ms)로 저장 → 영상 프레임 타임스탬프와 직접 매칭 가능
            acc.timeline.add(
                JSONObject().apply {
                    put("package", app)
                    put("app_name", appNameResolver.resolve(app))
                    put("start_epoch_ms", foregroundStartTimestamp)
                    put("end_epoch_ms", endTime)
                    put("duration_sec", (elapsed / 1000).toInt())
                }
            )
        }
        currentForegroundApp = null
    }
}
