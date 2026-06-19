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
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.reflect.TypeToken;
import com.mystery.hunter.R;
import com.mystery.hunter.api.ApiClient;
import com.mystery.hunter.api.ApiConfig;
import com.mystery.hunter.api.SSEClient;
import com.mystery.hunter.model.RoomStatus;
import java.lang.reflect.Type;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class MonitoringFragment extends Fragment {

    private SwipeRefreshLayout swipeRefresh;
    private RecyclerView rvRooms;
    private TextView tvEmpty;
    private EditText etRoomInput;
    private Button btnStart, btnStopAll;
    private RoomAdapter adapter;
    private final List<RoomStatus> roomList = new ArrayList<>();
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

    private void loadStatus() {
        ApiClient.get(ApiConfig.BASE_URL + ApiConfig.STATUS, new ApiClient.ApiCallback() {
            @Override
            public void onSuccess(String response) {
                mainHandler.post(() -> {
                    try {
                        JsonObject obj = gson.fromJson(response, JsonObject.class);
                        JsonArray rooms = obj.getAsJsonArray("rooms");
                        Type listType = new TypeToken<List<RoomStatus>>() {}.getType();
                        List<RoomStatus> newList = gson.fromJson(rooms, listType);
                        roomList.clear();
                        roomList.addAll(newList);
                        updateUI();

                        // 为 listening 状态的房间自动连接 SSE
                        for (RoomStatus rs : roomList) {
                            if (rs.isListening() && !sseClients.containsKey(rs.roomId)) {
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

    private void startMonitoring() {
        String input = etRoomInput.getText().toString().trim();
        if (input.isEmpty()) {
            Toast.makeText(getContext(), "请输入直播间链接或名称", Toast.LENGTH_SHORT).show();
            return;
        }

        // 先 resolve
        JsonObject body = new JsonObject();
        body.addProperty("input", input);
        ApiClient.post(ApiConfig.BASE_URL + ApiConfig.RESOLVE, body.toString(), new ApiClient.ApiCallback() {
            @Override
            public void onSuccess(String response) {
                mainHandler.post(() -> {
                    try {
                        JsonObject res = gson.fromJson(response, JsonObject.class);
                        String roomId = res.get("room_id").getAsString();

                        // 再 start
                        JsonObject startBody = new JsonObject();
                        startBody.addProperty("room_id", roomId);
                        ApiClient.post(ApiConfig.BASE_URL + ApiConfig.START, startBody.toString(),
                                new ApiClient.ApiCallback() {
                                    @Override
                                    public void onSuccess(String startRes) {
                                        mainHandler.post(() -> {
                                            Toast.makeText(getContext(), "开始监听 " + roomId, Toast.LENGTH_SHORT).show();
                                            etRoomInput.setText("");
                                            connectSSE(roomId);
                                            loadStatus();
                                        });
                                    }

                                    @Override
                                    public void onError(String error) {
                                        mainHandler.post(() -> Toast.makeText(getContext(),
                                                "启动失败: " + error, Toast.LENGTH_SHORT).show());
                                    }
                                });
                    } catch (Exception e) {
                        Toast.makeText(getContext(), "解析失败: " + e.getMessage(), Toast.LENGTH_SHORT).show();
                    }
                });
            }

            @Override
            public void onError(String error) {
                mainHandler.post(() -> Toast.makeText(getContext(),
                        "解析失败: " + error, Toast.LENGTH_SHORT).show());
            }
        });
    }

    private void connectSSE(String roomId) {
        SSEClient sseClient = new SSEClient();
        sseClients.put(roomId, sseClient);
        sseClient.connect(roomId, new SSEClient.SseCallback() {
            @Override
            public void onConnected() {
                mainHandler.post(() -> {
                    for (RoomStatus rs : roomList) {
                        if (rs.roomId.equals(roomId)) {
                            rs.sseConnected = true;
                            adapter.notifyDataSetChanged();
                            break;
                        }
                    }
                });
            }

            @Override
            public void onEvent(String type, String data) {
                // 收到实时消息，在 UI 上提示
                mainHandler.post(() -> {
                    try {
                        JsonObject event = gson.fromJson(data, JsonObject.class);
                        String eventType = event.has("type") ? event.get("type").getAsString() : type;
                        String display = event.has("display") ? event.get("display").getAsString() : "";
                        String msg;
                        switch (eventType) {
                            case "enter":
                                msg = "🚪 " + display + " 进入直播间";
                                break;
                            case "gift":
                                msg = "🎁 " + display + " 送出礼物";
                                break;
                            case "chat":
                                msg = "💬 " + display + " 发言";
                                break;
                            default:
                                msg = "📡 " + display;
                        }
                        Toast.makeText(getContext(), msg, Toast.LENGTH_SHORT).show();
                    } catch (Exception ignored) {}
                });
            }

            @Override
            public void onDisconnected() {
                mainHandler.post(() -> {
                    for (RoomStatus rs : roomList) {
                        if (rs.roomId.equals(roomId)) {
                            rs.sseConnected = false;
                            adapter.notifyDataSetChanged();
                            break;
                        }
                    }
                });
            }

            @Override
            public void onError(String message) {
                mainHandler.post(() -> {
                    for (RoomStatus rs : roomList) {
                        if (rs.roomId.equals(roomId)) {
                            rs.sseConnected = false;
                            adapter.notifyDataSetChanged();
                            break;
                        }
                    }
                });
            }
        });
    }

    private void stopRoom(String roomId) {
        JsonObject body = new JsonObject();
        body.addProperty("room_id", roomId);
        ApiClient.post(ApiConfig.BASE_URL + ApiConfig.STOP, body.toString(), new ApiClient.ApiCallback() {
            @Override
            public void onSuccess(String response) {
                mainHandler.post(() -> {
                    disconnectSSE(roomId);
                    Toast.makeText(getContext(), "已停止 " + roomId, Toast.LENGTH_SHORT).show();
                    loadStatus();
                });
            }

            @Override
            public void onError(String error) {
                mainHandler.post(() -> Toast.makeText(getContext(), "停止失败: " + error, Toast.LENGTH_SHORT).show());
            }
        });
    }

    private void stopAll() {
        ApiClient.post(ApiConfig.BASE_URL + ApiConfig.STOP_ALL, "{}", new ApiClient.ApiCallback() {
            @Override
            public void onSuccess(String response) {
                mainHandler.post(() -> {
                    disconnectAllSSE();
                    Toast.makeText(getContext(), "已停止全部监听", Toast.LENGTH_SHORT).show();
                    loadStatus();
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
            RoomStatus rs = roomList.get(pos);
            h.tvNick.setText(rs.nickname != null ? rs.nickname : rs.roomId);
            h.tvRoomId.setText("ID: " + rs.roomId);
            h.tvStatus.setText(rs.isListening() ? "监听中" : "已停止");
            h.tvStatus.setTextColor(rs.isListening() ? 0xFF4CAF50 : 0xFF888888);
            h.tvSse.setText("SSE: " + (rs.sseConnected ? "已连接" : "未连接"));
            h.tvSse.setTextColor(rs.sseConnected ? 0xFF4CAF50 : 0xFFFF6B6B);
            h.btnStop.setVisibility(rs.isListening() ? View.VISIBLE : View.GONE);
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
