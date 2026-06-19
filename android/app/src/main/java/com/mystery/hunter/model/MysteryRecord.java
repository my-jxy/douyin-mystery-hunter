package com.mystery.hunter.model;

import com.google.gson.annotations.SerializedName;
import com.google.gson.JsonObject;
import java.util.List;

/**
 * 神秘人记录模型，匹配 /api/history_all_all 和 /api/history_rooms 返回格式。
 * API 返回字段（从 web_listener.py 提取）：
 *   sec_uid, display, real_name, nickname, extra(JSON对象),
 *   last_room_id, seen_room_ids, first_seen, last_seen,
 *   enter_count, gift_count, chat_count, is_regular,
 *   displays[{display, last_seen, seen_count}], is_current, room_nickname
 */
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
    public JsonObject extra;

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

    @SerializedName("displays")
    public List<DisplayInfo> displays;

    @SerializedName("is_current")
    public boolean isCurrent;

    @SerializedName("room_nickname")
    public String roomNickname;

    /**
     * 判断是否为普通（常客）用户
     */
    public boolean isRegularUser() {
        return isRegular == 1;
    }

    /**
     * 获取最佳可显示名：优先 real_name（如果不是 dou/神秘人），其次 display
     */
    public String getDisplayName() {
        if (realName != null && !realName.isEmpty()
                && !realName.startsWith("dou")
                && !realName.startsWith("神秘人")) {
            return realName;
        }
        return display != null && !display.isEmpty() ? display : "未知";
    }

    /**
     * 显示名信息
     */
    public static class DisplayInfo {
        @SerializedName("display")
        public String display;

        @SerializedName("last_seen")
        public long lastSeen;

        @SerializedName("seen_count")
        public int seenCount;

        @SerializedName("is_current")
        public boolean isCurrent;
    }
}
