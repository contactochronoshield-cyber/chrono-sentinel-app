[app]
title = Chrono Sentinel
package.name = chronosentinel
package.domain = com.chronoshield
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 0.2.0
requirements = python3,kivy,plyer

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,ACCESS_NETWORK_STATE,POST_NOTIFICATIONS
android.api = 33
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a,armeabi-v7a
android.accept_sdk_license = True

icon.filename = %(source.dir)s/icon.png

[buildozer]
log_level = 2
warn_on_root = 1
