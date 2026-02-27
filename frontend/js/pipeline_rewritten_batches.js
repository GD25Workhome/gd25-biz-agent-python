(function() {
    'use strict';

    const { defineComponent, ref, computed, onMounted } = Vue;
    const { ElMessage } = ElementPlus;
    const icons = ElementPlusIconsVue;
    const { API_PREFIX, formatDateTime, PAGE_SIZE_OPTIONS } = window.PipelineCommon || {};

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

    window.PipelineRewrittenBatchesComponent = defineComponent({
        name: 'PipelineRewrittenBatchesComponent',
        props: {
            tabId: { type: String, default: '' }
        },
        setup() {
            const list = ref([]);
            const total = ref(0);
            const loading = ref(false);
            const queryExpanded = ref(true);
            const queryBatchCode = ref('');
            const limit = ref(20);
            const offset = ref(0);
            const currentPage = computed(() =>
                limit.value > 0 ? Math.floor(offset.value / limit.value) + 1 : 1
            );

            async function loadBatches() {
                loading.value = true;
                try {
                    const params = {
                        batch_code: queryBatchCode.value?.trim() || undefined,
                        limit: limit.value,
                        offset: offset.value
                    };
                    const res = await axios.get(`${API_PREFIX}/rewritten-batches`, { params });
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

            function onSearch() {
                offset.value = 0;
                loadBatches();
            }

            function onResetQuery() {
                queryBatchCode.value = '';
                offset.value = 0;
                loadBatches();
            }

            function onPageChange(page) {
                offset.value = (page - 1) * limit.value;
                loadBatches();
            }

            function onSizeChange() {
                offset.value = 0;
                loadBatches();
            }

            const actionLoading = ref(false);
            async function onClearQueue() {
                actionLoading.value = true;
                try {
                    const res = await axios.post(`${API_PREFIX}/rewritten-batches/clear-queue`);
                    const n = res.data?.removed ?? 0;
                    ElMessage.success(`已清空队列，共移除 ${n} 条`);
                    loadBatches();
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
                    const res = await axios.post(`${API_PREFIX}/rewritten-batches/run`, { batch_code: row.batch_code });
                    const n = res.data?.enqueued ?? 0;
                    if (n > 0) ElMessage.success(`已加入队列，共 ${n} 条`);
                    else ElMessage.warning('无待处理或执行中的任务，或任务已在队列中');
                    loadBatches();
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
                    const res = await axios.post(`${API_PREFIX}/rewritten-batches/remove-batch`, { batch_code: row.batch_code });
                    const n = res.data?.removed ?? 0;
                    ElMessage.success(`已从队列移除该批次 ${n} 条`);
                    loadBatches();
                } catch (err) {
                    const msg = err?.response?.data?.detail || err?.message || '操作失败';
                    ElMessage.error(`移除队列失败：${msg}`);
                } finally {
                    actionLoading.value = false;
                }
            }

            onMounted(() => loadBatches());

            return {
                list,
                total,
                loading,
                actionLoading,
                queryExpanded,
                queryBatchCode,
                limit,
                offset,
                currentPage,
                PAGE_SIZE_OPTIONS: DEFAULT_PAGE_SIZES,
                loadBatches,
                onSearch,
                onResetQuery,
                onPageChange,
                onSizeChange,
                onClearQueue,
                onRunBatch,
                onRemoveBatch,
                formatDateTime: fmtDateTime,
                Search: icons.Search,
                ArrowDown: icons.ArrowDown,
                ArrowUp: icons.ArrowUp
            };
        },
        template: `
        <div style="height:100%;width:100%;display:flex;flex-direction:column;background:#fff;">
            <div style="padding:12px 20px;border-bottom:1px solid #e4e7ed;display:flex;justify-content:space-between;align-items:center;">
                <span style="font-weight:600;">Step02 清洗批次管理</span>
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
                    <el-input v-model="queryBatchCode" placeholder="批次code（包含）" clearable style="width:220px;" size="small" />
                </div>
            </div>
            <div style="flex:1;min-width:0;overflow:auto;padding:12px;">
                <el-table :data="list" v-loading="loading" stripe border size="small" style="width:100%;">
                    <el-table-column prop="batch_code" label="批次code" min-width="160" show-overflow-tooltip />
                    <el-table-column prop="total_count" label="预期总数" width="100" />
                    <el-table-column prop="data_items_total" label="实际数据量" width="110" />
                    <el-table-column prop="status_init_count" label="待处理" width="90" />
                    <el-table-column prop="status_processing_count" label="执行中" width="90" />
                    <el-table-column prop="status_success_count" label="成功" width="90" />
                    <el-table-column prop="status_failed_count" label="失败" width="90" />
                    <el-table-column prop="status" label="批次状态" width="110" show-overflow-tooltip>
                        <template #default="scope">
                            <el-tag size="small" v-if="scope.row.status" type="info">{{ scope.row.status }}</el-tag>
                            <span v-else>-</span>
                        </template>
                    </el-table-column>
                    <el-table-column label="创建时间" width="180"><template #default="scope">{{ formatDateTime(scope.row.created_at) }}</template></el-table-column>
                    <el-table-column label="更新时间" width="180"><template #default="scope">{{ formatDateTime(scope.row.updated_at) }}</template></el-table-column>
                    <el-table-column label="操作" width="200" fixed="right">
                        <template #default="scope">
                            <span style="white-space:nowrap;">
                                <el-button link type="primary" size="small" :loading="actionLoading" @click="onRunBatch(scope.row)">运行</el-button>
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
