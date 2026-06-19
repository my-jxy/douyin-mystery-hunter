package com.mystery.hunter.model;

import com.google.gson.annotations.SerializedName;

/**
 * 活跃房间状态 — 对应 /api/status 返回的 active 数组元素
 * 注意：所有 active 里的房间都是监听中的
 */
public class RoomStatus {
    @SerializedName("room_id")
    public String roomId;

    @SerializedName("nickname")
    public String nickname;

    @SerializedName("mystery_count")
    public int mysteryCount;

    @SerializedName("unique_count")
    public int uniqueCount;

    /** 本地状态，不是 API 返回的 */
    public transient boolean sseConnected;

    /** 所有 active 里的都是监听中的 */
    public boolean isListening() {
        return true;
    }
}
