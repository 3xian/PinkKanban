package com.faweisi.kanban;

/** Locks the first deliberate direction until the next touch starts. */
final class RefreshGesture {
    private final int touchSlop;
    private float startX, startY;
    private boolean decided, horizontal;

    RefreshGesture(int touchSlop) {
        this.touchSlop = touchSlop;
    }

    void start(float x, float y) {
        startX = x;
        startY = y;
        decided = horizontal = false;
    }

    void move(float x, float y) {
        if (decided) return;
        float dx = Math.abs(x - startX), dy = Math.abs(y - startY);
        if (Math.max(dx, dy) > touchSlop) {
            horizontal = dx > dy;
            decided = true;
        }
    }

    boolean isHorizontal() {
        return horizontal;
    }
}
