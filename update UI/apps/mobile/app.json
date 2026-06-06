{
  "expo": {
    "name": "Anything mobile app",
    "version": "1.0.0",
    "orientation": "portrait",
    "icon": "./assets/images/icon.png",
    "userInterfaceStyle": "automatic",
    "newArchEnabled": true,
    "ios": {
      "supportsTablet": true,
      "infoPlist": {
        "ITSAppUsesNonExemptEncryption": false
      }
    },
    "android": {
      "adaptiveIcon": {
        "foregroundImage": "./assets/images/adaptive-icon.png",
        "backgroundColor": "#ffffff"
      },
      "permissions": [
        "android.permission.RECORD_AUDIO",
        "android.permission.MODIFY_AUDIO_SETTINGS"
      ],
      "package": "xyz.create.CreateExpoEnvironment"
    },
    "plugins": [
      [
        "expo-router",
        {
          "sitemap": false
        }
      ],
      [
        "expo-splash-screen",
        {
          "image": "./assets/images/splash-icon.png",
          "imageWidth": 200,
          "resizeMode": "contain"
        }
      ],
      "expo-audio",
      [
        "expo-build-properties",
        {
          "ios": {
            "useFrameworks": "static"
          }
        }
      ],
      [
        "expo-video",
        {
          "supportsBackgroundPlayback": true,
          "supportsPictureInPicture": true
        }
      ],
      "expo-font",
      "expo-secure-store",
      "expo-web-browser",
      "@sentry/react-native/expo",
      [
        "react-native-google-mobile-ads",
        {
          "androidAppId": "ca-app-pub-3940256099942544~3347511713",
          "iosAppId": "ca-app-pub-3940256099942544~1458002511"
        }
      ]
    ],
    "web": {
      "bundler": "metro",
      "favicon": "./assets/images/favicon.png"
    },
    "experiments": {
      "typedRoutes": true
    },
    "extra": {
      "router": {
        "origin": false
      }
    }
  }
}