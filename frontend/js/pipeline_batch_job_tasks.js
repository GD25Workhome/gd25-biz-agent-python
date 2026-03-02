/**
 * 批次 job 下任务列表组件（子界面）
 * 从 Step03-1批次任务管理 点击「任务」打开，界面风格参考 Step01 数据项管理
 * API: GET /api/v1/batch-jobs/{job_id}/tasks
 */
(function() {
    'use strict';

    const { defineComponent, ref, computed, watch } = Vue;
    const { ElMessage } = ElementPlus;
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

    window.PipelineBatchJobTasksComponent = defineComponent({
        name: 'PipelineBatchJobTasksComponent',
        props: {
            jobId: { type: String, default: '' },
            jobCode: { type: String, default: '' }
        },
        setup(props) {
            const list = ref([]);
            const total = ref(0);
            const loading = ref(false);
            const queryExpanded = ref(true);
            const queryStatus = ref('');
            const limit = ref(20);
            const offset = ref(0);
            const currentPage = computed(() =>
                limit.value > 0 ? Math.floor(offset.value / limit.value) + 1 : 1
            );

            async function loadList() {
                if (!props.jobId) return;
                loading.value = true;
                try {
                    const params = {
                        status: queryStatus.value?.trim() || undefined,
                        limit: limit.value,
                        offset: offset.value
                    };
                    const res = await axios.get(`${BATCH_JOBS_API_PREFIX}/${props.jobId}/tasks`, {
                        params
                    });
                    list.value = res.data?.items || [];
                    total.value = res.data?.total ?? 0;
                } catch (err) {
                    console.error('加载任务列表失败', err);
                    const message = err?.response?.data?.detail || err?.message || '加载失败';
                    ElMessage.error(`加载任务列表失败：${message}`);
                    list.value = [];
                    total.value = 0;
                } finally {
                    loading.value = false;
                }
            }

            function onSearch() {
                offset.value = 0;
                loadList();
            }

            function onResetQuery() {
                queryStatus.value = '';
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

            function statusType(status) {
                if (status === 'success') return 'success';
                if (status === 'failed') return 'danger';
                if (status === 'running') return 'warning';
                return 'info';
            }

            watch(
                () => props.jobId,
                () => {
                    offset.value = 0;
                    loadList();
                },
                { immediate: true }
            );

            return {
                list,
                total,
                loading,
                queryExpanded,
                queryStatus,
                limit,
                offset,
                currentPage,
                PAGE_SIZE_OPTIONS: DEFAULT_PAGE_SIZES,
                loadList,
                onSearch,
                onResetQuery,
                onPageChange,
                onSizeChange,
                formatDateTime: fmtDateTime,
                statusType,
                Search: icons.Search,
                ArrowDown: icons.ArrowDown,
                ArrowUp: icons.ArrowUp,
                Document: icons.Document
            };
        },
        template: `
        <div style="height:100%;width:100%;min-width:0;display:flex;flex-direction:column;background:#fff;">
            <div style="padding:12px 20px;border-bottom:1px solid #e4e7ed;display:flex;justify-content:space-between;align-items:center;">
                <div style="display:flex;align-items:baseline;gap:6px;">
                    <span style="font-weight:600;">{{ jobCode || jobId || '任务列表' }}</span><span v-if="jobId" style="font-size:12px;color:#909399;">JobID: {{ jobId }}</span>
                </div>
            </div>
            <div style="border-bottom:1px solid #e4e7ed;">
                <div style="padding:8px 12px;display:flex;align-items:center;gap:8px;cursor:pointer;" @click="queryExpanded=!queryExpanded">
                    <el-icon><component :is="queryExpanded ? 'ArrowUp' : 'ArrowDown'" /></el-icon>
                    <span style="font-size:13px;color:#606266;">查询条件</span>
                    <el-button size="small" type="primary" @click.stop="onSearch" :icon="Search">查询</el-button>
                    <el-button size="small" @click.stop="onResetQuery">重置</el-button>
                </div>
                <div v-show="queryExpanded" style="padding:0 12px 12px;display:flex;flex-wrap:wrap;gap:12px;align-items:center;">
                    <el-select v-model="queryStatus" placeholder="状态" clearable style="width:140px;" size="small">
                        <el-option label="待处理" value="pending" />
                        <el-option label="执行中" value="running" />
                        <el-option label="成功" value="success" />
                        <el-option label="失败" value="failed" />
                    </el-select>
                </div>
            </div>
            <div style="flex:1;min-width:0;overflow:auto;padding:12px;">
                <el-table :data="list" v-loading="loading" stripe border size="small" style="width:100%;">
                    <el-table-column type="expand" width="48">
                        <template #default="props">
                            <div style="padding:12px 24px;background:#fafafa;">
                                <div v-if="props.row.execution_error_message"><strong>执行失败信息：</strong><pre style="margin:4px 0;font-size:12px;white-space:pre-wrap;word-break:break-all;">{{ props.row.execution_error_message }}</pre></div>
                                <p v-else style="color:#909399;">无失败信息</p>
                            </div>
                        </template>
                    </el-table-column>
                    <el-table-column prop="id" label="任务ID" min-width="180" show-overflow-tooltip />
                    <el-table-column prop="source_table_id" label="来源表ID" width="140" show-overflow-tooltip />
                    <el-table-column prop="source_table_name" label="来源表名" width="180" show-overflow-tooltip />
                    <el-table-column prop="status" label="状态" width="100">
                        <template #default="scope">
                            <el-tag :type="statusType(scope.row.status)" size="small">{{ scope.row.status || '-' }}</el-tag>
                        </template>
                    </el-table-column>
                    <el-table-column prop="execution_return_key" label="返回key" min-width="120" show-overflow-tooltip />
                    <el-table-column label="创建时间" width="180"><template #default="scope">{{ formatDateTime(scope.row.create_time) }}</template></el-table-column>
                    <el-table-column label="更新时间" width="180"><template #default="scope">{{ formatDateTime(scope.row.update_time) }}</template></el-table-column>
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
