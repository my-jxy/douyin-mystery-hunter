package com.mystery.hunter.api;

import android.os.Handler;
import android.os.Looper;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.sse.EventSource;
import okhttp3.sse.EventSourceListener;
import okhttp3.sse.EventSources;

public class SSEClient {
    private EventSource eventSource;
    private final OkHttpClient client;
    private String currentRoomId;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    public SSEClient() {
        client = ApiClient.getClient();
    }

    public void connect(String roomId, final SseCallback callback) {
        currentRoomId = roomId;
        Request req = new Request.Builder()
                .url(ApiConfig.streamUrl(roomId))
                .header("Accept", "text/event-stream")
                .build();
        eventSource = EventSources.createFactory(client).newEventSource(req, new EventSourceListener() {
            @Override
            public void onOpen(EventSource es, Response res) {
                mainHandler.post(callback::onConnected);
            }

            @Override
            public void onEvent(EventSource es, String id, String type, String data) {
                mainHandler.post(() -> callback.onEvent(type != null ? type : "message", data));
            }

            @Override
            public void onClosed(EventSource es) {
                mainHandler.post(callback::onDisconnected);
            }

            @Override
            public void onFailure(EventSource es, Throwable t, Response res) {
                String msg = t != null && t.getMessage() != null ? t.getMessage() : "连接失败";
                mainHandler.post(() -> callback.onError(msg));
                // 自动重连 (3秒后)
                if (currentRoomId != null) {
                    mainHandler.postDelayed(() -> connect(currentRoomId, callback), 3000);
                }
            }
        });
    }

    public void disconnect() {
        currentRoomId = null;
        if (eventSource != null) {
            eventSource.cancel();
            eventSource = null;
        }
    }

    public boolean isConnected() {
        return eventSource != null && currentRoomId != null;
    }

    public interface SseCallback {
        void onConnected();
        void onEvent(String type, String data);
        void onDisconnected();
        void onError(String message);
    }
}
