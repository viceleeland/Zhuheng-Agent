using System;
using System.Drawing;
using System.IO;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

[assembly: System.Reflection.AssemblyTitle("江擎")]
[assembly: System.Reflection.AssemblyDescription("水利工程智能协作")]
[assembly: System.Reflection.AssemblyProduct("江擎")]
[assembly: System.Reflection.AssemblyVersion("1.0.2.0")]
[assembly: System.Reflection.AssemblyFileVersion("1.0.2.0")]

namespace ChangweiDesktop {
    static class Program {
        [STAThread] static void Main(string[] args) {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            using (var running = new System.Threading.Mutex(false, @"Local\JiangqingDesktopRunning")) { Application.Run(new MainWindow(Array.IndexOf(args, "--smoke-test") >= 0)); }
        }
    }

    sealed class MainWindow : Form {
        const string DefaultServer = "https://viceleeyoung.tail3f46fb.ts.net/changwei";
        readonly string dataDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "ChangweiAgent", "Desktop");
        readonly WebView2 browser = new WebView2();
        readonly ToolStripLabel status = new ToolStripLabel("正在连接…");
        readonly bool smoke;
        Uri server;
        bool captured;

        public MainWindow(bool smokeTest) {
            smoke = smokeTest;
            Text = "江擎 · 水利工程智能协作";
            Width = 1280; Height = 860; MinimumSize = new Size(820, 600);
            StartPosition = FormStartPosition.CenterScreen;
            Font = new Font("Microsoft YaHei UI", 9);
            Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
            Directory.CreateDirectory(dataDir);
            string saved = DefaultServer;
            try { if (File.Exists(Path.Combine(dataDir, "server.txt"))) saved = File.ReadAllText(Path.Combine(dataDir, "server.txt")).Trim(); } catch (IOException) { }
            server = ValidServer(saved) ?? new Uri(DefaultServer);
            var bar = new ToolStrip();
            bar.GripStyle = ToolStripGripStyle.Hidden;
            bar.Padding = new Padding(8, 5, 8, 5);
            var home = new ToolStripButton("工作台");
            home.Click += delegate { if (browser.CoreWebView2 != null) browser.CoreWebView2.Navigate(server.AbsoluteUri); };
            var refresh = new ToolStripButton("刷新");
            refresh.Click += delegate { if (browser.CoreWebView2 != null) browser.Reload(); };
            var settings = new ToolStripButton("服务器设置");
            settings.Click += delegate { ChangeServer(); };
            var mic = new ToolStripButton("麦克风权限");
            mic.Click += delegate { MessageBox.Show(this, "点击页面中的实时转录后，客户端会显示麦克风授权提示。\n允许后仍受 Windows 麦克风隐私设置控制。\n关闭客户端不会停止服务器；云端实时识别还需管理员配置百炼密钥。", "麦克风", MessageBoxButtons.OK, MessageBoxIcon.Information); };
            bar.Items.Add(home); bar.Items.Add(refresh); bar.Items.Add(settings); bar.Items.Add(mic);
            bar.Items.Add(new ToolStripSeparator()); bar.Items.Add(status);
            browser.Dock = DockStyle.Fill;
            Controls.Add(browser); Controls.Add(bar);
            Shown += async delegate { await InitializeBrowser(); };
        }

        internal static Uri ValidServer(string value) {
            Uri uri;
            if (!Uri.TryCreate(value, UriKind.Absolute, out uri) || uri.Scheme != "https" ||
                !String.IsNullOrEmpty(uri.UserInfo) || !String.IsNullOrEmpty(uri.Query) || !String.IsNullOrEmpty(uri.Fragment)) return null;
            if (uri.AbsolutePath == "/") return new Uri(uri.GetLeftPart(UriPartial.Authority) + "/changwei");
            return uri;
        }

        bool Trusted(string value) {
            Uri uri;
            return Uri.TryCreate(value, UriKind.Absolute, out uri) && uri.Scheme == "https" &&
                String.IsNullOrEmpty(uri.UserInfo) && String.Equals(uri.GetLeftPart(UriPartial.Authority), server.GetLeftPart(UriPartial.Authority), StringComparison.OrdinalIgnoreCase);
        }

        async Task InitializeBrowser() {
            try {
                var env = await CoreWebView2Environment.CreateAsync(null, Path.Combine(dataDir, "WebView2"));
                await browser.EnsureCoreWebView2Async(env);
                var core = browser.CoreWebView2;
                core.Settings.AreDevToolsEnabled = false;
                core.Settings.AreHostObjectsAllowed = false;
                core.Settings.IsWebMessageEnabled = false;
                core.Settings.AreDefaultScriptDialogsEnabled = true;
                core.Settings.IsStatusBarEnabled = true;
                core.NavigationStarting += delegate(object sender, CoreWebView2NavigationStartingEventArgs e) {
                    if (!Trusted(e.Uri)) { e.Cancel = true; OpenExternal(e.Uri); }
                    else status.Text = "连接 " + server.Host + "…";
                };
                core.NewWindowRequested += delegate(object sender, CoreWebView2NewWindowRequestedEventArgs e) {
                    e.Handled = true;
                    if (Trusted(e.Uri)) core.Navigate(e.Uri); else OpenExternal(e.Uri);
                };
                core.ServerCertificateErrorDetected += delegate(object sender, CoreWebView2ServerCertificateErrorDetectedEventArgs e) {
                    e.Action = CoreWebView2ServerCertificateErrorAction.Cancel;
                    status.Text = "HTTPS 证书无效，已阻止连接";
                };
                core.PermissionRequested += delegate(object sender, CoreWebView2PermissionRequestedEventArgs e) {
                    e.SavesInProfile = false;
                    e.State = CoreWebView2PermissionState.Deny;
                    if (e.PermissionKind == CoreWebView2PermissionKind.Microphone && Trusted(e.Uri)) {
                        var answer = MessageBox.Show(this, "允许 " + server.Host + " 使用麦克风进行实时转录？\n音频会发送到当前服务器配置的云端识别服务。", "麦克风授权", MessageBoxButtons.YesNo, MessageBoxIcon.Question);
                        e.State = answer == DialogResult.Yes ? CoreWebView2PermissionState.Allow : CoreWebView2PermissionState.Deny;
                    }
                };
                core.NavigationCompleted += async delegate(object sender, CoreWebView2NavigationCompletedEventArgs e) {
                    status.Text = e.IsSuccess ? "已连接 · " + server.Host : "连接失败 · 请检查服务器和网络后刷新";
                    if (smoke && !captured) {
                        captured = true;
                        try {
                        await Task.Delay(3000);
                        string evidence = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "smoke-evidence");
                        Directory.CreateDirectory(evidence);
                        using (var image = File.Create(Path.Combine(evidence, "windows-client.png")))
                            await core.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png, image);
                        File.WriteAllText(Path.Combine(evidence, "navigation.txt"), "Success=" + e.IsSuccess + "\nHttpStatus=" + e.HttpStatusCode + "\nWebError=" + e.WebErrorStatus + "\nRuntime=" + env.BrowserVersionString + "\nServer=" + server.AbsoluteUri + "\nTitle=" + core.DocumentTitle);
                        } finally { Close(); }
                    }
                };
                core.Navigate(server.AbsoluteUri);
            } catch (WebView2RuntimeNotFoundException) {
                status.Text = "缺少 Microsoft Edge WebView2 Runtime";
                MessageBox.Show(this, "请先从 Microsoft 官方安装 WebView2 Evergreen Runtime，再重新打开。\nhttps://developer.microsoft.com/microsoft-edge/webview2/", "需要 WebView2", MessageBoxButtons.OK, MessageBoxIcon.Information);
            } catch (Exception ex) {
                status.Text = "浏览器初始化失败";
                MessageBox.Show(this, "客户端无法初始化浏览器：" + ex.GetType().Name + "\n请检查 WebView2 Runtime 或重新启动客户端。", "启动失败", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        void OpenExternal(string value) {
            Uri uri;
            if (!Uri.TryCreate(value, UriKind.Absolute, out uri) || uri.Scheme != "https" || !String.IsNullOrEmpty(uri.UserInfo)) return;
            if (MessageBox.Show(this, "此链接不属于当前服务器，是否在系统浏览器打开？\n" + uri.Host, "外部链接", MessageBoxButtons.YesNo, MessageBoxIcon.Question) == DialogResult.Yes)
                System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(uri.AbsoluteUri) { UseShellExecute = true });
        }

        void ChangeServer() {
            using (var dialog = new Form()) {
                dialog.Text = "可信服务器设置"; dialog.Width = 620; dialog.Height = 200;
                dialog.FormBorderStyle = FormBorderStyle.FixedDialog; dialog.StartPosition = FormStartPosition.CenterParent;
                dialog.MaximizeBox = false; dialog.MinimizeBox = false;
                var label = new Label { Left = 15, Top = 15, Width = 570, Height = 35, Text = "只接受有效 HTTPS 地址。请确认服务器可信后登录和上传资料。" };
                var input = new TextBox { Left = 15, Top = 55, Width = 570, Text = server.AbsoluteUri };
                var ok = new Button { Text = "保存并连接", Left = 365, Top = 100, Width = 110 };
                var cancel = new Button { Text = "取消", Left = 485, Top = 100, Width = 100, DialogResult = DialogResult.Cancel };
                ok.Click += delegate {
                    Uri candidate = ValidServer(input.Text.Trim());
                    if (candidate == null) { MessageBox.Show(dialog, "请输入 HTTPS 地址，不要包含账号密码、查询参数或片段。"); return; }
                    server = candidate;
                    File.WriteAllText(Path.Combine(dataDir, "server.txt"), server.AbsoluteUri);
                    dialog.DialogResult = DialogResult.OK;
                };
                dialog.Controls.AddRange(new Control[] { label, input, ok, cancel }); dialog.AcceptButton = ok; dialog.CancelButton = cancel;
                if (dialog.ShowDialog(this) == DialogResult.OK && browser.CoreWebView2 != null) browser.CoreWebView2.Navigate(server.AbsoluteUri);
            }
        }
    }
}
