package io.github.eggplanta.downloadity;

import android.app.Service;
import android.content.Intent;
import android.os.Binder;
import android.os.IBinder;

/**
 * Runs in the app process
 * The foreground service binds here, lending its priority
 */
public class DownloadAnchor extends Service {
    private final IBinder binder = new Binder();

    @Override
    public IBinder onBind(Intent intent) {
        return binder;
    }
}
