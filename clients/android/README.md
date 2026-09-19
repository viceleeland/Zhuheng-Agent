# 江擎 Android 客户端

副标题：水利工程智能协作。桌面图标沿用 `clients/branding/jiangqing.svg` 的门形结构和江水曲线，适配 Android 自适应图标的安全区域。

这是现有工程工作台的 Android WebView 客户端。包名 `org.changwei.mobile`，版本 `0.1.3`（versionCode 4），最低 Android 8.0 / API 26。默认连接 `https://viceleeyoung.tail3f46fb.ts.net/changwei`；“菜单 → 设置服务地址”可以更换 HTTPS 服务源。

默认 HTTPS 地址通过已开启的公网入口访问，手机可使用普通 Wi-Fi 或移动数据，无需安装 Tailscale。本机工程服务与隧道必须保持在线；若设置为其他内网地址，手机仍需连接对应网络。应用内使用原系统账号登录；账号、工程和权限均由现有后端管理。客户端不内置账号、JWT、模型 Key 或天气 Key，也不提供离线业务数据库。手机退出后登录态由本应用 WebView 的私有存储保留；更换服务源会清除本机网页登录态。

## 安装与使用

本版沿用 0.1.0 的包名与签名，可直接覆盖升级，通常不需要卸载；卸载会删除本机登录态。构建脚本核验原签名指纹，私钥缺失或被替换时会拒绝生成升级包。

1. 将 `jiangqing-android-0.1.3-local-test.apk` 传到手机，由手机文件管理器打开安装。如果系统提示安装来源，按设备提示仅允许本次使用的文件管理器安装。
2. 确认服务地址可访问，启动“江擎”。登录后可使用资料上传、五类业务填报、模块确认和成果下载。
3. 上传通过系统文件选择器选择 DOCX、XLSX、PDF、ZIP 等文件；不申请整个存储空间权限。
4. 下载支持页面生成的 `blob:` Word 文件。点击成果下载后，由系统“保存到”窗口选择位置，单次最多 30 MB。
5. 语音输入仍使用服务端的实时转录链路。需要服务端配置百炼 API Key；客户端会说明音频用途并申请麦克风权限，不申请相机权限。切到后台会停止采集并关闭当前语音 WebSocket，回到前台后可以重新开始。
6. 天气模块可点击“自动定位并获取”。应用仅在这次点击后说明用途并申请大致位置权限，用坐标识别附近县市；拒绝权限后仍可直接填写“歙县”“黄山市”等地名。

支持能够安装 Android APK 的手机系统。纯 HarmonyOS NEXT 不能直接运行本 APK。AudioWorklet 等网页能力依赖设备上实际的 Android System WebView 版本，建议更新系统 WebView。尚未用实体手机验证厂商系统兼容性。

## 安全边界

- 只在内置 WebView 加载已配置的 HTTPS 同源页面，HTTP 明文与混合内容禁止；证书错误一律中止。外部 HTTPS 链接需确认后交给外部浏览器。
- 原生层不读取登录 Token。下载的鉴权请求在同源网页内完成，原生层只接收用户要保存的文件字节。
- 下载通过指定 origin 的 `WebMessagePort` 传送，使用随机握手标识；没有向所有 iframe 暴露 `addJavascriptInterface`。
- 文件传输使用逐块确认并校验累计长度，系统保存位置由用户选择。文件名过滤路径与控制字符；不申请全盘读写权限。
- 关闭 Android 应用备份和 WebView 调试。SDK 和本地测试签名私钥不进入 APK，也不提交到源码。
- Manifest 声明联网、麦克风、音频设置和大致位置四项权限。位置只响应页面在前台发起的单次同源请求，不持续定位；音频设置用于 Chromium 的音频设备处理，麦克风采集仍需用户许可。依据为 [Chromium AudioManagerAndroid](https://chromium.googlesource.com/chromium/src/media/+/master/base/android/java/src/org/chromium/media/AudioManagerAndroid.java)。

## 构建

只使用本机 JDK 11 与 Google 官方 Android SDK Platform 34、Build-tools 34.0.0，不需要 Android Studio 或 Gradle。SDK 下载和解压在仓库 `work/android-sdk`，官方包信息与许可正文也保留在该目录。此次开发按用户授权接受 Android SDK 使用许可。

固定官方包：

| 组件 | Google 下载地址 | 官方清单 SHA-1 |
| --- | --- | --- |
| Platform 34 r3 | https://dl.google.com/android/repository/platform-34-ext7_r03.zip | `1f2e9478d6a7601425ceaa553311dc43191f103d` |
| Windows Build-tools 34.0.0 | https://dl.google.com/android/repository/build-tools_r34-windows.zip | `62cfde1b6fcc3ad12a4d2ba1b537e752768bfd47` |

SDK 目录结构为 `work/android-sdk/platform/android-34/android.jar` 和 `work/android-sdk/build-tools/android-14/`。可从仓库根目录执行：

```powershell
node --test clients/android/test/download-bridge.test.cjs
./clients/android/build.ps1
```

脚本执行真实 `aapt2 → javac → D8 → jar → zipalign → apksigner` 流程。APK、签名验证、Manifest 信息和 SHA-256 收据输出到 `outputs/android`。私钥只在被忽略的 `work/android-build/changwei-local-test.jks`；保留该文件才能为同一安装包后续升级签名。

**本包使用本地测试签名，且 `debuggable=false`。它不是商店发布或商业发行签名。** 本地测试证书密码是 Android 开发惯例 `android`，不是生产密钥保护方案；不要复用作正式发行身份。没有连接实体手机时，不把 APK 编译/签名验证称为安装或云端语音验收。

官方参考：[AAPT2](https://developer.android.com/tools/aapt2)、[apksigner](https://developer.android.com/tools/apksigner)、[WebView](https://developer.android.com/develop/ui/views/layout/webapps/webview)、[WebMessagePort](https://developer.android.com/reference/android/webkit/WebMessagePort)、[WebChromeClient](https://developer.android.com/reference/android/webkit/WebChromeClient)。
