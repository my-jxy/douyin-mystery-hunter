package com.mystery.hunter.api;

public class ApiConfig {
    // 服务器基础地址
    public static String BASE_URL = "https://mybb-jy.top";

    // ===== API 端点（从 web_listener.py 实际路由提取） =====
    public static final String RESOLVE = "/api/resolve";                          // POST
    public static final String START = "/api/start";                              // POST
    public static final String STOP = "/api/stop";                                // POST
    public static final String STOP_ALL = "/api/stop_all";                        // POST
    public static final String STATUS = "/api/status";                            // GET
    public static final String TOGGLE_RECORD_ALL = "/api/toggle_record_all";      // POST
    public static final String RECORD_ALL_STATUS = "/api/record_all_status";      // GET
    public static final String REAL_NAMES = "/api/real_names";                    // GET
    public static final String HISTORY_ROOMS = "/api/history_rooms";              // GET
    public static final String HISTORY_ALL_ALL = "/api/history_all_all";          // GET
    public static final String SEARCH_HISTORY_LIST = "/api/search_history/list";  // GET
    public static final String SEARCH_HISTORY_SAVE = "/api/search_history/save";  // POST
    public static final String SEARCH_HISTORY_DELETE = "/api/search_history/delete"; // POST

    /** /stream/<room_id> SSE 实时事件流 */
    public static String streamUrl(String roomId) {
        return BASE_URL + "/stream/" + roomId;
    }

    /** /api/history/<room_id> 获取当前监听的房间历史 */
    public static String historyRoom(String roomId) {
        return BASE_URL + "/api/history/" + roomId;
    }

    /** /api/all_records/<room_id> 获取全部用户记录（带可选 hours 参数） */
    public static String allRecords(String roomId, int hours) {
        String url = BASE_URL + "/api/all_records/" + roomId;
        if (hours > 0) {
            url += "?hours=" + hours;
        }
        return url;
    }

    /** /api/interactions/<room_id>/<sec_uid> 获取互动记录 */
    public static String interactions(String roomId, String secUid) {
        return BASE_URL + "/api/interactions/" + roomId + "/" + secUid;
    }
}
