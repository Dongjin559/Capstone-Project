package com.example.mobilelog

import android.content.Context
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import java.net.HttpURLConnection
import java.net.URL

/**
 * 로그 전송 + 실패 시 로컬(SharedPreferences) 큐에 저장했다가 재시도하는 업로더.
 * WorkManager 같은 별도 의존성 없이 가벼운 재시도 큐로 구현.
 */
object LogUploader {

    private const val TAG = "MobileLogUploader"
    private const val PREFS_NAME = "mobile_log_pending_queue"
    private const val KEY_QUEUE = "pending_json_array"
    private const val MAX_QUEUE_SIZE = 50 // 큐가 무한정 쌓이는 것 방지

    /**
     * 로그 전송 시도. 실패하면 로컬 큐에 저장해두고, 성공하면
     * 그동안 밀려있던 큐도 함께 비우기를 시도한다.
     */
    suspend fun uploadWithRetry(context: Context, jsonPayload: String) {
        val sent = trySend(context, jsonPayload)
        if (!sent) {
            enqueue(context, jsonPayload)
            Log.d(TAG, "⚠️ 전송 실패 → 로컬 큐에 저장됨 (다음 기회에 재시도)")
        } else {
            flushQueue(context)
        }
    }

    /**
     * 큐에 남아있는 실패 로그들을 순서대로 재전송 시도.
     * 서비스/모니터링이 새로 시작될 때 호출해주면 좋다.
     */
    suspend fun flushQueue(context: Context) {
        val queue = readQueue(context)
        if (queue.length() == 0) return

        val stillFailed = JSONArray()
        for (i in 0 until queue.length()) {
            val item = queue.optString(i)
            val ok = trySend(context, item)
            if (!ok) {
                stillFailed.put(item)
            }
        }
        writeQueue(context, stillFailed)

        if (stillFailed.length() == 0) {
            Log.d(TAG, "✅ 큐에 밀려있던 로그 전부 재전송 성공")
        } else {
            Log.d(TAG, "⏳ 재전송 후에도 ${stillFailed.length()}건 남음")
        }
    }

    private suspend fun trySend(context: Context, jsonPayload: String): Boolean =
        withContext(Dispatchers.IO) {
            try {
                val url = URL(AppConfig.getUploadEndpoint(context))
                val conn = url.openConnection() as HttpURLConnection
                conn.requestMethod = "POST"
                conn.setRequestProperty("Content-Type", "application/json; charset=UTF-8")
                conn.connectTimeout = 5000
                conn.readTimeout = 5000
                conn.doOutput = true

                conn.outputStream.use { it.write(jsonPayload.toByteArray(Charsets.UTF_8)) }

                val success = conn.responseCode == HttpURLConnection.HTTP_OK
                conn.disconnect()

                if (success) {
                    Log.d(TAG, "✅ PC 서버로 전송 성공")
                } else {
                    Log.d(TAG, "❌ 전송 실패: 에러 코드 ${conn.responseCode}")
                }
                success
            } catch (e: Exception) {
                Log.e(TAG, "서버 전송 중 통신 에러: ${e.message}")
                false
            }
        }

    private fun enqueue(context: Context, jsonPayload: String) {
        val queue = readQueue(context)
        queue.put(jsonPayload)
        // 큐가 너무 커지면 오래된 것부터 버림
        while (queue.length() > MAX_QUEUE_SIZE) {
            queue.remove(0)
        }
        writeQueue(context, queue)
    }

    private fun readQueue(context: Context): JSONArray {
        val raw = prefs(context).getString(KEY_QUEUE, null) ?: return JSONArray()
        return try {
            JSONArray(raw)
        } catch (e: Exception) {
            JSONArray()
        }
    }

    private fun writeQueue(context: Context, queue: JSONArray) {
        prefs(context).edit().putString(KEY_QUEUE, queue.toString()).apply()
    }

    private fun prefs(context: Context) =
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
}
