/**
 * 批次任务管理组件（通用 batch_jobs）
 * 提供批次列表（含子任务统计）、运行、清空队列、按 job 移除队列。
 * 设计文档：cursor_docs/030202-批次任务batch_jobs与Step02清洗批次管理功能对比与缺口分析.md
 */
(function() {
    'use strict';

    const { defineComponent, ref, computed, onMounted, inject } = Vue;
    const { ElMessage, ElMessageBox } = ElementPlus;
    const icons = ElementPlusIconsVue;
    const { BATCH_JOBS_API_PREFIX, formatDateTime, PAGE_SIZE_OPTIONS } = window.PipelineCommon || {};

    const DEFAULT_PAGE_SIZES = PAGE_SIZE_OPTIONS || [10, 20, 50, 100];
    const fmtDateTime =
        formatDateTime ||
        (s =>
            s
                ? new Date(s).toLocaleString('zh-CN', {
                      year: 'numeric',
                      month: '2-digit',
                      day: '2-digit',
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit'
                  })
                : '-');

    window.PipelineBatchJobsComponent = defineComponent({
        name: 'PipelineBatchJobsComponent',
        props: {
            tabId: { type: String, default: '' }
        },
        setup() {
            const { openTabForJobTasks } = inject('pipelineTabManager', { openTabForJobTasks: () => {} });
            const list = ref([]);
            const total = ref(0);
            const loading = ref(false);
            const queryExpanded = ref(true);
            const queryCode = ref('');
            const queryJobType = ref('');
            const limit = ref(20);
            const offset = ref(0);
            const currentPage = computed(() =>
                limit.value > 0 ? Math.floor(offset.value / limit.value) + 1 : 1
            );
            const queueStats = ref({ queue_size: 0, in_flight_count: 0 });

            async function loadList() {
                loading.value = true;
                try {
                    const params = {
                        code: queryCode.value?.trim() || undefined,
                        job_type: queryJobType.value?.trim() || undefined,
                        limit: limit.value,
                        offset: offset.value
                    };
                    const res = await axios.get(BATCH_JOBS_API_PREFIX, { params });
                    list.value = res.data?.items || [];
                    total.value = res.data?.total ?? 0;
                } catch (err) {
                    console.error('加载批次列表失败', err);
                    const message = err?.response?.data?.detail || err?.message || '加载失败';
                    ElMessage.error(`加载批次列表失败：${message}`);
                    list.value = [];
                    total.value = 0;
                } finally {
                    loading.value = false;
                }
            }

            async function loadQueueStats() {
                try {
                    const res = await axios.get(`${BATCH_JOBS_API_PREFIX}/queue-stats`);
                    queueStats.value = res.data || { queue_size: 0, in_flight_count: 0 };
                } catch (_) {
                    queueStats.value = { queue_size: 0, in_flight_count: 0 };
                }
            }

            function onSearch() {
                offset.value = 0;
                loadList();
            }

            function onResetQuery() {
                queryCode.value = '';
                queryJobType.value = '';
                offset.value = 0;
                loadList();
            }

            function onPageChange(page) {
                offset.value = (page - 1) * limit.value;
                loadList();
            }

            function onSizeChange() {
                offset.value = 0;
                loadList();
            }

            const actionLoading = ref(false);
            async function onClearQueue() {
                actionLoading.value = true;
                try {
                    const res = await axios.post(`${BATCH_JOBS_API_PREFIX}/clear-queue`);
                    const n = res.data?.removed ?? 0;
                    ElMessage.success(`已清空队列，共移除 ${n} 条`);
                    loadList();
                    loadQueueStats();
                } catch (err) {
                    const msg = err?.response?.data?.detail || err?.message || '操作失败';
                    ElMessage.error(`清空队列失败：${msg}`);
                } finally {
                    actionLoading.value = false;
                }
            }

            async function onRunBatch(row) {
                actionLoading.value = true;
                try {
                    const res = await axios.post(`${BATCH_JOBS_API_PREFIX}/${row.id}/run`);
                    const n = res.data?.enqueued ?? 0;
                    if (n > 0) ElMessage.success(`已加入队列，共 ${n} 条`);
                    else ElMessage.warning('无待处理任务，或任务已在队列中');
                    loadList();
                    loadQueueStats();
                } catch (err) {
                    const msg = err?.response?.data?.detail || err?.message || '操作失败';
                    ElMessage.error(`运行失败：${msg}`);
                } finally {
                    actionLoading.value = false;
                }
            }

            async function onRemoveBatch(row) {
                actionLoading.value = true;
                try {
                    const res = await axios.post(`${BATCH_JOBS_API_PREFIX}/remove-batch`, {
                        job_id: row.id
                    });
                    const n = res.data?.removed ?? 0;
                    ElMessage.success(`已从队列移除该批次 ${n} 条`);
                    loadList();
                    loadQueueStats();
                } catch (err) {
                    const msg = err?.response?.data?.detail || err?.message || '操作失败';
                    ElMessage.error(`移除队列失败：${msg}`);
                } finally {
                    actionLoading.value = false;
                }
            }

            async function onRerunBatch(row) {
                try {
                    await ElMessageBox.confirm(
                        '即将将该批次下所有任务都重新执行，请慎重！',
                        '重跑确认',
                        { type: 'warning' }
                    );
                } catch (_) {
                    return;
                }
                actionLoading.value = true;
                try {
                    const res = await axios.post(`${BATCH_JOBS_API_PREFIX}/${row.id}/rerun`);
                    const n = res.data?.enqueued ?? 0;
                    ElMessage.success(`重跑已入队，共 ${n} 条`);
                    loadList();
                    loadQueueStats();
                } catch (err) {
                    const msg = err?.response?.data?.detail || err?.message || '操作失败';
                    ElMessage.error(`重跑失败：${msg}`);
                } finally {
                    actionLoading.value = false;
                }
            }

            function openJobTasks(row) {
                openTabForJobTasks(row.id, row.code);
            }

            onMounted(() => {
                loadList();
                loadQueueStats();
            });

            return {
                openJobTasks,
                list,
                total,
                loading,
                actionLoading,
                queryExpanded,
                queryCode,
                queryJobType,
                limit,
                offset,
                currentPage,
                queueStats,
                PAGE_SIZE_OPTIONS: DEFAULT_PAGE_SIZES,
                loadList,
                onSearch,
                onResetQuery,
                onPageChange,
                onSizeChange,
                onClearQueue,
                onRunBatch,
                onRerunBatch,
                onRemoveBatch,
                formatDateTime: fmtDateTime,
                Search: icons.Search,
                ArrowDown: icons.ArrowDown,
                ArrowUp: icons.ArrowUp,
                Document: icons.Document
            };
        },
        template: `
        <div style="height:100%;width:100%;display:flex;flex-direction:column;background:#fff;">
            <div style="padding:12px 20px;border-bottom:1px solid #e4e7ed;display:flex;justify-content:space-between;align-items:center;">
                <span style="font-weight:600;">Step03-1批次任务管理</span>
                <span style="font-size:13px;color:#606266;">排队 {{ queueStats.queue_size }}，执行中+排队 {{ queueStats.in_flight_count }}</span>
                <el-button type="warning" size="small" :loading="actionLoading" @click="onClearQueue">清空队列</el-button>
            </div>
            <div style="border-bottom:1px solid #e4e7ed;">
                <div style="padding:8px 12px;display:flex;align-items:center;gap:8px;cursor:pointer;" @click="queryExpanded=!queryExpanded">
                    <el-icon><component :is="queryExpanded ? 'ArrowUp' : 'ArrowDown'" /></el-icon>
                    <span style="font-size:13px;color:#606266;">查询条件</span>
                    <el-button size="small" type="primary" @click.stop="onSearch" :icon="Search">查询</el-button>
                    <el-button size="small" @click.stop="onResetQuery">重置</el-button>
                </div>
                <div v-show="queryExpanded" style="padding:0 12px 12px;display:flex;flex-wrap:wrap;gap:12px;align-items:center;">
                    <el-input v-model="queryCode" placeholder="批次编码（包含）" clearable style="width:200px;" size="small" />
                    <el-input v-model="queryJobType" placeholder="任务类型（精确）" clearable style="width:180px;" size="small" />
                </div>
            </div>
            <div style="flex:1;min-width:0;overflow:auto;padding:12px;">
                <el-table :data="list" v-loading="loading" stripe border size="small" style="width:100%;">
                    <el-table-column prop="code" label="批次编码" min-width="160" show-overflow-tooltip />
                    <el-table-column prop="job_type" label="任务类型" width="140" show-overflow-tooltip />
                    <el-table-column prop="total_count" label="预期总数" width="100" />
                    <el-table-column prop="tasks_total" label="实际任务量" width="110" />
                    <el-table-column prop="status_pending_count" label="待处理" width="90" />
                    <el-table-column prop="status_running_count" label="执行中" width="90" />
                    <el-table-column prop="status_success_count" label="成功" width="90" />
                    <el-table-column prop="status_failed_count" label="失败" width="90" />
                    <el-table-column label="创建时间" width="180"><template #default="scope">{{ formatDateTime(scope.row.create_time) }}</template></el-table-column>
                    <el-table-column label="更新时间" width="180"><template #default="scope">{{ formatDateTime(scope.row.update_time) }}</template></el-table-column>
                    <el-table-column label="操作" width="260" fixed="right">
                        <template #default="scope">
                            <span style="white-space:nowrap;">
                                <el-button link type="primary" size="small" @click="openJobTasks(scope.row)" :icon="Document">任务</el-button>
                                <el-button link type="primary" size="small" :loading="actionLoading" @click="onRunBatch(scope.row)">运行</el-button>
                                <el-button link type="danger" size="small" :loading="actionLoading" @click="onRerunBatch(scope.row)">重跑</el-button>
                                <el-button link type="warning" size="small" :loading="actionLoading" @click="onRemoveBatch(scope.row)">移除队列</el-button>
                            </span>
                        </template>
                    </el-table-column>
                </el-table>
            </div>
            <div style="padding:12px 20px;border-top:1px solid #e4e7ed;display:flex;align-items:center;justify-content:space-between;">
                <span style="color:#606266;font-size:13px;">共 {{ total }} 条，每页
                    <el-select v-model="limit" size="small" style="width:80px;margin:0 4px;" @change="onSizeChange">
                        <el-option v-for="s in PAGE_SIZE_OPTIONS" :key="s" :label="s" :value="s" />
                    </el-select>条
                </span>
                <el-pagination
                    :current-page="currentPage"
                    :page-size="limit"
                    :total="total"
                    layout="prev,pager,next"
                    @current-change="onPageChange"
                />
            </div>
        </div>
        `
    });
})();
