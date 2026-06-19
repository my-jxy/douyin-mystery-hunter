package com.mystery.hunter.ui;

import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.view.inputmethod.EditorInfo;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;
import android.widget.Toast;
import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.fragment.app.Fragment;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout;
import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.mystery.hunter.R;
import com.mystery.hunter.api.ApiClient;
import com.mystery.hunter.api.ApiConfig;
import com.mystery.hunter.api.SSEClient;
import com.mystery.hunter.model.StatusResponse;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 监听管理 Fragment
 * API:
 *   POST /api/resolve  -> {"success": true, "room_id": "...", "nickname": "...", "live_status": 0/1, "sec_uid": "..."}
 *   POST /api/start    -> {"success": true, "room_id": "...", "already": false/true}
 *   POST /api/stop     -> {"success": true, "room_id": "..."}
 *   POST /api/stop_all -> {"success": true}
 *   GET  /api/status   -> {"active": [{room_id, nickname, mystery_count, unique_count}], "count": N, "max": N}
 */
public class MonitoringFragment extends Fragment {

    private SwipeRefreshLayout swipeRefresh;
    private RecyclerView rvRooms;
    private TextView tvEmpty;
    private EditText etRoomInput;
    private Button btnStart, btnStopAll;
    private RoomAdapter adapter;
    private final List<StatusResponse.ActiveRoom> roomList = new ArrayList<>();
    private final Map<String, SSEClient> sseClients = new HashMap<>();
    private final Gson gson = ApiClient.getGson();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    @Nullable
    @Override
    public View onCreateView(@NonNull LayoutInflater inflater, @Nullable ViewGroup container,
                             @Nullable Bundle savedInstanceState) {
        View v = inflater.inflate(R.layout.fragment_monitoring, container, false);

        swipeRefresh = v.findViewById(R.id.swipe_refresh);
        rvRooms = v.findViewById(R.id.rv_rooms);
        tvEmpty = v.findViewById(R.id.tv_empty);
        etRoomInput = v.findViewById(R.id.et_room_input);
        btnStart = v.findViewById(R.id.btn_start);
        btnStopAll = v.findViewById(R.id.btn_stop_all);

        rvRooms.setLayoutManager(new LinearLayoutManager(getContext()));
        adapter = new RoomAdapter();
        rvRooms.setAdapter(adapter);

        swipeRefresh.setOnRefreshListener(this::loadStatus);
        btnStart.setOnClickListener(vw -> startMonitoring());
        btnStopAll.setOnClickListener(vw -> stopAll());

        etRoomInput.setOnEditorActionListener((tv, actionId, event) -> {
            if (actionId == EditorInfo.IME_ACTION_DONE) {
                startMonitoring();
                return true;
            }
            return false;
        });

        loadStatus();
        return v;
    }

    @Override
    public void onResume() {
        super.onResume();
        loadStatus();
    }

    /**
     * 加载当前活跃房间列表
     * GET /api/status -> {"active": [{room_id, nickname, mystery_count, unique_count}], "count": N, "max": N}
     */
    private void loadStatus() {
        ApiClient.get(ApiConfig.BASE_URL + ApiConfig.STATUS, new ApiClient.ApiCallback() {
            @Override
            public void onSuccess(String response) {
                mainHandler.post(() -> {
                    try {
                        StatusResponse status = gson.fromJson(response, StatusResponse.class);
                        roomList.clear();
                        if (status.active != null) {
                            roomList.addAll(status.active);
                        }
                        updateUI();

                        // 为所有活跃房间连接 SSE
                        for (StatusResponse.ActiveRoom rs : roomList) {
                            if (!sseClients.containsKey(rs.roomId)) {
                                connectSSE(rs.roomId);
                            }
                        }
                    } catch (Exception e) {
                        Toast.makeText(getContext(), "解析状态失败: " + e.getMessage(), Toast.LENGTH_SHORT).show();
                    }
                    swipeRefresh.setRefreshing(false);
                });
            }

            @Override
            public void onError(String error) {
                mainHandler.post(() -> {
                    Toast.makeText(getContext(), "获取状态失败: " + error, Toast.LENGTH_SHORT).show();
                    swipeRefresh.setRefreshing(false);
                });
            }
        });
    }

    /**
     * 开始监听：先 resolve 再 start
     * POST /api/resolve -> {"success": true, "room_id": "...", "nickname": "...", "live_status": 0/1, "sec_uid": "..."}
     * POST /api/start   -> {"success": true, "room_id": "...", "already": false/true}
     */
    private void startMonitoring() {
        String input = etRoomInput.getText().toString().trim();
        if (input.isEmpty()) {
            Toast.makeText(getContext(), "请输入抖音号或链接", Toast.LENGTH_SHORT).show();
            return;
        }

        btnStart.setEnabled(false);
        btnStart.setText("解析中...");

        // Step 1: Resolve
        JsonObject resolveBody = new JsonObject();
        resolveBody.addProperty("input", input);
        ApiClient.post(ApiConfig.BASE_URL + ApiConfig.RESOLVE, resolveBody.toString(), new ApiClient.ApiCallback() {
            @Override
            public void onSuccess(String response) {
                mainHandler.post(() -> {
                    try {
                        JsonObject res = gson.fromJson(response, JsonObject.class);
                        // 检查是否成功
                        if (!res.has("success") || !res.get("success").getAsBoolean()) {
                            String error = res.has("error") ? res.get("error").getAsString() : "解析失败";
                            Toast.makeText(getContext(), error, Toast.LENGTH_SHORT).show();
                            resetBtn();
                            return;
                        }
                        String roomId = res.get("room_id").getAsString();
                        String nickname = res.has("nickname") ? res.get("nickname").getAsString() : "";

                        // live_status 为 0 表示未在直播
                        if (res.has("live_status") && res.get("live_status").getAsInt() == 0) {
                            Toast.makeText(getContext(), "该主播未在直播", Toast.LENGTH_SHORT).show();
                            resetBtn();
                            return;
                        }

                        // Step 2: Start
                        JsonObject startBody = new JsonObject();
                        startBody.addProperty("room_id", roomId);
                        startBody.addProperty("nickname", nickname);
                        ApiClient.post(ApiConfig.BASE_URL + ApiConfig.START, startBody.toString(),
                                new ApiClient.ApiCallback() {
                                    @Override
                                    public void onSuccess(String startRes) {
                                        mainHandler.post(() -> {
                                            try {
                                                JsonObject sr = gson.fromJson(startRes, JsonObject.class);
                                                if (sr.has("success") && sr.get("success").getAsBoolean()) {
                                                    Toast.makeText(getContext(), "已开始监听 " + (nickname.isEmpty() ? roomId : nickname), Toast.LENGTH_SHORT).show();
                                                    etRoomInput.setText("");
                                                    connectSSE(roomId);
                                                    loadStatus();
                                                } else {
                                                    String err = sr.has("error") ? sr.get("error").getAsString() : "启动失败";
                                                    Toast.makeText(getContext(), err, Toast.LENGTH_SHORT).show();
                                                }
                                            } catch (Exception e) {
                                                Toast.makeText(getContext(), "启动失败: " + e.getMessage(), Toast.LENGTH_SHORT).show();
                                            }
                                            resetBtn();
                                        });
                                    }

                                    @Override
                                    public void onError(String error) {
                                        mainHandler.post(() -> {
                                            Toast.makeText(getContext(), "启动失败: " + error, Toast.LENGTH_SHORT).show();
                                            resetBtn();
                                        });
                                    }
                                });
                    } catch (Exception e) {
                        Toast.makeText(getContext(), "解析失败: " + e.getMessage(), Toast.LENGTH_SHORT).show();
                        resetBtn();
                    }
                });
            }

            @Override
            public void onError(String error) {
                mainHandler.post(() -> {
                    Toast.makeText(getContext(), "网络错误: " + error, Toast.LENGTH_SHORT).show();
                    resetBtn();
                });
            }
        });
    }

    private void resetBtn() {
        btnStart.setEnabled(true);
        btnStart.setText("开始监听");
    }

    /**
     * 连接 SSE 实时事件流
     */
    private void connectSSE(String roomId) {
        SSEClient sseClient = new SSEClient();
        sseClients.put(roomId, sseClient);
        sseClient.connect(roomId, new SSEClient.SseCallback() {
            @Override
            public void onConnected() {
                mainHandler.post(() -> adapter.notifyDataSetChanged());
            }

            @Override
            public void onEvent(String type, String data) {
                // 收到实时消息 - 只做轻量提示
                mainHandler.post(() -> {
                    try {
                        // SSE events are wrapped: {"type": "mystery_enter", "data": {...}}
                        JsonObject event = gson.fromJson(data, JsonObject.class);
                        String eventType = event.has("type") ? event.get("type").getAsString() : type;
                        JsonObject eventData = event.has("data") ? event.getAsJsonObject("data") : null;

                        String display = "";
                        if (eventData != null && eventData.has("display")) {
                            display = eventData.get("display").getAsString();
                        }

                        String msg;
                        switch (eventType) {
                            case "init":
                                msg = "✅ SSE 已连接";
                                break;
                            case "enter":
                                msg = "🚪 神秘人: " + display;
                                break;
                            case "chat":
                                msg = "💬 " + display;
                                break;
                            case "gift":
                                msg = "🎁 " + display + " 送了礼物";
                                break;
                            case "error":
                                msg = "⚠️ " + display;
                                break;
                            case "connected":
                                msg = null; // suppress raw "connected" type if still sent
                                break;
                            default:
                                msg = null;
                        }
                        if (msg != null) {
                            Toast.makeText(getContext(), msg, Toast.LENGTH_SHORT).show();
                        }
                        // 刷新房间列表更新 count
                        loadStatus();
                    } catch (Exception ignored) {}
                });
            }

            @Override
            public void onDisconnected() {
                mainHandler.post(() -> adapter.notifyDataSetChanged());
            }

            @Override
            public void onError(String message) {
                mainHandler.post(() -> adapter.notifyDataSetChanged());
            }
        });
    }

    /**
     * 停止指定房间
     * POST /api/stop -> {"success": true, "room_id": "..."}
     */
    private void stopRoom(String roomId) {
        JsonObject body = new JsonObject();
        body.addProperty("room_id", roomId);
        ApiClient.post(ApiConfig.BASE_URL + ApiConfig.STOP, body.toString(), new ApiClient.ApiCallback() {
            @Override
            public void onSuccess(String response) {
                mainHandler.post(() -> {
                    try {
                        JsonObject res = gson.fromJson(response, JsonObject.class);
                        if (!res.has("success") || !res.get("success").getAsBoolean()) {
                            String err = res.has("error") ? res.get("error").getAsString() : "停止失败";
                            Toast.makeText(getContext(), err, Toast.LENGTH_SHORT).show();
                            return;
                        }
                        disconnectSSE(roomId);
                        Toast.makeText(getContext(), "已停止", Toast.LENGTH_SHORT).show();
                        loadStatus();
                    } catch (Exception e) {
                        Toast.makeText(getContext(), "停止失败: " + e.getMessage(), Toast.LENGTH_SHORT).show();
                    }
                });
            }

            @Override
            public void onError(String error) {
                mainHandler.post(() -> Toast.makeText(getContext(), "停止失败: " + error, Toast.LENGTH_SHORT).show());
            }
        });
    }

    /**
     * 停止全部
     * POST /api/stop_all -> {"success": true}
     */
    private void stopAll() {
        ApiClient.post(ApiConfig.BASE_URL + ApiConfig.STOP_ALL, "{}", new ApiClient.ApiCallback() {
            @Override
            public void onSuccess(String response) {
                mainHandler.post(() -> {
                    try {
                        JsonObject res = gson.fromJson(response, JsonObject.class);
                        if (!res.has("success") || !res.get("success").getAsBoolean()) {
                            String err = res.has("error") ? res.get("error").getAsString() : "停止全部失败";
                            Toast.makeText(getContext(), err, Toast.LENGTH_SHORT).show();
                            return;
                        }
                        disconnectAllSSE();
                        Toast.makeText(getContext(), "已停止全部", Toast.LENGTH_SHORT).show();
                        loadStatus();
                    } catch (Exception e) {
                        Toast.makeText(getContext(), "停止全部失败: " + e.getMessage(), Toast.LENGTH_SHORT).show();
                    }
                });
            }

            @Override
            public void onError(String error) {
                mainHandler.post(() -> Toast.makeText(getContext(), "停止全部失败: " + error, Toast.LENGTH_SHORT).show());
            }
        });
    }

    private void disconnectSSE(String roomId) {
        SSEClient client = sseClients.remove(roomId);
        if (client != null) {
            client.disconnect();
        }
    }

    private void disconnectAllSSE() {
        for (SSEClient client : sseClients.values()) {
            client.disconnect();
        }
        sseClients.clear();
    }

    public void setInputText(String text) {
        if (etRoomInput != null) {
            etRoomInput.setText(text);
        }
    }

    private void updateUI() {
        boolean empty = roomList.isEmpty();
        tvEmpty.setVisibility(empty ? View.VISIBLE : View.GONE);
        rvRooms.setVisibility(empty ? View.GONE : View.VISIBLE);
        adapter.notifyDataSetChanged();
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        disconnectAllSSE();
    }

    // -- RecyclerView Adapter --
    private class RoomAdapter extends RecyclerView.Adapter<RoomAdapter.VH> {

        @NonNull
        @Override
        public VH onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
            View v = LayoutInflater.from(parent.getContext())
                    .inflate(R.layout.item_room, parent, false);
            return new VH(v);
        }

        @Override
        public void onBindViewHolder(@NonNull VH h, int pos) {
            StatusResponse.ActiveRoom rs = roomList.get(pos);
            String nickname = rs.nickname != null && !rs.nickname.isEmpty() ? rs.nickname : rs.roomId;
            h.tvNick.setText(nickname);
            h.tvRoomId.setText("ID: " + rs.roomId + " | 🎯" + rs.mysteryCount + " | 👤" + rs.uniqueCount);

            boolean connected = sseClients.containsKey(rs.roomId);
            h.tvStatus.setText("监听中");
            h.tvStatus.setTextColor(0xFF4CAF50);
            h.tvSse.setText(connected ? "SSE: 已连接" : "SSE: 未连接");
            h.tvSse.setTextColor(connected ? 0xFF4CAF50 : 0xFFFF6B6B);

            h.btnStop.setVisibility(View.VISIBLE);
            h.btnStop.setOnClickListener(v -> stopRoom(rs.roomId));
        }

        @Override
        public int getItemCount() { return roomList.size(); }

        class VH extends RecyclerView.ViewHolder {
            TextView tvNick, tvRoomId, tvStatus, tvSse;
            Button btnStop;
            VH(View v) {
                super(v);
                tvNick = v.findViewById(R.id.tv_nick);
                tvRoomId = v.findViewById(R.id.tv_room_id);
                tvStatus = v.findViewById(R.id.tv_status);
                tvSse = v.findViewById(R.id.tv_sse);
                btnStop = v.findViewById(R.id.btn_stop);
            }
        }
    }
}
