package com.mystery.hunter.model;

import com.google.gson.annotations.SerializedName;
import java.util.List;

/**
 * /api/search_history/list 返回格式: {"success": true, "data": [...]}
 */
public class SearchHistoryResponse {
    @SerializedName("success")
    public boolean success;

    @SerializedName("error")
    public String error;

    @SerializedName("data")
    public List<SearchHistoryItem> data;
}
