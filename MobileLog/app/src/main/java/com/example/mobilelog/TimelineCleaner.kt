package com.example.mobilelog

import org.json.JSONObject

/**
 * 타임라인에서 발생하는 노이즈를 정리하는 유틸리티.
 *
 * 인증 앱의 OTP 화면, 생체인증 오버레이, 시스템 권한 팝업 등은
 * 짧은 시간 안에 MOVE_TO_FOREGROUND/MOVE_TO_BACKGROUND를 반복 발생시켜
 * 같은 앱이 수십 ms 간격으로 여러 번 끊어져 기록되는 경우가 많다.
 * 이를 그대로 두면 분석 시 노이즈가 되므로 2단계로 정리한다.
 *
 * 1) 병합: 같은 패키지의 연속된 구간이 짧은 간격(mergeGapMs)으로 떨어져 있으면 하나로 합침
 * 2) 필터: 병합 후에도 지속시간이 minDurationMs 미만인 아주 짧은 항목은 노이즈로 간주해 제거
 */
object TimelineCleaner {

    private const val DEFAULT_MERGE_GAP_MS = 1000L      // 1초 이내 재등장하면 같은 세션으로 병합
    private const val DEFAULT_MIN_DURATION_MS = 500L    // 병합 후에도 0.5초 미만이면 제거

    fun clean(
        timeline: List<JSONObject>,
        mergeGapMs: Long = DEFAULT_MERGE_GAP_MS,
        minDurationMs: Long = DEFAULT_MIN_DURATION_MS
    ): List<JSONObject> {
        if (timeline.isEmpty()) return timeline

        // 1) 같은 패키지 + 짧은 간격 → 병합
        val merged = mutableListOf<JSONObject>()
        var current = copyEntry(timeline[0])

        for (i in 1 until timeline.size) {
            val next = timeline[i]
            val samePackage = next.getString("package") == current.getString("package")
            val gap = next.getLong("start_epoch_ms") - current.getLong("end_epoch_ms")

            if (samePackage && gap in 0..mergeGapMs) {
                // 병합: 종료 시각만 늘리고 duration 재계산
                val newEnd = next.getLong("end_epoch_ms")
                current.put("end_epoch_ms", newEnd)
                current.put(
                    "duration_sec",
                    ((newEnd - current.getLong("start_epoch_ms")) / 1000).toInt()
                )
            } else {
                merged.add(current)
                current = copyEntry(next)
            }
        }
        merged.add(current)

        // 2) 병합 후에도 너무 짧은 항목은 노이즈로 간주해 제거
        return merged.filter { entry ->
            val durationMs = entry.getLong("end_epoch_ms") - entry.getLong("start_epoch_ms")
            durationMs >= minDurationMs
        }
    }

    private fun copyEntry(entry: JSONObject): JSONObject {
        return JSONObject(entry.toString())
    }
}
