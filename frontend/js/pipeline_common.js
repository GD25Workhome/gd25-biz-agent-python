/**
 * 数据清洗模块公共工具与常量
 * 供 pipeline_*.js 组件复用
 * 设计文档：cursor_docs/020401-数据导入管理模块技术设计.md
 */
(function() {
    'use strict';

    const API_BASE = (typeof window !== 'undefined' && window.location?.origin)
        ? window.location.origin
        : 'http://localhost:8000';
    const API_PREFIX = `${API_BASE}/api/v1/data-cleaning`;
    /** 批次任务管理 API 前缀（设计文档：030202） */
    const BATCH_JOBS_API_PREFIX = `${API_BASE}/api/v1/batch-jobs`;

    window.PipelineCommon = {
        API_PREFIX,
        BATCH_JOBS_API_PREFIX,
        PAGE_SIZE_OPTIONS: [10, 20, 50, 100],

        /** 格式化日期时间 */
        formatDateTime(str) {
            if (!str) return '-';
            return new Date(str).toLocaleString('zh-CN', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            });
        },

        /** 解析 JSON 字段，失败时返回 undefined */
        parseJsonField(val, warningMsg = 'JSON 格式错误') {
            if (!val || String(val).trim() === '') return null;
            try {
                return JSON.parse(val);
            } catch {
                try {
                    if (typeof ElementPlus !== 'undefined' && ElementPlus.ElMessage) {
                        ElementPlus.ElMessage.warning(warningMsg);
                    }
                } catch (_) { /* ElementPlus 可能未加载 */ }
                return undefined;
            }
        },

        /** 从 API 错误中提取可读消息 */
        getApiErrorMsg(err) {
            if (!err) return '请求失败';
            const detail = err.response?.data?.detail;
            const msg = err.message;
            return detail ?? msg ?? '请求失败';
        }
    };
})();
