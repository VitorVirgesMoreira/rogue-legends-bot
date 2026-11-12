package com.roguebot.input;

import android.os.SystemClock;
import android.view.InputEvent;
import android.view.InputDevice;
import android.view.MotionEvent;
import java.lang.reflect.Method;

/** A short-lived shell gesture, using the same injection API as Android's input tool. */
public final class TreeGesture {
    private static Object manager;
    private static Method inject;

    private static void send(long down, int action, int count,
                             MotionEvent.PointerProperties[] props,
                             MotionEvent.PointerCoords[] coords) throws Exception {
        MotionEvent event = MotionEvent.obtain(down, SystemClock.uptimeMillis(), action, count,
            props, coords, 0, 0, 1f, 1f, 0, 0, InputDevice.SOURCE_TOUCHSCREEN, 0);
        try {
            if (!Boolean.TRUE.equals(inject.invoke(manager, event, 2))) {
                throw new IllegalStateException("Gesture injection rejected");
            }
        } finally {
            event.recycle();
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 9) throw new IllegalArgumentException("Expected 8 coordinates and duration");
        int[] values = new int[9];
        for (int i = 0; i < values.length; i++) values[i] = Integer.parseInt(args[i]);
        if (values[8] < 100 || values[8] > 1500) throw new IllegalArgumentException("Invalid duration");
        Class<?> type = Class.forName("android.hardware.input.InputManager");
        manager = type.getMethod("getInstance").invoke(null);
        inject = type.getMethod("injectInputEvent", InputEvent.class, int.class);
        MotionEvent.PointerProperties[] props = new MotionEvent.PointerProperties[2];
        MotionEvent.PointerCoords[] coords = new MotionEvent.PointerCoords[2];
        for (int i = 0; i < 2; i++) {
            props[i] = new MotionEvent.PointerProperties();
            props[i].id = i;
            props[i].toolType = MotionEvent.TOOL_TYPE_FINGER;
            coords[i] = new MotionEvent.PointerCoords();
            coords[i].pressure = 1f;
            coords[i].size = 1f;
            coords[i].x = values[i * 2];
            coords[i].y = values[i * 2 + 1];
        }
        long down = SystemClock.uptimeMillis();
        boolean finished = false;
        try {
            send(down, MotionEvent.ACTION_DOWN, 1, props, coords);
            send(down, MotionEvent.ACTION_POINTER_DOWN | (1 << MotionEvent.ACTION_POINTER_INDEX_SHIFT), 2, props, coords);
            for (int step = 1; step <= 20; step++) {
                SystemClock.sleep(values[8] / 20);
                float fraction = step / 20f;
                for (int i = 0; i < 2; i++) {
                    coords[i].x = values[i * 2] + (values[4 + i * 2] - values[i * 2]) * fraction;
                    coords[i].y = values[i * 2 + 1] + (values[5 + i * 2] - values[i * 2 + 1]) * fraction;
                }
                send(down, MotionEvent.ACTION_MOVE, 2, props, coords);
            }
            send(down, MotionEvent.ACTION_POINTER_UP | (1 << MotionEvent.ACTION_POINTER_INDEX_SHIFT), 2, props, coords);
            send(down, MotionEvent.ACTION_UP, 1, props, coords);
            finished = true;
            System.out.println("ROGUEBOT_PINCH_OK");
        } finally {
            if (!finished) send(down, MotionEvent.ACTION_CANCEL, 2, props, coords);
        }
    }
}
