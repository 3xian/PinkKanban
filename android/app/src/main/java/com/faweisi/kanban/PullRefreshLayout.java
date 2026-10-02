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
    private final int touchSlop;
    private float startX, startY;
    private int gesture;
    private boolean pageBlocksRefresh, horizontal;

    PullRefreshLayout(Context context, WebView web) {
        super(context);
        this.web = web;
        touchSlop = ViewConfiguration.get(context).getScaledTouchSlop();
        addView(web, new LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT));
        setOnChildScrollUpCallback((parent, child) ->
                pageBlocksRefresh || horizontal || web.canScrollVertically(-1));
    }

    @Override public boolean dispatchTouchEvent(MotionEvent event) {
        if (event.getActionMasked() == MotionEvent.ACTION_DOWN) {
            startX = event.getX();
            startY = event.getY();
            horizontal = false;
            pageBlocksRefresh = false;
            int currentGesture = ++gesture;
            // Let SwipeRefreshLayout record the pointer before the asynchronous page check.
            boolean handled = super.dispatchTouchEvent(event);
            pageBlocksRefresh = true;
            float x = startX / Math.max(1, web.getWidth());
            float y = startY / Math.max(1, web.getHeight());
            web.evaluateJavascript("(() => { let el = document.elementFromPoint(" + x +
                    " * innerWidth, " + y + " * innerHeight); if (!el) return true; " +
                    "for (; el; el = el.parentElement) { " +
                    "if (el.isContentEditable || el.matches('button, a, input, textarea, select, label, " +
                    "[draggable=true], [data-drag], [data-drop-column]')) return true; " +
                    "if (el !== document.scrollingElement && el.scrollHeight > el.clientHeight && " +
                    "/auto|scroll/.test(getComputedStyle(el).overflowY)) return true; } return false; })()",
                    blocked -> {
                        if (gesture == currentGesture) pageBlocksRefresh = !"false".equals(blocked);
                    });
            return handled;
        }
        if (event.getActionMasked() == MotionEvent.ACTION_MOVE) {
            float dx = Math.abs(event.getX() - startX), dy = Math.abs(event.getY() - startY);
            if (dx > touchSlop && dx > dy) horizontal = true;
        }
        if (event.getActionMasked() == MotionEvent.ACTION_UP || event.getActionMasked() == MotionEvent.ACTION_CANCEL) {
            ++gesture;
        }
        return super.dispatchTouchEvent(event);
    }
}
