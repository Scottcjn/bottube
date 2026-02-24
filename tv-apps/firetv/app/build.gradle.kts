plugins {
  id("com.android.application") version "8.5.2"
  kotlin("android") version "1.9.24"
}

android {
  namespace = "ai.bottube.tv"
  compileSdk = 34
  defaultConfig {
    applicationId = "ai.bottube.tv"
    minSdk = 24
    targetSdk = 34
    versionCode = 1
    versionName = "0.1.0"
  }
}

dependencies {
  implementation("androidx.leanback:leanback:1.2.0")
  implementation("com.squareup.okhttp3:okhttp:4.12.0")
}
