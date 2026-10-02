package com.faweisi.kanban;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.net.http.SslError;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.Message;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.webkit.CookieManager;
import android.webkit.SslErrorHandler;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.PopupMenu;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends Activity {
    private static final int PICK_FILE = 100, SAVE_FILE = 101;
    private static final int BACKGROUND = Color.rgb(8, 11, 18);
    private final OriginPolicy policy = new OriginPolicy(BuildConfig.SERVER_URL, BuildConfig.DEBUG);
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final ExecutorService downloads = Executors.newSingleThreadExecutor();
    private WebView web;
    private ProgressBar progress;
    private LinearLayout errorPanel;
    private ValueCallback<Uri[]> fileCallback;
    private AttachmentSaver.Download pendingDownload;
    private String currentPage = BuildConfig.SERVER_URL + "/";
    private boolean pageFailed;
    private final Runnable timeout = () -> {
        showError();
        if (web != null) web.stopLoading();
    };

    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        buildLayout();
        configureWebView();
        if (Build.VERSION.SDK_INT >= 33) {
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(0, this::handleBack);
        }
        if (savedInstanceState != null) {
            pendingDownload = restoredDownload(savedInstanceState);
            if (web.restoreState(savedInstanceState) != null && policy.isInternal(web.getUrl())) {
                currentPage = web.getUrl();
                return;
            }
        }
        beginLoading();
        web.loadUrl(currentPage);
    }

    private void buildLayout() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(BACKGROUND);
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            if (Build.VERSION.SDK_INT >= 30) {
                android.graphics.Insets bars = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
                android.graphics.Insets keyboard = insets.getInsets(WindowInsets.Type.ime());
                view.setPadding(bars.left, bars.top, bars.right, Math.max(bars.bottom, keyboard.bottom));
            } else {
                view.setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(),
                        insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom());
            }
            return Build.VERSION.SDK_INT >= 30 ? WindowInsets.CONSUMED : insets.consumeSystemWindowInsets();
        });
        setContentView(root);
        root.requestApplyInsets();

        LinearLayout toolbar = new LinearLayout(this);
        toolbar.setGravity(Gravity.CENTER_VERTICAL);
        toolbar.setPadding(dp(16), 0, dp(6), 0);
        TextView title = text(getString(R.string.app_name), 18);
        toolbar.addView(title, new LinearLayout.LayoutParams(0, dp(48), 1));
        title.setGravity(Gravity.CENTER_VERTICAL);
        Button refresh = new Button(this);
        refresh.setText("↻");
        refresh.setTextSize(24);
        refresh.setBackgroundResource(android.R.drawable.list_selector_background);
        refresh.setContentDescription(getString(R.string.refresh));
        refresh.setOnClickListener(v -> reload());
        toolbar.addView(refresh, new LinearLayout.LayoutParams(dp(48), dp(48)));
        Button menu = new Button(this);
        menu.setText("⋮");
        menu.setTextSize(24);
        menu.setBackgroundResource(android.R.drawable.list_selector_background);
        menu.setContentDescription(getString(R.string.more));
        menu.setOnClickListener(v -> showMenu(v));
        toolbar.addView(menu, new LinearLayout.LayoutParams(dp(48), dp(48)));
        root.addView(toolbar);

        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setIndeterminate(false);
        progress.setContentDescription(getString(R.string.connecting));
        root.addView(progress, new LinearLayout.LayoutParams(-1, dp(2)));
        FrameLayout content = new FrameLayout(this);
        root.addView(content, new LinearLayout.LayoutParams(-1, 0, 1));
        web = new WebView(this);
        web.setBackgroundColor(BACKGROUND);
        content.addView(web, new FrameLayout.LayoutParams(-1, -1));

        errorPanel = new LinearLayout(this);
        errorPanel.setOrientation(LinearLayout.VERTICAL);
        errorPanel.setGravity(Gravity.CENTER);
        errorPanel.setPadding(dp(32), dp(24), dp(32), dp(24));
        errorPanel.setBackgroundColor(BACKGROUND);
        errorPanel.addView(text(getString(R.string.connection_failed), 24));
        TextView help = text(getString(R.string.connection_help), 15);
        help.setPadding(0, dp(16), 0, dp(24));
        errorPanel.addView(help);
        Button retry = new Button(this);
        retry.setText(R.string.retry);
        retry.setOnClickListener(v -> reload());
        errorPanel.addView(retry);
        content.addView(errorPanel, new FrameLayout.LayoutParams(-1, -1));
        errorPanel.setVisibility(View.GONE);
    }

    @SuppressLint("SetJavaScriptEnabled")
    private void configureWebView() {
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        // An online client must not present stale pages as a successful reconnect.
        settings.setCacheMode(WebSettings.LOAD_NO_CACHE);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setSafeBrowsingEnabled(true);
        settings.setSupportMultipleWindows(true);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setUserAgentString(settings.getUserAgentString() + " KanbanAndroid/" + BuildConfig.VERSION_NAME);
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false);
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG);
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                if (!request.isForMainFrame()) return !policy.isInternal(request.getUrl().toString());
                return navigate(request.getUrl().toString());
            }
            @Override public void onPageStarted(WebView view, String url, android.graphics.Bitmap favicon) {
                if (!policy.isInternal(url)) { view.stopLoading(); showError(); return; }
                currentPage = url;
                beginLoading();
            }
            @Override public void onPageFinished(WebView view, String url) {
                handler.removeCallbacks(timeout);
                progress.setVisibility(View.INVISIBLE);
                CookieManager.getInstance().flush();
                if (!pageFailed) errorPanel.setVisibility(View.GONE);
            }
            @Override public void onPageCommitVisible(WebView view, String url) {
                // Optional remote fonts must not turn an already visible app into a timeout error.
                if (!pageFailed && policy.isInternal(url)) {
                    handler.removeCallbacks(timeout);
                    progress.setVisibility(View.INVISIBLE);
                }
            }
            @Override public void doUpdateVisitedHistory(WebView view, String url, boolean reload) {
                if (policy.isInternal(url)) currentPage = url;
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) showError();
            }
            @Override public void onReceivedHttpError(WebView view, WebResourceRequest request, WebResourceResponse response) {
                if (request.isForMainFrame() && response.getStatusCode() >= 400) showError();
            }
            @Override public void onReceivedSslError(WebView view, SslErrorHandler ssl, SslError error) {
                ssl.cancel();
                if (error.getUrl().equals(view.getUrl())) showError();
            }
            @Override public boolean onRenderProcessGone(WebView view, android.webkit.RenderProcessGoneDetail detail) {
                // Recreate the activity rather than reuse a WebView whose renderer died.
                ((FrameLayout) view.getParent()).removeView(view);
                view.destroy();
                web = null;
                recreate();
                return true;
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override public void onProgressChanged(WebView view, int value) { progress.setProgress(value); }
            @Override public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (!policy.isInternal(view.getUrl())) return false;
                cancelFileChooser();
                fileCallback = callback;
                Intent picker = new Intent(Intent.ACTION_OPEN_DOCUMENT);
                picker.addCategory(Intent.CATEGORY_OPENABLE);
                picker.setType("*/*");
                picker.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, params.getMode() == FileChooserParams.MODE_OPEN_MULTIPLE);
                try { startActivityForResult(picker, PICK_FILE); }
                catch (ActivityNotFoundException e) { cancelFileChooser(); toast(R.string.no_handler); }
                return true;
            }
            @Override public boolean onCreateWindow(WebView view, boolean dialog, boolean userGesture, Message message) {
                if (!userGesture) return false;
                WebView popup = new WebView(MainActivity.this);
                popup.setWebViewClient(new WebViewClient() {
                    @Override public boolean shouldOverrideUrlLoading(WebView child, WebResourceRequest request) {
                        String url = request.getUrl().toString();
                        if (!navigate(url) && policy.isInternal(url)) web.loadUrl(url);
                        child.destroy();
                        return true;
                    }
                });
                ((WebView.WebViewTransport) message.obj).setWebView(popup);
                message.sendToTarget();
                return true;
            }
        });
        web.setDownloadListener((url, agent, disposition, type, size) -> {
            if (policy.isAttachment(url)) chooseDownload(url, URLUtil.guessFileName(url, disposition, type), type);
            else if (policy.isExternal(url) && !policy.isInternal(url)) openExternal(url);
            else toast(R.string.save_failed);
        });
    }

    private boolean navigate(String url) {
        if (policy.isAttachment(url)) {
            // The existing card detail exposes the original filename on its attachment link.
            web.evaluateJavascript("(() => { const link = [...document.querySelectorAll('a[href]')].find(a => a.href === " +
                    org.json.JSONObject.quote(url) + "); return link ? link.textContent.trim() : ''; })()", value -> {
                if (isFinishing() || isDestroyed()) return;
                String filename = "附件-" + Uri.parse(url).getPathSegments().get(2);
                try {
                    Object decoded = new org.json.JSONTokener(value).nextValue();
                    if (decoded instanceof String && !((String) decoded).isBlank()) filename = (String) decoded;
                } catch (org.json.JSONException ignored) { }
                String extension = filename.contains(".") ? filename.substring(filename.lastIndexOf('.') + 1).toLowerCase(java.util.Locale.ROOT) : "";
                String mime = android.webkit.MimeTypeMap.getSingleton().getMimeTypeFromExtension(extension);
                chooseDownload(url, filename, mime);
            });
            return true;
        }
        if (policy.isInternal(url)) return false;
        if (policy.isExternal(url)) openExternal(url);
        return true;
    }

    private void openExternal(String url) {
        try { startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url))); }
        catch (ActivityNotFoundException e) { toast(R.string.no_handler); }
    }

    private void chooseDownload(String url, String filename, String mime) {
        if (pendingDownload != null) return;
        pendingDownload = new AttachmentSaver.Download(url, CookieManager.getInstance().getCookie(url), web.getSettings().getUserAgentString());
        Intent save = new Intent(Intent.ACTION_CREATE_DOCUMENT);
        save.addCategory(Intent.CATEGORY_OPENABLE);
        save.setType(mime == null || mime.isBlank() ? "application/octet-stream" : mime);
        save.putExtra(Intent.EXTRA_TITLE, filename.replaceAll("[\\\\/\\p{Cntrl}]", "_"));
        try { startActivityForResult(save, SAVE_FILE); }
        catch (ActivityNotFoundException e) { pendingDownload = null; toast(R.string.no_handler); }
    }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request == PICK_FILE && fileCallback != null) {
            Uri[] files = result == RESULT_OK ? WebChromeClient.FileChooserParams.parseResult(result, data) : null;
            if (files != null && !UploadPolicy.isAllowed(this, files)) {
                files = null;
                toast(R.string.upload_rejected);
            }
            fileCallback.onReceiveValue(files);
            fileCallback = null;
        } else if (request == SAVE_FILE) {
            AttachmentSaver.Download download = pendingDownload;
            pendingDownload = null;
            if (result != RESULT_OK || data == null || data.getData() == null || download == null) return;
            Uri destination = data.getData();
            toast(R.string.saving);
            downloads.execute(() -> {
                int status = R.string.saved;
                try { AttachmentSaver.save(getContentResolver(), destination, download, policy); }
                catch (Exception e) {
                    status = R.string.save_failed;
                    try { android.provider.DocumentsContract.deleteDocument(getContentResolver(), destination); }
                    catch (Exception ignored) { /* Provider may not allow removing the incomplete document. */ }
                }
                int finalStatus = status;
                handler.post(() -> toast(finalStatus));
            });
        }
    }

    private void reload() {
        if (web == null) { recreate(); return; }
        beginLoading();
        // loadUrl on a hash route can be treated as same-document navigation, without fetching anything.
        if (policy.isInternal(web.getUrl())) web.reload();
        else web.loadUrl(policy.isInternal(currentPage) ? currentPage : BuildConfig.SERVER_URL + "/");
    }

    private void beginLoading() {
        pageFailed = false;
        errorPanel.setVisibility(View.GONE);
        progress.setVisibility(View.VISIBLE);
        handler.removeCallbacks(timeout);
        handler.postDelayed(timeout, 30000);
    }

    private void showError() {
        pageFailed = true;
        handler.removeCallbacks(timeout);
        progress.setVisibility(View.INVISIBLE);
        errorPanel.setVisibility(View.VISIBLE);
    }

    private void showMenu(View anchor) {
        PopupMenu menu = new PopupMenu(this, anchor);
        menu.getMenu().add(0, 1, 0, R.string.browser);
        menu.getMenu().add(0, 2, 1, R.string.about);
        menu.setOnMenuItemClickListener(item -> {
            if (item.getItemId() == 1) openExternal(currentPage);
            else new AlertDialog.Builder(this).setTitle(R.string.app_name)
                    .setMessage(getString(R.string.about_message, BuildConfig.VERSION_NAME, BuildConfig.SERVER_URL))
                    .setPositiveButton(android.R.string.ok, null).show();
            return true;
        });
        menu.show();
    }

    // API 33+ uses the platform dispatcher registered in onCreate; this fallback serves API 26–32.
    @SuppressLint("GestureBackNavigation")
    @Override public void onBackPressed() { handleBack(); }

    private void handleBack() {
        if (web == null || errorPanel.getVisibility() == View.VISIBLE) { confirmExit(); return; }
        web.evaluateJavascript("window.kanbanNavigation?.handleBack() === true",
                handled -> {
                    if (isFinishing() || isDestroyed()) return;
                    if (!"true".equals(handled)) {
                        if (web.canGoBack()) web.goBack();
                        else confirmExit();
                    }
                });
    }

    private void confirmExit() {
        new AlertDialog.Builder(this).setMessage(R.string.exit).setNegativeButton(R.string.cancel, null)
                .setPositiveButton(R.string.confirm_exit, (dialog, which) -> finish()).show();
    }

    @Override protected void onSaveInstanceState(Bundle state) {
        if (web != null) web.saveState(state);
        if (pendingDownload != null) state.putString("download_url", pendingDownload.url());
        super.onSaveInstanceState(state);
    }

    private AttachmentSaver.Download restoredDownload(Bundle state) {
        String url = state.getString("download_url");
        return policy.isAttachment(url) ? new AttachmentSaver.Download(url, CookieManager.getInstance().getCookie(url),
                web.getSettings().getUserAgentString()) : null;
    }

    @Override protected void onPause() {
        if (web != null) web.onPause();
        CookieManager.getInstance().flush();
        super.onPause();
    }
    @Override protected void onResume() { super.onResume(); if (web != null) web.onResume(); }
    @Override protected void onDestroy() {
        handler.removeCallbacks(timeout);
        cancelFileChooser();
        downloads.shutdown();
        if (web != null) { web.stopLoading(); web.destroy(); }
        super.onDestroy();
    }
    private void cancelFileChooser() {
        if (fileCallback != null) { fileCallback.onReceiveValue(null); fileCallback = null; }
    }
    private TextView text(String value, int size) {
        TextView text = new TextView(this);
        text.setText(value);
        text.setTextSize(size);
        text.setTextColor(Color.rgb(245, 247, 251));
        text.setGravity(Gravity.CENTER);
        return text;
    }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private void toast(int message) { Toast.makeText(getApplicationContext(), message, Toast.LENGTH_LONG).show(); }
}
