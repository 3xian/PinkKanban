package com.faweisi.kanban;

import org.junit.Test;
import static org.junit.Assert.*;

public class RefreshGestureTest {
    @Test public void verticalPullStaysVerticalWhenFingerTurnsSideways() {
        RefreshGesture gesture = new RefreshGesture(8);
        gesture.start(0, 0);
        gesture.move(0, 20);
        gesture.move(100, 20);
        assertFalse(gesture.isHorizontal());
    }

    @Test public void horizontalSwipeCannotTurnIntoRefresh() {
        RefreshGesture gesture = new RefreshGesture(8);
        gesture.start(0, 0);
        gesture.move(20, 0);
        gesture.move(20, 100);
        assertTrue(gesture.isHorizontal());
    }

    @Test public void smallMovementsDoNotLockDirectionAndNextTouchResets() {
        RefreshGesture gesture = new RefreshGesture(8);
        gesture.start(100, 100);
        gesture.move(107, 100);
        gesture.move(100, 120);
        assertFalse(gesture.isHorizontal());
        gesture.start(100, 100);
        gesture.move(120, 100);
        assertTrue(gesture.isHorizontal());
    }
}
