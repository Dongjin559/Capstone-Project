# AndroidManifest.xml에 추가해야 할 내용

기존 프로젝트의 `AndroidManifest.xml`에 아래 내용을 추가해주세요.

## 1. 권한 (`<manifest>` 태그 안, `<application>` 밖)

```xml
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.PACKAGE_USAGE_STATS"
    tools:ignore="ProtectedPermissions" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_DATA_SYNC" />
<uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
```

- `PACKAGE_USAGE_STATS`는 일반 권한이 아니라 사용자가 설정 화면에서 직접 허용해야 하는
  특수 권한이라 매니페스트에 선언해도 앱 실행만으로는 부여되지 않습니다.
  (기존 코드의 `requestUsageStatsPermission()`으로 유도하는 흐름은 그대로 유지)
- `tools:ignore="ProtectedPermissions"`를 쓰려면 `xmlns:tools="http://schemas.android.com/tools"`가
  `<manifest>` 태그에 선언되어 있어야 합니다.

## 2. 서비스 등록 (`<application>` 태그 안)

```xml
<service
    android:name=".LogCollectionService"
    android:foregroundServiceType="dataSync"
    android:exported="false" />
```

## 3. (선택) 로컬 HTTP 통신 허용

`http://` 평문 통신을 그대로 쓰는 경우, Android 9(API 28) 이상에서는 기본적으로
cleartext 트래픽이 차단됩니다. 테스트 단계에서 계속 HTTP를 쓰려면:

```xml
<application
    android:usesCleartextTraffic="true"
    ...>
```

정식 배포 전에는 HTTPS로 전환하는 것을 권장합니다.
