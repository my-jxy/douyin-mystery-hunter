package com.mystery.hunter.ui;

import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
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
import com.google.gson.reflect.TypeToken;
import com.mystery.hunter.R;
import com.mystery.hunter.api.ApiClient;
import com.mystery.hunter.api.ApiConfig;
import com.mystery.hunter.model.MysteryRecord;
import java.lang.reflect.Type;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;

public class MysteryFragment extends Fragment {

    private SwipeRefreshLayout swipeRefresh;
    private RecyclerView rvMystery;
    private TextView tvEmpty;
    private EditText etSearch;
    private Button btnClearSearch;
    private MysteryAdapter adapter;
    private final List<MysteryRecord> allRecords = new ArrayList<>();
    private final List<MysteryRecord> filteredRecords = new ArrayList<>();
    private final Gson gson = ApiClient.getGson();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final SimpleDateFormat sdf = new SimpleDateFormat("MM-dd HH:mm", Locale.getDefault());

    @Nullable
    @Override
    public View onCreateView(@NonNull LayoutInflater inflater, @Nullable ViewGroup container,
                             @Nullable Bundle savedInstanceState) {
        View v = inflater.inflate(R.layout.fragment_mystery, container, false);

        swipeRefresh = v.findViewById(R.id.swipe_refresh);
        rvMystery = v.findViewById(R.id.rv_mystery);
        tvEmpty = v.findViewById(R.id.tv_empty);
        etSearch = v.findViewById(R.id.et_search);
        btnClearSearch = v.findViewById(R.id.btn_clear_search);

        rvMystery.setLayoutManager(new LinearLayoutManager(getContext()));
        adapter = new MysteryAdapter();
        rvMystery.setAdapter(adapter);

        swipeRefresh.setOnRefreshListener(this::loadData);

        etSearch.addTextChangedListener(new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int st, int c, int a) {}
            @Override public void onTextChanged(CharSequence s, int st, int b, int c) { filter(s.toString()); }
            @Override public void afterTextChanged(Editable s) {}
        });

        btnClearSearch.setOnClickListener(vw -> {
            etSearch.setText("");
            filter("");
        });

        loadData();
        return v;
    }

    private void loadData() {
        ApiClient.get(ApiConfig.BASE_URL + ApiConfig.HISTORY_ALL, new ApiClient.ApiCallback() {
            @Override
            public void onSuccess(String response) {
                mainHandler.post(() -> {
                    try {
                        Type listType = new TypeToken<List<MysteryRecord>>() {}.getType();
                        List<MysteryRecord> records = gson.fromJson(response, listType);
                        allRecords.clear();
                        if (records != null) allRecords.addAll(records);
                        filter(etSearch.getText().toString());
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

    private void filter(String query) {
        filteredRecords.clear();
        if (query == null || query.isEmpty()) {
            filteredRecords.addAll(allRecords);
        } else {
            String q = query.toLowerCase();
            for (MysteryRecord r : allRecords) {
                if ((r.getDisplayName() != null && r.getDisplayName().toLowerCase().contains(q))
                        || (r.nickname != null && r.nickname.toLowerCase().contains(q))
                        || (r.realName != null && r.realName.toLowerCase().contains(q))
                        || (r.secUid != null && r.secUid.toLowerCase().contains(q))
                        || (r.display != null && r.display.toLowerCase().contains(q))) {
                    filteredRecords.add(r);
                }
            }
        }
        boolean empty = filteredRecords.isEmpty();
        tvEmpty.setVisibility(empty ? View.VISIBLE : View.GONE);
        rvMystery.setVisibility(empty ? View.GONE : View.VISIBLE);
        btnClearSearch.setVisibility(query != null && !query.isEmpty() ? View.VISIBLE : View.GONE);
        adapter.notifyDataSetChanged();
    }

    // -- RecyclerView Adapter --
    private class MysteryAdapter extends RecyclerView.Adapter<MysteryAdapter.VH> {

        @NonNull
        @Override
        public VH onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
            View v = LayoutInflater.from(parent.getContext())
                    .inflate(R.layout.item_mystery, parent, false);
            return new VH(v);
        }

        @Override
        public void onBindViewHolder(@NonNull VH h, int pos) {
            MysteryRecord r = filteredRecords.get(pos);
            h.tvDisplay.setText(r.getDisplayName());
            h.tvNick.setText("@" + (r.nickname != null ? r.nickname : "-"));
            h.tvSeen.setText("出现 " + (r.enterCount) + " 次");
            h.tvFirst.setText("首次: " + sdf.format(new Date(r.firstSeen * 1000)));
            h.tvLast.setText("最近: " + sdf.format(new Date(r.lastSeen * 1000)));

            // 点击展开详情
            h.itemView.setOnClickListener(v -> {
                boolean expanded = h.detailLayout.getVisibility() == View.VISIBLE;
                h.detailLayout.setVisibility(expanded ? View.GONE : View.VISIBLE);
            });

            h.tvDetailEnter.setText("进场: " + r.enterCount);
            h.tvDetailGift.setText("送礼: " + r.giftCount);
            h.tvDetailChat.setText("发言: " + r.chatCount);
            h.tvDetailRooms.setText("出现房间: " + (r.seenRoomIds != null ? r.seenRoomIds : "-"));
            h.detailLayout.setVisibility(View.GONE);
        }

        @Override
        public int getItemCount() { return filteredRecords.size(); }

        class VH extends RecyclerView.ViewHolder {
            TextView tvDisplay, tvNick, tvSeen, tvFirst, tvLast;
            TextView tvDetailEnter, tvDetailGift, tvDetailChat, tvDetailRooms;
            View detailLayout;
            VH(View v) {
                super(v);
                tvDisplay = v.findViewById(R.id.tv_display);
                tvNick = v.findViewById(R.id.tv_nick);
                tvSeen = v.findViewById(R.id.tv_seen);
                tvFirst = v.findViewById(R.id.tv_first);
                tvLast = v.findViewById(R.id.tv_last);
                tvDetailEnter = v.findViewById(R.id.tv_detail_enter);
                tvDetailGift = v.findViewById(R.id.tv_detail_gift);
                tvDetailChat = v.findViewById(R.id.tv_detail_chat);
                tvDetailRooms = v.findViewById(R.id.tv_detail_rooms);
                detailLayout = v.findViewById(R.id.detail_layout);
            }
        }
    }
}
