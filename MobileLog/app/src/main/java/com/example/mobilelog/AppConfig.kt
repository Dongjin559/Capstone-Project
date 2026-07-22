package com.example.mobilelog

import android.content.Context
import android.content.SharedPreferences

/**
 * 서버 주소 등 외부 설정을 SharedPreferences에 저장/조회하는 헬퍼.
 * 기존에 코드에 하드코딩되어 있던 IP(192.168.0.229)를 분리하기 위한 용도.
 * MainActivity의 입력창에서 값을 바꾸면 앱을 재빌드하지 않아도 즉시 반영된다.
 */
object AppConfig {

    private const val PREFS_NAME = "mobile_log_config"
    private const val KEY_SERVER_URL = "server_base_url"

    // 최초 실행 시 기본값 (사용자가 설정 화면에서 언제든 변경 가능)
    private const val DEFAULT_SERVER_URL = "http://192.168.0.229:5000"

    private fun prefs(context: Context): SharedPreferences =
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    fun getServerBaseUrl(context: Context): String {
        return prefs(context).getString(KEY_SERVER_URL, DEFAULT_SERVER_URL) ?: DEFAULT_SERVER_URL
    }

    fun setServerBaseUrl(context: Context, url: String) {
        prefs(context).edit().putString(KEY_SERVER_URL, url.trim()).apply()
    }

    fun getUploadEndpoint(context: Context): String {
        val base = getServerBaseUrl(context).trimEnd('/')
        return "$base/upload_mobile_log"
    }
}
