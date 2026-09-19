package org.changwei.mobile;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.net.http.SslError;
import android.os.Bundle;
import android.util.Base64;
import android.view.Gravity;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.GeolocationPermissions;
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
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
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
    private static final int COARSE_LOCATION = 103;
    private static final int MAX_DOWNLOAD = 30 * 1024 * 1024;
    private final ExecutorService writer = Executors.newSingleThreadExecutor();
    private WebView web;
    private ProgressBar progress;
    private ScrollView errorPanel;
    private ScrollView loadingPanel;
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
    private GeolocationPermissions.Callback locationCallback;
    private String locationOrigin;
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
        root.setBackgroundColor(getColor(R.color.canvas));
        LinearLayout toolbar = new LinearLayout(this);
        toolbar.setGravity(Gravity.CENTER_VERTICAL);
        toolbar.setPadding(dp(8), 0, dp(8), 0);
        toolbar.setBackgroundColor(getColor(R.color.navy));
        toolbar.addView(toolbarButton("返回", v -> onBackPressed()));
        address = new TextView(this);
        address.setText(R.string.app_name);
        address.setTextColor(getColor(R.color.on_navy));
        address.setTextSize(18);
        address.setTypeface(android.graphics.Typeface.DEFAULT_BOLD);
        address.setGravity(Gravity.CENTER);
        LinearLayout brand = new LinearLayout(this);
        brand.setOrientation(LinearLayout.VERTICAL);
        brand.setGravity(Gravity.CENTER);
        brand.addView(address);
        TextView subtitle = new TextView(this);
        subtitle.setText(R.string.app_subtitle);
        subtitle.setTextSize(12);
        subtitle.setTextColor(getColor(R.color.on_navy_muted));
        subtitle.setGravity(Gravity.CENTER);
        brand.addView(subtitle);
        toolbar.addView(brand, new LinearLayout.LayoutParams(0, dp(60), 1));
        toolbar.addView(toolbarButton("菜单", v -> showMenu()));
        root.addView(toolbar, new LinearLayout.LayoutParams(-1, dp(60)));
        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setMax(100);
        progress.setProgressTintList(ColorStateList.valueOf(getColor(R.color.accent)));
        root.addView(progress, new LinearLayout.LayoutParams(-1, dp(3)));
        FrameLayout body = new FrameLayout(this);
        web = new WebView(this);
        web.setBackgroundColor(Color.WHITE);
        body.addView(web, new FrameLayout.LayoutParams(-1, -1));
        LinearLayout loadingContent = statusPanel("正在连接工程服务");
        loadingContent.addView(statusText("请稍候，正在打开工作台。", 16, R.color.secondary_text));
        ProgressBar spinner = new ProgressBar(this);
        spinner.setIndeterminateTintList(ColorStateList.valueOf(getColor(R.color.accent)));
        LinearLayout.LayoutParams spinnerLayout = new LinearLayout.LayoutParams(dp(28), dp(28));
        spinnerLayout.topMargin = dp(24);
        loadingContent.addView(spinner, spinnerLayout);
        loadingPanel = scrollPanel(loadingContent);
        body.addView(loadingPanel, new FrameLayout.LayoutParams(-1, -1));
        LinearLayout errorContent = statusPanel("暂时无法打开工作台");
        errorText = statusText("", 16, R.color.secondary_text);
        errorText.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        errorContent.addView(errorText);
        Button reconnect = button("重新连接", v -> web.loadUrl(server + "/changwei"));
        reconnect.setTextColor(Color.WHITE);
        reconnect.setBackgroundTintList(ColorStateList.valueOf(getColor(R.color.accent)));
        LinearLayout.LayoutParams actionLayout = new LinearLayout.LayoutParams(-1, dp(52));
        actionLayout.topMargin = dp(28);
        errorContent.addView(reconnect, actionLayout);
        LinearLayout.LayoutParams settingsLayout = new LinearLayout.LayoutParams(-1, dp(52));
        settingsLayout.topMargin = dp(12);
        errorContent.addView(button("设置服务地址", v -> showServerDialog()), settingsLayout);
        errorPanel = scrollPanel(errorContent);
        errorPanel.setVisibility(View.GONE);
        body.addView(errorPanel, new FrameLayout.LayoutParams(-1, -1));
        root.addView(body, new LinearLayout.LayoutParams(-1, 0, 1));
        setContentView(root);
    }

    private Button button(String label, View.OnClickListener listener) {
        Button button = new Button(this);
        button.setText(label);
        button.setTextSize(16);
        button.setAllCaps(false);
        button.setTextColor(getColor(R.color.navy));
        button.setBackgroundTintList(ColorStateList.valueOf(getColor(R.color.surface)));
        button.setMinHeight(dp(48));
        button.setMinimumHeight(dp(48));
        button.setMinWidth(dp(64));
        button.setMinimumWidth(dp(64));
        button.setOnClickListener(listener);
        return button;
    }

    /** 工具栏保留足够触控面积，避免系统按钮边框挤压品牌。 */
    private Button toolbarButton(String label, View.OnClickListener listener) {
        Button result = button(label, listener);
        result.setTextColor(getColor(R.color.on_navy));
        result.setBackgroundTintList(ColorStateList.valueOf(getColor(R.color.navy)));
        return result;
    }

    /** 本地连接状态与网页使用相同的品牌和阅读层级。 */
    private LinearLayout statusPanel(String title) {
        LinearLayout panel = new LinearLayout(this);
        panel.setOrientation(LinearLayout.VERTICAL);
        panel.setGravity(Gravity.CENTER);
        panel.setPadding(dp(32), dp(32), dp(32), dp(32));
        panel.setBackgroundColor(getColor(R.color.canvas));
        ImageView logo = new ImageView(this);
        logo.setImageResource(R.mipmap.ic_launcher);
        logo.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        LinearLayout.LayoutParams logoLayout = new LinearLayout.LayoutParams(dp(72), dp(72));
        logoLayout.bottomMargin = dp(28);
        panel.addView(logo, logoLayout);
        TextView heading = statusText(title, 24, R.color.navy);
        heading.setTypeface(android.graphics.Typeface.DEFAULT_BOLD);
        LinearLayout.LayoutParams titleLayout = new LinearLayout.LayoutParams(-1, -2);
        titleLayout.bottomMargin = dp(16);
        panel.addView(heading, titleLayout);
        return panel;
    }

    /** 连接说明使用可读正文和自适应行高。 */
    private TextView statusText(String value, int size, int color) {
        TextView text = new TextView(this);
        text.setText(value);
        text.setTextSize(size);
        text.setTextColor(getColor(color));
        text.setGravity(Gravity.CENTER);
        text.setLineSpacing(dp(5), 1);
        return text;
    }

    /** 小屏、横屏和大字体下仍可滚动到恢复操作。 */
    private ScrollView scrollPanel(LinearLayout content) {
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(getColor(R.color.canvas));
        scroll.addView(content, new ScrollView.LayoutParams(-1, -2));
        return scroll;
    }

    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }

    private void configureWebView() {
        WebView.setWebContentsDebuggingEnabled(false);
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setGeolocationEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(true);
        settings.setAllowFileAccessFromFileURLs(false);
        settings.setAllowUniversalAccessFromFileURLs(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setSafeBrowsingEnabled(true);
        settings.setSupportMultipleWindows(false);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setUserAgentString(settings.getUserAgentString() + " JiangqingMobile/0.1.3");
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
                cancelLocationRequest();
                errorPanel.setVisibility(View.GONE);
                loadingPanel.setVisibility(View.VISIBLE);
                progress.setVisibility(View.VISIBLE);
                if (!trustedPage) {
                    view.stopLoading();
                    showError("已阻止非工程服务页面。请从菜单设置正确的 HTTPS 地址。");
                }
            }
            @Override public void onPageFinished(WebView view, String url) {
                if (!trustedPage || !ServerPolicy.sameOrigin(server, url)) return;
                progress.setVisibility(View.INVISIBLE);
                loadingPanel.setVisibility(View.GONE);
                CookieManager.getInstance().flush();
                installDownloadBridge();
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) showError("请检查手机网络，并确认服务地址可访问。服务离线时，请联系管理员。\n\n" + server);
            }
            @Override public void onReceivedHttpError(WebView view, WebResourceRequest request, WebResourceResponse response) {
                if (request.isForMainFrame()) showError("工程服务暂时不可用（HTTP " + response.getStatusCode() + "）。请稍后重试，或联系管理员检查服务。");
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
            @Override public void onGeolocationPermissionsShowPrompt(String origin, GeolocationPermissions.Callback callback) {
                requestLocation(origin, callback);
            }
            @Override public void onGeolocationPermissionsHidePrompt() { cancelLocationRequest(); }
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

    private void requestLocation(String origin, GeolocationPermissions.Callback callback) {
        if (!foreground || !trustedPage || !ServerPolicy.sameOrigin(server, origin)) {
            callback.invoke(origin, false, false);
            return;
        }
        cancelLocationRequest();
        locationCallback = callback;
        locationOrigin = origin;
        new AlertDialog.Builder(this).setTitle("允许本次天气定位？")
                .setMessage("只在你点击自动定位时读取大致位置，用于查询附近城市的当前天气；不会持续定位。\n\n" + server)
                .setNegativeButton("不允许", (dialog, which) -> cancelLocationRequest())
                .setOnCancelListener(dialog -> cancelLocationRequest())
                .setPositiveButton("允许", (dialog, which) -> {
                    if (locationCallback != callback || !foreground) return;
                    if (checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED) grantLocation();
                    else requestPermissions(new String[]{Manifest.permission.ACCESS_COARSE_LOCATION}, COARSE_LOCATION);
                }).show();
    }

    private void grantLocation() {
        GeolocationPermissions.Callback callback = locationCallback;
        String origin = locationOrigin;
        locationCallback = null;
        locationOrigin = null;
        if (callback == null || origin == null) return;
        boolean allowed = foreground && trustedPage && ServerPolicy.sameOrigin(server, origin);
        callback.invoke(origin, allowed, false);
    }

    private void cancelLocationRequest() {
        GeolocationPermissions.Callback callback = locationCallback;
        String origin = locationOrigin;
        locationCallback = null;
        locationOrigin = null;
        if (callback != null && origin != null) callback.invoke(origin, false, false);
    }

    @Override public void onRequestPermissionsResult(int code, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(code, permissions, results);
        if (code == COARSE_LOCATION) {
            if (results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED) grantLocation();
            else { cancelLocationRequest(); toast("未获得定位权限，可继续手动填写地名。"); }
            return;
        }
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
                    else new AlertDialog.Builder(this).setTitle("江擎 · 本地试用版 0.1.3")
                            .setMessage("水利工程智能协作\n\n工程数据保存在已连接的服务端。手机需要能够访问服务地址；如使用内网地址，需先连接相应网络。\n\n实时语音由服务端提供。建议保持 Android System WebView 为较新版本。仅支持可安装 Android APK 的系统。\n\n本包使用本地测试签名，登录态保存在本应用内。\n\n" + server)
                            .setPositiveButton("知道了", null).show();
                }).show();
    }

    private void showServerDialog() {
        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(dp(24), dp(12), dp(24), dp(8));
        TextView label = statusText("服务地址", 14, R.color.secondary_text);
        label.setGravity(Gravity.START);
        content.addView(label);
        EditText input = new EditText(this);
        input.setId(View.generateViewId());
        label.setLabelFor(input.getId());
        input.setSingleLine(true);
        input.setInputType(android.text.InputType.TYPE_CLASS_TEXT | android.text.InputType.TYPE_TEXT_VARIATION_URI);
        input.setText(server);
        input.setTextSize(16);
        input.setPadding(dp(12), dp(12), dp(12), dp(12));
        input.setMinHeight(dp(52));
        GradientDrawable field = new GradientDrawable();
        field.setColor(getColor(R.color.surface));
        field.setStroke(dp(1), getColor(R.color.outline));
        field.setCornerRadius(dp(6));
        input.setBackground(field);
        LinearLayout.LayoutParams inputLayout = new LinearLayout.LayoutParams(-1, -2);
        inputLayout.topMargin = dp(8);
        inputLayout.bottomMargin = dp(12);
        content.addView(input, inputLayout);
        TextView hint = statusText("使用 HTTPS 地址，可包含端口。更换服务后需重新登录，工程数据不受影响。", 14, R.color.secondary_text);
        hint.setGravity(Gravity.START);
        content.addView(hint);
        AlertDialog dialog = new AlertDialog.Builder(this).setTitle("连接工程服务")
                .setView(content).setNegativeButton("取消", null).setPositiveButton("保存并连接", null).create();
        dialog.setOnShowListener(ignored -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
            final String next;
            try { next = ServerPolicy.normalize(input.getText().toString()); }
            catch (IllegalArgumentException error) { input.setError(error.getMessage()); return; }
            if (next.equals(server)) { dialog.dismiss(); web.loadUrl(server + "/changwei"); return; }
            trustedPage = false;
            web.stopLoading();
            closePort();
            cancelAudioRequest();
            cancelLocationRequest();
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
        progress.setVisibility(View.INVISIBLE);
        loadingPanel.setVisibility(View.GONE);
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
        cancelLocationRequest();
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
        cancelLocationRequest();
        closePort();
        pendingDownload = null;
        if (fileCallback != null) { fileCallback.onReceiveValue(null); fileCallback = null; }
        if (web != null) { web.removeAllViews(); web.destroy(); }
        writer.shutdown();
        super.onDestroy();
    }
}
