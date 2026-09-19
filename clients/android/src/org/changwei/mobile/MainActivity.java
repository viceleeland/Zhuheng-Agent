package org.changwei.mobile;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.net.http.SslError;
import android.os.Bundle;
import android.util.Base64;
import android.view.Gravity;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.PermissionRequest;
import android.webkit.SslErrorHandler;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebMessage;
import android.webkit.WebMessagePort;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebStorage;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** HTTPS 工程工作台容器：页面拥有身份，原生层只负责用户授权的设备能力。 */
public class MainActivity extends Activity {
    private static final int PICK_FILES = 100;
    private static final int SAVE_FILE = 101;
    private static final int RECORD_AUDIO = 102;
    private static final int MAX_DOWNLOAD = 30 * 1024 * 1024;
    private final ExecutorService writer = Executors.newSingleThreadExecutor();
    private WebView web;
    private ProgressBar progress;
    private LinearLayout errorPanel;
    private TextView errorText;
    private TextView address;
    private SharedPreferences preferences;
    private String server;
    private String bridgeSource;
    private boolean foreground;
    private boolean trustedPage;
    private int pageGeneration;
    private int bridgeGeneration = -1;
    private PermissionRequest audioRequest;
    private boolean approvedAudio;
    private ValueCallback<Uri[]> fileCallback;
    private WebMessagePort downloadPort;
    private ByteArrayOutputStream incoming;
    private int expectedSize;
    private String downloadName;
    private String downloadMime;
    private byte[] pendingDownload;
    private boolean saving;

    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        preferences = getSharedPreferences("changwei-client", MODE_PRIVATE);
        try {
            server = ServerPolicy.normalize(preferences.getString("server", ServerPolicy.DEFAULT_SERVER));
        } catch (IllegalArgumentException error) {
            server = ServerPolicy.DEFAULT_SERVER;
        }
        try (InputStream input = getAssets().open("download-bridge.js")) {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            byte[] buffer = new byte[4096];
            int count;
            while ((count = input.read(buffer)) != -1) bytes.write(buffer, 0, count);
            bridgeSource = bytes.toString("UTF-8");
        } catch (Exception error) {
            bridgeSource = "";
        }
        buildScreen();
        configureWebView();
        web.loadUrl(server + "/changwei");
    }

    private void buildScreen() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.WHITE);
        LinearLayout toolbar = new LinearLayout(this);
        toolbar.setGravity(Gravity.CENTER_VERTICAL);
        toolbar.setPadding(dp(6), 0, dp(6), 0);
        toolbar.addView(button("返回", v -> onBackPressed()));
        address = new TextView(this);
        address.setText(R.string.app_name);
        address.setTextColor(Color.rgb(18, 57, 87));
        address.setTextSize(16);
        address.setTypeface(android.graphics.Typeface.DEFAULT_BOLD);
        address.setGravity(Gravity.CENTER);
        LinearLayout brand = new LinearLayout(this);
        brand.setOrientation(LinearLayout.VERTICAL);
        brand.setGravity(Gravity.CENTER);
        brand.addView(address);
        TextView subtitle = new TextView(this);
        subtitle.setText(R.string.app_subtitle);
        subtitle.setTextSize(10);
        subtitle.setTextColor(Color.rgb(83, 102, 118));
        subtitle.setGravity(Gravity.CENTER);
        brand.addView(subtitle);
        toolbar.addView(brand, new LinearLayout.LayoutParams(0, dp(48), 1));
        toolbar.addView(button("菜单", v -> showMenu()));
        root.addView(toolbar, new LinearLayout.LayoutParams(-1, dp(48)));
        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setMax(100);
        root.addView(progress, new LinearLayout.LayoutParams(-1, dp(3)));
        FrameLayout body = new FrameLayout(this);
        web = new WebView(this);
        body.addView(web, new FrameLayout.LayoutParams(-1, -1));
        errorPanel = new LinearLayout(this);
        errorPanel.setOrientation(LinearLayout.VERTICAL);
        errorPanel.setGravity(Gravity.CENTER);
        errorPanel.setPadding(dp(28), dp(24), dp(28), dp(24));
        errorPanel.setBackgroundColor(Color.rgb(245, 248, 248));
        errorText = new TextView(this);
        errorText.setTextSize(17);
        errorText.setLineSpacing(dp(7), 1);
        errorPanel.addView(errorText);
        errorPanel.addView(button("重新连接", v -> web.loadUrl(server + "/changwei")));
        errorPanel.addView(button("设置服务地址", v -> showServerDialog()));
        errorPanel.setVisibility(View.GONE);
        body.addView(errorPanel, new FrameLayout.LayoutParams(-1, -1));
        root.addView(body, new LinearLayout.LayoutParams(-1, 0, 1));
        setContentView(root);
    }

    private Button button(String label, View.OnClickListener listener) {
        Button button = new Button(this);
        button.setText(label);
        button.setTextSize(14);
        button.setMinWidth(dp(64));
        button.setMinimumWidth(dp(64));
        button.setOnClickListener(listener);
        return button;
    }

    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }

    private void configureWebView() {
        WebView.setWebContentsDebuggingEnabled(false);
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(true);
        settings.setAllowFileAccessFromFileURLs(false);
        settings.setAllowUniversalAccessFromFileURLs(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setSafeBrowsingEnabled(true);
        settings.setSupportMultipleWindows(false);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setUserAgentString(settings.getUserAgentString() + " JiangqingMobile/0.1.1");
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false);
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                String url = request.getUrl().toString();
                if (ServerPolicy.sameOrigin(server, url)) return false;
                if (request.isForMainFrame() && "https".equals(request.getUrl().getScheme())) {
                    confirmExternal(request.getUrl());
                }
                return true;
            }
            @Override public void onPageStarted(WebView view, String url, android.graphics.Bitmap icon) {
                pageGeneration++;
                trustedPage = ServerPolicy.sameOrigin(server, url);
                closePort();
                cancelAudioRequest();
                errorPanel.setVisibility(View.GONE);
                progress.setVisibility(View.VISIBLE);
                if (!trustedPage) {
                    view.stopLoading();
                    showError("已阻止非工程服务页面。请从菜单设置正确的 HTTPS 地址。");
                }
            }
            @Override public void onPageFinished(WebView view, String url) {
                if (!trustedPage || !ServerPolicy.sameOrigin(server, url)) return;
                progress.setVisibility(View.GONE);
                CookieManager.getInstance().flush();
                installDownloadBridge();
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) showError("暂时无法连接工程服务。\n\n请确认手机已连接同一 Tailscale 网络，电脑在线且工程服务正在运行。\n\n" + server);
            }
            @Override public void onReceivedHttpError(WebView view, WebResourceRequest request, WebResourceResponse response) {
                if (request.isForMainFrame()) showError("工程服务返回 HTTP " + response.getStatusCode() + "。请检查电脑端服务后重试。");
            }
            @Override public void onReceivedSslError(WebView view, SslErrorHandler handler, SslError error) {
                handler.cancel();
                showError("HTTPS 证书验证失败，已停止连接。请检查手机日期和服务证书；客户端不会忽略证书错误。");
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override public void onProgressChanged(WebView view, int value) { progress.setProgress(value); }
            @Override public void onPermissionRequest(PermissionRequest request) { requestAudio(request); }
            @Override public void onPermissionRequestCanceled(PermissionRequest request) {
                if (audioRequest == request) audioRequest = null;
            }
            @Override public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType("*/*");
                intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, params.getMode() == FileChooserParams.MODE_OPEN_MULTIPLE);
                intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                try { startActivityForResult(intent, PICK_FILES); }
                catch (ActivityNotFoundException error) {
                    fileCallback.onReceiveValue(null);
                    fileCallback = null;
                    toast("此设备没有可用的系统文件选择器。");
                }
                return true;
            }
        });
        web.setDownloadListener((url, agent, disposition, mime, length) -> {
            if (downloadPort == null) { toast("页面仍在加载，请稍后重新点击下载。"); return; }
            if (!trustedPage || !(ServerPolicy.sameOrigin(server, url)
                    || (url.startsWith("blob:") && ServerPolicy.sameOrigin(server, url.substring(5))))) {
                toast("只能保存当前工程服务的文件。");
                return;
            }
            String name = android.webkit.URLUtil.guessFileName(url, disposition, mime);
            web.evaluateJavascript("window.__cwDownload && window.__cwDownload(" + JSONObject.quote(url)
                    + "," + JSONObject.quote(name) + ")", null);
        });
    }

    private void requestAudio(PermissionRequest request) {
        boolean audioOnly = request.getResources().length == 1
                && PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(request.getResources()[0]);
        if (!foreground || !trustedPage || !audioOnly || !ServerPolicy.sameOrigin(server, request.getOrigin().toString())) {
            request.deny();
            return;
        }
        cancelAudioRequest();
        audioRequest = request;
        new AlertDialog.Builder(this).setTitle("允许本次实时语音？")
                .setMessage("麦克风音频将经当前工程服务实时发送至云端转录。只在你点击允许后启用，退出到后台会停止。\n\n" + server)
                .setNegativeButton("不允许", (dialog, which) -> denyAudio(request))
                .setOnCancelListener(dialog -> denyAudio(request))
                .setPositiveButton("允许", (dialog, which) -> {
                    if (audioRequest != request || !foreground) return;
                    if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) grantAudio();
                    else requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, RECORD_AUDIO);
                }).show();
    }

    private void grantAudio() {
        PermissionRequest request = audioRequest;
        audioRequest = null;
        approvedAudio = false;
        if (request == null) return;
        if (foreground && trustedPage && ServerPolicy.sameOrigin(server, request.getOrigin().toString())) {
            request.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});
        } else request.deny();
    }

    private void denyAudio(PermissionRequest request) {
        if (audioRequest == request) { audioRequest = null; request.deny(); }
    }

    private void cancelAudioRequest() {
        if (audioRequest != null) { audioRequest.deny(); audioRequest = null; }
        approvedAudio = false;
    }

    @Override public void onRequestPermissionsResult(int code, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(code, permissions, results);
        if (code != RECORD_AUDIO) return;
        if (results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED) {
            approvedAudio = true;
            if (foreground) grantAudio();
        }
        else { cancelAudioRequest(); toast("未获得麦克风权限，可继续文字填报。"); }
    }

    private void installDownloadBridge() {
        if (downloadPort != null || bridgeSource.isEmpty() || bridgeGeneration == pageGeneration) return;
        final int generation = pageGeneration;
        bridgeGeneration = generation;
        String marker = "changwei-native-" + UUID.randomUUID();
        web.evaluateJavascript(bridgeSource.replace("__NATIVE_MARKER__", JSONObject.quote(marker)), result -> {
            if (pageGeneration != generation || !trustedPage || !ServerPolicy.sameOrigin(server, web.getUrl())) return;
            WebMessagePort[] ports = web.createWebMessageChannel();
            downloadPort = ports[0];
            downloadPort.setWebMessageCallback(new WebMessagePort.WebMessageCallback() {
                @Override public void onMessage(WebMessagePort port, WebMessage message) { receiveDownload(port, message); }
            });
            web.postWebMessage(new WebMessage(marker, new WebMessagePort[]{ports[1]}), Uri.parse(server));
        });
    }

    private void receiveDownload(WebMessagePort port, WebMessage message) {
        if (port != downloadPort || !trustedPage) return;
        try {
            String raw = message.getData();
            if (raw == null || raw.length() > 100000) throw new IllegalArgumentException("文件分块过大。");
            JSONObject packet = new JSONObject(raw);
            String type = packet.getString("type");
            if (type.equals("cancel")) { incoming = null; return; }
            if (type.equals("start")) {
                if (incoming != null || pendingDownload != null || saving) throw new IllegalArgumentException("请先完成当前文件的保存。");
                expectedSize = packet.getInt("size");
                if (expectedSize < 1 || expectedSize > MAX_DOWNLOAD) throw new IllegalArgumentException("文件大小须在 1 字节至 30 MB 之间。");
                downloadName = ServerPolicy.filename(packet.optString("name"));
                downloadMime = packet.optString("mime", "application/octet-stream");
                if (!downloadMime.matches("[a-zA-Z0-9.+-]+/[a-zA-Z0-9.+-]+")) downloadMime = "application/octet-stream";
                incoming = new ByteArrayOutputStream(Math.min(expectedSize, 65536));
            } else if (type.equals("chunk")) {
                if (incoming == null) throw new IllegalArgumentException("下载尚未开始。");
                byte[] bytes = Base64.decode(packet.getString("data"), Base64.NO_WRAP);
                if (bytes.length > 49152 || incoming.size() + bytes.length > expectedSize) throw new IllegalArgumentException("文件分块大小不匹配。");
                incoming.write(bytes, 0, bytes.length);
            } else if (type.equals("finish")) {
                if (incoming == null || incoming.size() != expectedSize) throw new IllegalArgumentException("文件接收不完整，请重试。");
                pendingDownload = incoming.toByteArray();
                incoming = null;
                Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType(downloadMime);
                intent.putExtra(Intent.EXTRA_TITLE, downloadName);
                try { startActivityForResult(intent, SAVE_FILE); }
                catch (ActivityNotFoundException error) {
                    pendingDownload = null;
                    throw new IllegalArgumentException("此设备没有可用的系统保存位置选择器。");
                }
            } else throw new IllegalArgumentException("未知下载指令。");
            port.postMessage(new WebMessage("{\"ok\":true}"));
        } catch (JSONException | IllegalArgumentException error) {
            incoming = null;
            port.postMessage(new WebMessage("{\"ok\":false,\"error\":" + JSONObject.quote("保存失败：" + error.getMessage()) + "}"));
        }
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == PICK_FILES && fileCallback != null) {
            ArrayList<Uri> selected = new ArrayList<>();
            if (resultCode == RESULT_OK && data != null) {
                ClipData clips = data.getClipData();
                if (clips != null) {
                    for (int i = 0; i < Math.min(clips.getItemCount(), 100); i++) addContentUri(selected, clips.getItemAt(i).getUri());
                } else addContentUri(selected, data.getData());
            }
            fileCallback.onReceiveValue(selected.isEmpty() ? null : selected.toArray(new Uri[0]));
            fileCallback = null;
        }
        if (requestCode == SAVE_FILE) {
            byte[] bytes = pendingDownload;
            pendingDownload = null;
            Uri uri = data == null ? null : data.getData();
            if (resultCode != RESULT_OK) { toast("已取消保存。"); return; }
            if (bytes == null || uri == null || !"content".equals(uri.getScheme())) { toast("文件数据已失效，请重新下载。"); return; }
            saving = true;
            writer.execute(() -> {
                boolean success = false;
                try (OutputStream stream = getContentResolver().openOutputStream(uri, "wt")) {
                    if (stream == null) throw new IllegalStateException("No output stream");
                    stream.write(bytes);
                    stream.flush();
                    success = true;
                } catch (Exception ignored) { /* 不把文件 URI、内容或账户信息写入日志。 */ }
                final boolean saved = success;
                runOnUiThread(() -> { saving = false; if (!isDestroyed()) toast(saved ? "成果已保存到你选择的位置。" : "保存失败，请检查存储空间并重新下载。"); });
            });
        }
    }

    private void addContentUri(ArrayList<Uri> items, Uri uri) {
        if (uri != null && "content".equals(uri.getScheme())) items.add(uri);
    }

    private void showMenu() {
        new AlertDialog.Builder(this).setTitle(R.string.app_name)
                .setItems(new String[]{"刷新当前页", "工程首页", "设置服务地址", "连接与版本说明"}, (dialog, which) -> {
                    if (which == 0) web.reload();
                    else if (which == 1) web.loadUrl(server + "/changwei");
                    else if (which == 2) showServerDialog();
                    else new AlertDialog.Builder(this).setTitle("江擎 · 本地试用版 0.1.1")
                            .setMessage("这是连接现有工程服务的 Android 客户端，业务数据仍在电脑端。\n\n手机需登录同一 Tailscale 网络；电脑和服务必须在线。仅支持可安装 Android APK 的系统，不支持纯 HarmonyOS NEXT。\n\n实时语音需要服务端配置百炼 Key。建议更新 Android System WebView。\n\n本包使用本地测试签名；登录态仅留在此应用的 WebView 内。\n\n" + server)
                            .setPositiveButton("知道了", null).show();
                }).show();
    }

    private void showServerDialog() {
        EditText input = new EditText(this);
        input.setSingleLine(true);
        input.setInputType(android.text.InputType.TYPE_CLASS_TEXT | android.text.InputType.TYPE_TEXT_VARIATION_URI);
        input.setText(server);
        AlertDialog dialog = new AlertDialog.Builder(this).setTitle("HTTPS 服务地址")
                .setMessage("填写域名，可带端口。更换服务会清除本机网页登录状态；不会删除工程数据。")
                .setView(input).setNegativeButton("取消", null).setPositiveButton("连接", null).create();
        dialog.setOnShowListener(ignored -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
            final String next;
            try { next = ServerPolicy.normalize(input.getText().toString()); }
            catch (IllegalArgumentException error) { input.setError(error.getMessage()); return; }
            if (next.equals(server)) { dialog.dismiss(); web.loadUrl(server + "/changwei"); return; }
            trustedPage = false;
            web.stopLoading();
            closePort();
            cancelAudioRequest();
            web.loadUrl("about:blank");
            WebStorage.getInstance().deleteAllData();
            CookieManager.getInstance().removeAllCookies(removed -> {
                server = next;
                preferences.edit().putString("server", server).apply();
                web.clearCache(true);
                web.clearHistory();
                web.loadUrl(server + "/changwei");
            });
            dialog.dismiss();
        }));
        dialog.show();
    }

    private void confirmExternal(Uri uri) {
        new AlertDialog.Builder(this).setTitle("在浏览器打开外部链接？")
                .setMessage(uri.getHost()).setNegativeButton("取消", null)
                .setPositiveButton("打开", (dialog, which) -> {
                    try { startActivity(new Intent(Intent.ACTION_VIEW, uri)); }
                    catch (ActivityNotFoundException error) { toast("没有可用的浏览器。"); }
                }).show();
    }

    private void showError(String message) {
        progress.setVisibility(View.GONE);
        errorText.setText(message);
        errorPanel.setVisibility(View.VISIBLE);
    }

    private void toast(String text) { Toast.makeText(this, text, Toast.LENGTH_LONG).show(); }

    private void closePort() {
        if (downloadPort != null) { downloadPort.close(); downloadPort = null; }
        incoming = null;
    }

    @Override protected void onResume() {
        super.onResume();
        foreground = true;
        if (web != null) {
            web.onResume();
            web.evaluateJavascript("window.__cwResumeCapture && window.__cwResumeCapture()", ignored -> {
                if (approvedAudio && foreground) grantAudio();
            });
        }
    }

    @Override protected void onPause() {
        foreground = false;
        if (web != null) {
            web.evaluateJavascript("window.__cwStopCapture && window.__cwStopCapture()", null);
            web.onPause();
        }
        super.onPause();
    }

    @Override public void onBackPressed() {
        if (web.canGoBack()) { errorPanel.setVisibility(View.GONE); web.goBack(); }
        else new AlertDialog.Builder(this).setTitle("退出工程工作台？")
                .setMessage("未保存的填报文字可能丢失，请先保存。")
                .setNegativeButton("继续填写", null).setPositiveButton("退出", (dialog, which) -> finish()).show();
    }

    @Override protected void onDestroy() {
        cancelAudioRequest();
        closePort();
        pendingDownload = null;
        if (fileCallback != null) { fileCallback.onReceiveValue(null); fileCallback = null; }
        if (web != null) { web.removeAllViews(); web.destroy(); }
        writer.shutdown();
        super.onDestroy();
    }
}
