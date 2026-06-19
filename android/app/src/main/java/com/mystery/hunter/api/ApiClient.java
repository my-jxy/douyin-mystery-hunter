package com.mystery.hunter.api;

import com.google.gson.Gson;
import java.io.IOException;
import okhttp3.Call;
import okhttp3.Callback;
import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;

public class ApiClient {
    private static final MediaType JSON = MediaType.parse("application/json; charset=utf-8");
    private static final OkHttpClient client = new OkHttpClient.Builder()
            .connectTimeout(10, java.util.concurrent.TimeUnit.SECONDS)
            .readTimeout(30, java.util.concurrent.TimeUnit.SECONDS)
            .build();
    private static final Gson gson = new Gson();

    public static OkHttpClient getClient() { return client; }

    public static Gson getGson() { return gson; }

    public static void get(String url, final ApiCallback callback) {
        Request req = new Request.Builder().url(url).build();
        client.newCall(req).enqueue(new Callback() {
            @Override
            public void onFailure(Call call, IOException e) {
                callback.onError(e.getMessage() != null ? e.getMessage() : "网络错误");
            }

            @Override
            public void onResponse(Call call, Response res) throws IOException {
                if (res.isSuccessful()) {
                    String body = res.body() != null ? res.body().string() : "";
                    callback.onSuccess(body);
                } else {
                    callback.onError("HTTP " + res.code() + ": " + res.message());
                }
            }
        });
    }

    public static void post(String url, String jsonBody, final ApiCallback callback) {
        RequestBody body = RequestBody.create(jsonBody, JSON);
        Request req = new Request.Builder().url(url).post(body).build();
        client.newCall(req).enqueue(new Callback() {
            @Override
            public void onFailure(Call call, IOException e) {
                callback.onError(e.getMessage() != null ? e.getMessage() : "网络错误");
            }

            @Override
            public void onResponse(Call call, Response res) throws IOException {
                if (res.isSuccessful()) {
                    String bodyStr = res.body() != null ? res.body().string() : "";
                    callback.onSuccess(bodyStr);
                } else {
                    callback.onError("HTTP " + res.code() + ": " + res.message());
                }
            }
        });
    }

    public interface ApiCallback {
        void onSuccess(String response);
        void onError(String error);
    }
}
