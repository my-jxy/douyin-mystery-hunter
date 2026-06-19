package com.mystery.hunter.model;

import com.google.gson.annotations.SerializedName;

/**
 * 互动记录（聊天/送礼）
 * API 返回: {"type": "chat"/"gift", "content": "...", "gift_count": N, "timestamp": N}
 */
public class Interaction {
    @SerializedName("type")
    public String type;

    @SerializedName("content")
    public String content;

    @SerializedName("gift_count")
    public int giftCount;

    @SerializedName("timestamp")
    public long timestamp;
}
