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
import com.google.gson.JsonObject;
import com.mystery.hunter.R;
import com.mystery.hunter.api.ApiClient;
import com.mystery.hunter.api.ApiConfig;
import com.mystery.hunter.model.SearchHistoryItem;
import com.mystery.hunter.model.SearchHistoryResponse;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;

/**
 * 搜索历史 Fragment
 * API: /api/search_history/list -> {"success": true, "data": [{input_text, nickname, room_id, created_at}]}
 */
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
                        SearchHistoryResponse resp = gson.fromJson(response, SearchHistoryResponse.class);
                        if (resp.success && resp.data != null) {
                            historyList.clear();
                            historyList.addAll(resp.data);
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

    private void deleteItem(int pos) {
        SearchHistoryItem item = historyList.get(pos);
        JsonObject body = new JsonObject();
        body.addProperty("input", item.inputText);
        ApiClient.post(ApiConfig.BASE_URL + ApiConfig.SEARCH_HISTORY_DELETE, body.toString(),
                new ApiClient.ApiCallback() {
                    @Override
                    public void onSuccess(String response) {
                        mainHandler.post(() -> {
                            try {
                                JsonObject res = gson.fromJson(response, JsonObject.class);
                                if (!res.has("success") || !res.get("success").getAsBoolean()) {
                                    String err = res.has("error") ? res.get("error").getAsString() : "删除失败";
                                    Toast.makeText(getContext(), err, Toast.LENGTH_SHORT).show();
                                    adapter.notifyItemChanged(pos);
                                    return;
                                }
                                String deletedInput = item.inputText;
                                historyList.remove(pos);
                                adapter.notifyItemRemoved(pos);
                                updateUI();
                                Toast.makeText(getContext(), "已删除", Toast.LENGTH_SHORT).show();
                            } catch (Exception e) {
                                adapter.notifyItemChanged(pos);
                                Toast.makeText(getContext(), "删除失败: " + e.getMessage(), Toast.LENGTH_SHORT).show();
                            }
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

    private void updateUI() {
        boolean empty = historyList.isEmpty();
        tvEmpty.setVisibility(empty ? View.VISIBLE : View.GONE);
        rvHistory.setVisibility(empty ? View.GONE : View.VISIBLE);
        adapter.notifyDataSetChanged();
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
            h.tvRoomName.setText(item.getDisplayName());
            h.tvRoomId.setText("ID: " + (item.roomId != null ? item.roomId : "-"));
            h.tvTime.setText(sdf.format(new Date(item.createdAt * 1000)));
            h.itemView.setOnClickListener(v -> {
                // 切换到监控 tab - 自动填入 room_id
                MonitoringFragment frag = findMonitoringFragment();
                if (frag != null) {
                    frag.setInputText(item.inputText);
                }
                // 切换到第一个 tab (0 = monitoring)
                if (getActivity() != null) {
                    androidx.viewpager2.widget.ViewPager2 vp = getActivity().findViewById(R.id.view_pager);
                    if (vp != null) vp.setCurrentItem(0, true);
                }
            });
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

    private MonitoringFragment findMonitoringFragment() {
        if (getActivity() != null) {
            return (MonitoringFragment) getActivity().getSupportFragmentManager()
                    .findFragmentByTag("f0");
        }
        return null;
    }
}
