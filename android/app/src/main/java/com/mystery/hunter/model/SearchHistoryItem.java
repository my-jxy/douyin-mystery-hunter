package com.mystery.hunter.model;

import com.google.gson.annotations.SerializedName;

/**
 * 搜索历史条目
 * API 返回: {"input_text": "...", "nickname": "...", "room_id": "...", "created_at": N}
 */
public class SearchHistoryItem {
    @SerializedName("input_text")
    public String inputText;

    @SerializedName("nickname")
    public String nickname;

    @SerializedName("room_id")
    public String roomId;

    @SerializedName("created_at")
    public long createdAt;

    /**
     * 获取显示名
     */
    public String getDisplayName() {
        return nickname != null && !nickname.isEmpty() ? nickname : inputText;
    }
}
