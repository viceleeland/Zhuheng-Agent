# 江擎 Windows 客户端 1.0.1 — 水利工程智能协作

Windows 10/11 x64 桌面客户端，使用 .NET Framework 4.8 和 Microsoft Edge WebView2 Evergreen Runtime。安装包为真实 Inno Setup EXE，按当前用户安装，创建桌面与开始菜单快捷方式，支持系统设置中卸载。客户端关闭不会关闭工程服务器。

默认服务器为 https://viceleeyoung.tail3f46fb.ts.net/changwei 。此地址属于 Tailscale 私网：客户端设备必须加入同一获授权网络，且服务器电脑和服务保持运行。可在“服务器设置”更换为自己的可信 HTTPS 服务器，不接受 HTTP、无效证书或 URL 内嵌凭据。

网页本身负责登录和工程业务。登录状态保存在当前用户的 WebView2 数据目录中，各 HTTPS 源按浏览器规则隔离。支持网页原生文件选择和下载提示。麦克风仅向当前可信服务器开放，并显示用户授权对话框；不会自动启动录音。没有浏览器到本机任意命令的桥接。实时转录仍需服务器配置百炼 API Key，本安装包不携带任何服务端密钥。

尚未购买代码签名证书，因此此验收构建未签名；Windows 可能显示未知发布者。WebView2 是微软签名组件；如缺运行时，客户端提示前往微软官网安装，不会绕过证书或静默安装其他组件。

## 重现构建

1. 使用 Windows 自带 .NET Framework C# 编译器：`C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe`。
2. 从官方 NuGet 下载并解压 Microsoft.Web.WebView2 **1.0.4191.47**：https://api.nuget.org/v3-flatcontainer/microsoft.web.webview2/1.0.4191.47/microsoft.web.webview2.1.0.4191.47.nupkg 。保存到 `work/windows-build/webview2-sdk`。
3. 从 Inno Setup 官网 https://jrsoftware.org/isdl.php 获取 **6.7.3** 构建器，验证数字签名后安装到 `work/windows-build/inno`。遵守其许可证，商业使用请查官方授权条件。
4. PowerShell 执行 `clients/windows/build.ps1`。可通过 `-SdkDirectory`、`-InnoCompiler`、`-OutputDirectory` 指定构建依赖和输出目录。
5. 运行构建目录中的 `ChangweiAgent.exe --smoke-test` 会打开真实客户端窗口，并在相邻 `smoke-evidence` 目录记录首次导航结果和页面截图。此参数只用于本机构建验收；不启用调试端口。

客户端设置和登录数据位置：`%LOCALAPPDATA%\ChangweiAgent\Desktop`。卸载保留此目录，便于重装后保留登录；如要清除登录，可在页面退出登录。

源码：Program.cs、app.manifest、ChangweiAgent.exe.config、setup.iss、build.ps1。安装器仅部署客户端文件，不部署后端、Docker或模型。

升级保持原 AppId、内部 ChangweiAgent.exe 文件名及 WebView2 用户数据路径，不清除已有登录。构建时还需源码包中的 clients/branding/jiangqing.ico，同一图标同时嵌入客户端和安装器。
