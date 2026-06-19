package com.mystery.hunter.model;

import com.google.gson.annotations.SerializedName;

public class MysteryRecord {
    @SerializedName("sec_uid")
    public String secUid;
    @SerializedName("display")
    public String display;
    @SerializedName("real_name")
    public String realName;
    @SerializedName("nickname")
    public String nickname;
    @SerializedName("extra")
    public String extra;  // JSON string
    @SerializedName("last_room_id")
    public String lastRoomId;
    @SerializedName("seen_room_ids")
    public String seenRoomIds;
    @SerializedName("first_seen")
    public long firstSeen;
    @SerializedName("last_seen")
    public long lastSeen;
    @SerializedName("enter_count")
    public int enterCount;
    @SerializedName("gift_count")
    public int giftCount;
    @SerializedName("chat_count")
    public int chatCount;
    @SerializedName("is_regular")
    public int isRegular;

    public boolean isRegularUser() {
        return isRegular == 1;
    }

    public String getDisplayName() {
        if (realName != null && !realName.isEmpty()
                && !realName.startsWith("dou")
                && !realName.startsWith("神秘人")) {
            return realName;
        }
        return display != null && !display.isEmpty() ? display : "未知";
    }
}
