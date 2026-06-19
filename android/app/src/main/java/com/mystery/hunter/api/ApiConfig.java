package com.mystery.hunter.api;

public class ApiConfig {
    // 服务器基础地址，用户可修改
    public static String BASE_URL = "https://mybb-jy.top";

    // API 端点
    public static final String RESOLVE = "/api/resolve";
    public static final String START = "/api/start";
    public static final String STOP = "/api/stop";
    public static final String STOP_ALL = "/api/stop_all";
    public static final String STATUS = "/api/status";
    public static final String TOGGLE_RECORD_ALL = "/api/toggle_record_all";
    public static final String RECORD_ALL_STATUS = "/api/record_all_status";
    public static final String REAL_NAMES = "/api/real_names";
    public static final String HISTORY_ROOMS = "/api/history_rooms";
    public static final String HISTORY_ALL = "/api/history_all";
    public static final String HISTORY_ALL_ALL = "/api/history_all_all";
    public static final String SEARCH_HISTORY_LIST = "/api/search_history/list";
    public static final String SEARCH_HISTORY_SAVE = "/api/search_history/save";
    public static final String SEARCH_HISTORY_DELETE = "/api/search_history/delete";

    public static String streamUrl(String roomId) {
        return BASE_URL + "/stream/" + roomId;
    }

    public static String historyRoom(String roomId) {
        return BASE_URL + "/api/history/" + roomId;
    }

    public static String allRecords(String roomId) {
        return BASE_URL + "/api/all_records/" + roomId;
    }

    public static String interactions(String roomId, String secUid) {
        return BASE_URL + "/api/interactions/" + roomId + "/" + secUid;
    }
}
