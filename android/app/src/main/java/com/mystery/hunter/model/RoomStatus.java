package com.mystery.hunter.model;

import com.google.gson.annotations.SerializedName;

public class RoomStatus {
    @SerializedName("room_id")
    public String roomId;
    @SerializedName("nickname")
    public String nickname;
    @SerializedName("status")
    public String status; // "listening" / "stopped"
    @SerializedName("user_input")
    public String userInput;

    // 当前的 SSE 连接状态（本地维护，不参与序列化）
    public transient boolean sseConnected;

    public boolean isListening() {
        return "listening".equals(status);
    }
}
