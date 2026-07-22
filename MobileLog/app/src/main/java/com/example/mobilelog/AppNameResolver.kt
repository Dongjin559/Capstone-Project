package com.example.mobilelog

import android.content.Context
import android.content.pm.PackageManager

/**
 * 패키지명(예: com.kakao.talk)을 사람이 읽기 좋은 앱 이름(예: 카카오톡)으로 변환.
 * 매번 PackageManager를 조회하면 비용이 있어서 세션 동안은 캐시해서 재사용한다.
 */
class AppNameResolver(private val context: Context) {

    private val cache = mutableMapOf<String, String>()

    fun resolve(packageName: String): String {
        cache[packageName]?.let { return it }

        val name = try {
            val pm = context.packageManager
            val appInfo = pm.getApplicationInfo(packageName, 0)
            pm.getApplicationLabel(appInfo).toString()
        } catch (e: PackageManager.NameNotFoundException) {
            packageName // 삭제된 앱 등 조회 실패 시 패키지명 그대로 사용
        }

        cache[packageName] = name
        return name
    }
}
