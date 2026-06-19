package com.mystery.hunter.model;

import com.google.gson.annotations.SerializedName;
import java.util.List;

/**
 * /api/history_all_all 和 /api/all_records/<room_id> 响应包装
 * 返回格式: {"success": true, "records": [...], "count": N}
 */
public class HistoryListResponse {
    @SerializedName("success")
    public boolean success;

    @SerializedName("error")
    public String error;

    @SerializedName("records")
    public List<MysteryRecord> records;

    @SerializedName("count")
    public int count;
}
