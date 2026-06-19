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
import androidx.recyclerview.widget.ItemTouchHelper;
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
import java.lang.reflect.Type;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;

public class SearchFragment extends Fragment {

    private SwipeRefreshLayout swipeRefresh;
    private RecyclerView rvHistory;
    private TextView tvEmpty;
    private HistoryAdapter adapter;
    private final List<SearchHistoryItem> historyList = new ArrayList<>();
    private final Gson gson = ApiClient.getGson();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final SimpleDateFormat sdf = new SimpleDateFormat("MM-dd HH:mm", Locale.getDefault());

    @Nullable
    @Override
    public View onCreateView(@NonNull LayoutInflater inflater, @Nullable ViewGroup container,
                             @Nullable Bundle savedInstanceState) {
        View v = inflater.inflate(R.layout.fragment_search, container, false);

        swipeRefresh = v.findViewById(R.id.swipe_refresh);
        rvHistory = v.findViewById(R.id.rv_search_history);
        tvEmpty = v.findViewById(R.id.tv_empty);

        rvHistory.setLayoutManager(new LinearLayoutManager(getContext()));
        adapter = new HistoryAdapter();
        rvHistory.setAdapter(adapter);

        swipeRefresh.setOnRefreshListener(this::loadData);

        // 右滑删除
        ItemTouchHelper helper = new ItemTouchHelper(new ItemTouchHelper.SimpleCallback(
                0, ItemTouchHelper.LEFT | ItemTouchHelper.RIGHT) {
            @Override
            public boolean onMove(@NonNull RecyclerView rv, @NonNull RecyclerView.ViewHolder vh,
                                  @NonNull RecyclerView.ViewHolder target) {
                return false;
            }

            @Override
            public void onSwiped(@NonNull RecyclerView.ViewHolder vh, int direction) {
                int pos = vh.getAdapterPosition();
                if (pos >= 0 && pos < historyList.size()) {
                    deleteItem(pos);
                }
            }
        });
        helper.attachToRecyclerView(rvHistory);

        loadData();
        return v;
    }

    private void loadData() {
        ApiClient.get(ApiConfig.BASE_URL + ApiConfig.SEARCH_HISTORY_LIST, new ApiClient.ApiCallback() {
            @Override
            public void onSuccess(String response) {
                mainHandler.post(() -> {
                    try {
                        Type listType = new TypeToken<List<SearchHistoryItem>>() {}.getType();
                        List<SearchHistoryItem> items = gson.fromJson(response, listType);
                        historyList.clear();
                        if (items != null) historyList.addAll(items);
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

    private void deleteItem(int pos) {
        SearchHistoryItem item = historyList.get(pos);
        JsonObject body = new JsonObject();
        body.addProperty("room_id", item.roomId);
        ApiClient.post(ApiConfig.BASE_URL + ApiConfig.SEARCH_HISTORY_DELETE, body.toString(),
                new ApiClient.ApiCallback() {
                    @Override
                    public void onSuccess(String response) {
                        mainHandler.post(() -> {
                            historyList.remove(pos);
                            adapter.notifyItemRemoved(pos);
                            updateUI();
                            Toast.makeText(getContext(), "已删除", Toast.LENGTH_SHORT).show();
                        });
                    }

                    @Override
                    public void onError(String error) {
                        mainHandler.post(() -> {
                            adapter.notifyItemChanged(pos);
                            Toast.makeText(getContext(), "删除失败: " + error, Toast.LENGTH_SHORT).show();
                        });
                    }
                });
    }

    private void onItemClick(SearchHistoryItem item) {
        // 切换到监控 tab 并自动填入
        MonitoringFragment frag = findMonitoringFragment();
        if (frag != null) {
            frag.setInputText(item.roomId);
        }
    }

    private MonitoringFragment findMonitoringFragment() {
        if (getParentFragment() != null) {
            return (MonitoringFragment) getParentFragment().getChildFragmentManager()
                    .findFragmentByTag("f0");
        }
        if (getActivity() != null) {
            return (MonitoringFragment) getActivity().getSupportFragmentManager()
                    .findFragmentByTag("f0");
        }
        return null;
    }

    private void updateUI() {
        boolean empty = historyList.isEmpty();
        tvEmpty.setVisibility(empty ? View.VISIBLE : View.GONE);
        rvHistory.setVisibility(empty ? View.GONE : View.VISIBLE);
    }

    // -- Model --
    public static class SearchHistoryItem {
        public String roomId;
        public String nickname;
        public long lastSearch;
    }

    // -- RecyclerView Adapter --
    private class HistoryAdapter extends RecyclerView.Adapter<HistoryAdapter.VH> {

        @NonNull
        @Override
        public VH onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
            View v = LayoutInflater.from(parent.getContext())
                    .inflate(R.layout.item_search_history, parent, false);
            return new VH(v);
        }

        @Override
        public void onBindViewHolder(@NonNull VH h, int pos) {
            SearchHistoryItem item = historyList.get(pos);
            h.tvRoomName.setText(item.nickname != null ? item.nickname : item.roomId);
            h.tvRoomId.setText("ID: " + item.roomId);
            h.tvTime.setText(sdf.format(new Date(item.lastSearch * 1000)));
            h.itemView.setOnClickListener(v -> onItemClick(item));
            h.itemView.setOnLongClickListener(v -> {
                deleteItem(pos);
                return true;
            });
        }

        @Override
        public int getItemCount() { return historyList.size(); }

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
}
