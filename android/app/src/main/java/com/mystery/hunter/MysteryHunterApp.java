package com.mystery.hunter;

import android.app.Application;
import android.content.Intent;

public class MysteryHunterApp extends Application {

    private static MysteryHunterApp instance;

    @Override
    public void onCreate() {
        super.onCreate();
        instance = this;
    }

    public static MysteryHunterApp getInstance() {
        return instance;
    }

    public void startFloatingService() {
        Intent intent = new Intent(this, FloatingWindowService.class);
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
            startForegroundService(intent);
        } else {
            startService(intent);
        }
    }

    public void stopFloatingService() {
        Intent intent = new Intent(this, FloatingWindowService.class);
        stopService(intent);
    }
}
