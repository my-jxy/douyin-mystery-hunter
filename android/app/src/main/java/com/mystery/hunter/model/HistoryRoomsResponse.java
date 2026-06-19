package com.mystery.hunter.model;

import com.google.gson.annotations.SerializedName;
import java.util.List;

/**
 * /api/history_rooms 返回格式: {"success": true, "rooms": [{"room_id": "...", "last_seen": N, "mystery_count": N, "nickname": "..."}]}
 */
public class HistoryRoomsResponse {
    @SerializedName("success")
    public boolean success;

    @SerializedName("error")
    public String error;

    @SerializedName("rooms")
    public List<RoomHistoryItem> rooms;

    public static class RoomHistoryItem {
        @SerializedName("room_id")
        public String roomId;

        @SerializedName("last_seen")
        public long lastSeen;

        @SerializedName("mystery_count")
        public int mysteryCount;

        @SerializedName("nickname")
        public String nickname;
    }
}
