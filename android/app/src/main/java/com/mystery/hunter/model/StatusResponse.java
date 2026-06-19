package com.mystery.hunter.model;

import com.google.gson.annotations.SerializedName;
import java.util.List;

/**
 * /api/status 返回格式: {"active": [...], "count": N, "max": N}
 */
public class StatusResponse {
    @SerializedName("active")
    public List<ActiveRoom> active;

    @SerializedName("count")
    public int count;

    @SerializedName("max")
    public int max;

    public static class ActiveRoom {
        @SerializedName("room_id")
        public String roomId;

        @SerializedName("nickname")
        public String nickname;

        @SerializedName("mystery_count")
        public int mysteryCount;

        @SerializedName("unique_count")
        public int uniqueCount;
    }
}
