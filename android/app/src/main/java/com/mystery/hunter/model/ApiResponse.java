package com.mystery.hunter.model;

import com.google.gson.annotations.SerializedName;

/**
 * 通用 API 响应包装
 * 所有 API 失败时返回: {"success": false, "error": "..."}
 */
public class ApiResponse {
    @SerializedName("success")
    public boolean success;

    @SerializedName("error")
    public String error;
}
