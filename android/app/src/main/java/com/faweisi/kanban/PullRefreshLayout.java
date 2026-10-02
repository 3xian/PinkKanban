package com.faweisi.kanban;

import android.annotation.SuppressLint;
import android.content.Context;
import android.view.MotionEvent;
import android.view.ViewConfiguration;
import android.webkit.WebView;
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout;

/** Adapts page and nested HTML scrolling to the platform refresh gesture. */
@SuppressLint("ViewConstructor") // Created in code with its WebView, never inflated from XML.
final class PullRefreshLayout extends SwipeRefreshLayout {
    private final WebView web;
    private final RefreshGesture direction;
    private int gesture;
    private boolean pageBlocksRefresh, refreshOwnsGesture;

    PullRefreshLayout(Context context, WebView web) {
        super(context);
        this.web = web;
        direction = new RefreshGesture(ViewConfiguration.get(context).getScaledTouchSlop());
        addView(web, new LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT));
        // Once intercepted, keep delivering events so SwipeRefreshLayout can finish its spinner.
        setOnChildScrollUpCallback((parent, child) ->
                !refreshOwnsGesture &&
                (pageBlocksRefresh || direction.isHorizontal() || web.canScrollVertically(-1)));
    }

    @Override public boolean onInterceptTouchEvent(MotionEvent event) {
        boolean intercept = super.onInterceptTouchEvent(event);
        if (intercept) refreshOwnsGesture = true;
        return intercept;
    }

    @Override public boolean dispatchTouchEvent(MotionEvent event) {
        if (event.getActionMasked() == MotionEvent.ACTION_DOWN) {
            direction.start(event.getX(), event.getY());
            refreshOwnsGesture = false;
            pageBlocksRefresh = false;
            int currentGesture = ++gesture;
            // Let SwipeRefreshLayout record the pointer before the asynchronous page check.
            boolean handled = super.dispatchTouchEvent(event);
            pageBlocksRefresh = true;
            float x = event.getX() / Math.max(1, web.getWidth());
            float y = event.getY() / Math.max(1, web.getHeight());
            web.evaluateJavascript("window.kanbanGestures?.canPullRefreshAt(" + x + ", " + y + ") === true",
                    allowed -> {
                        if (gesture == currentGesture) pageBlocksRefresh = !"true".equals(allowed);
                    });
            return handled;
        }
        if (event.getActionMasked() == MotionEvent.ACTION_MOVE) {
            direction.move(event.getX(), event.getY());
        }
        if (event.getActionMasked() == MotionEvent.ACTION_UP || event.getActionMasked() == MotionEvent.ACTION_CANCEL) {
            ++gesture;
        }
        return super.dispatchTouchEvent(event);
    }
}
