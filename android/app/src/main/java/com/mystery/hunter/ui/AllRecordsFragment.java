package com.mystery.hunter.ui;

import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;
import android.widget.Toast;
import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.fragment.app.Fragment;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout;
import com.google.gson.Gson;
import com.mystery.hunter.R;
import com.mystery.hunter.api.ApiClient;
import com.mystery.hunter.api.ApiConfig;
import com.mystery.hunter.model.HistoryRoomsResponse;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;

/**
 * 全部记录 Fragment — 显示有记录的直播间列表
 * API: GET /api/history_rooms -> {"success": true, "rooms": [{"room_id": "...", "last_seen": N, "mystery_count": N, "nickname": "..."}]}
 * 点击条目跳转到 Monitoring tab 并预填 room_id
 */
public class AllRecordsFragment extends Fragment {

    private SwipeRefreshLayout swipeRefresh;
    private RecyclerView rvRecords;
    private TextView tvEmpty;
    private RecordsAdapter adapter;
    private final List<HistoryRoomsResponse.RoomHistoryItem> roomList = new ArrayList<>();
    private final Gson gson = ApiClient.getGson();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final SimpleDateFormat sdf = new SimpleDateFormat("MM-dd HH:mm", Locale.getDefault());

    @Nullable
    @Override
    public View onCreateView(@NonNull LayoutInflater inflater, @Nullable ViewGroup container,
                             @Nullable Bundle savedInstanceState) {
        View v = inflater.inflate(R.layout.fragment_all_records, container, false);

        swipeRefresh = v.findViewById(R.id.swipe_refresh);
        rvRecords = v.findViewById(R.id.rv_records);
        tvEmpty = v.findViewById(R.id.tv_empty);

        rvRecords.setLayoutManager(new LinearLayoutManager(getContext()));
        adapter = new RecordsAdapter();
        rvRecords.setAdapter(adapter);

        swipeRefresh.setOnRefreshListener(this::loadData);

        loadData();
        return v;
    }

    @Override
    public void onResume() {
        super.onResume();
        loadData();
    }

    /**
     * 加载有记录的直播间列表
     * GET /api/history_rooms -> {"success": true, "rooms": [{room_id, last_seen, mystery_count, nickname}]}
     */
    private void loadData() {
        ApiClient.get(ApiConfig.BASE_URL + ApiConfig.HISTORY_ROOMS, new ApiClient.ApiCallback() {
            @Override
            public void onSuccess(String response) {
                mainHandler.post(() -> {
                    try {
                        HistoryRoomsResponse resp = gson.fromJson(response, HistoryRoomsResponse.class);
                        roomList.clear();
                        if (resp.success && resp.rooms != null) {
                            roomList.addAll(resp.rooms);
                        } else if (!resp.success && resp.error != null) {
                            Toast.makeText(getContext(), resp.error, Toast.LENGTH_SHORT).show();
                        }
                        updateUI();
                    } catch (Exception e) {
                        Toast.makeText(getContext(), "解析失败: " + e.getMessage(), Toast.LENGTH_SHORT).show();
                    }
                    swipeRefresh.setRefreshing(false);
                });
            }

            @Override
            public void onError(String error) {
                mainHandler.post(() -> {
                    Toast.makeText(getContext(), "加载失败: " + error, Toast.LENGTH_SHORT).show();
                    swipeRefresh.setRefreshing(false);
                });
            }
        });
    }

    private void updateUI() {
        boolean empty = roomList.isEmpty();
        tvEmpty.setVisibility(empty ? View.VISIBLE : View.GONE);
        rvRecords.setVisibility(empty ? View.GONE : View.VISIBLE);
        adapter.notifyDataSetChanged();
    }

    // -- RecyclerView Adapter --
    private class RecordsAdapter extends RecyclerView.Adapter<RecordsAdapter.VH> {

        @NonNull
        @Override
        public VH onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
            View v = LayoutInflater.from(parent.getContext())
                    .inflate(R.layout.item_search_history, parent, false);
            return new VH(v);
        }

        @Override
        public void onBindViewHolder(@NonNull VH h, int pos) {
            HistoryRoomsResponse.RoomHistoryItem room = roomList.get(pos);
            String name = room.nickname != null && !room.nickname.isEmpty() ? room.nickname : room.roomId;
            h.tvRoomName.setText(name);
            h.tvRoomId.setText("ID: " + room.roomId + " | 🎯" + room.mysteryCount);
            h.tvTime.setText(room.lastSeen > 0 ? sdf.format(new Date(room.lastSeen * 1000)) : "-");

            // 点击跳转到监控 tab 并预填 room_id
            h.itemView.setOnClickListener(v -> {
                MonitoringFragment frag = findMonitoringFragment();
                if (frag != null) {
                    frag.setInputText(room.roomId);
                }
                if (getActivity() != null) {
                    androidx.viewpager2.widget.ViewPager2 vp = getActivity().findViewById(R.id.view_pager);
                    if (vp != null) vp.setCurrentItem(0, true);
                }
            });
        }

        @Override
        public int getItemCount() { return roomList.size(); }

        class VH extends RecyclerView.ViewHolder {
            TextView tvRoomName, tvRoomId, tvTime;
            VH(View v) {
                super(v);
                tvRoomName = v.findViewById(R.id.tv_room_name);
                tvRoomId = v.findViewById(R.id.tv_room_id);
                tvTime = v.findViewById(R.id.tv_time);
            }
        }
    }

    private MonitoringFragment findMonitoringFragment() {
        if (getActivity() != null) {
            return (MonitoringFragment) getActivity().getSupportFragmentManager()
                    .findFragmentByTag("f0");
        }
        return null;
    }
}
