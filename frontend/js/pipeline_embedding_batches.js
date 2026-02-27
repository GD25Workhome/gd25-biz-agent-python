/**
 * Step03 批量创建 Embedding 组件
 * 复用 Step02 改写后数据项列表作为数据源，
 * 在当前查询条件基础上创建 Embedding 批次任务。
 *
 * 前端交互设计：cursor_docs/022702-Step03批量Embedding前后端改造清单.md
 */
(function() {
    'use strict';

    const { defineComponent, ref, reactive, computed, onMounted, nextTick } = Vue;
    const { ElMessage, ElMessageBox } = ElementPlus;
    const icons = ElementPlusIconsVue;
    const { API_PREFIX, formatDateTime, getApiErrorMsg, PAGE_SIZE_OPTIONS } = window.PipelineCommon || {};

    // 将 data-cleaning 前缀去掉，得到通用批次接口前缀，例如：http://host/api/v1
    const BATCH_API_PREFIX = API_PREFIX ? API_PREFIX.replace(/\/data-cleaning$/, '') : '';

    window.PipelineEmbeddingBatchComponent = defineComponent({
        name: 'PipelineEmbeddingBatchComponent',
        props: {
            tabId: { type: String, default: '' }
        },
        setup() {
            // 列表相关状态
            const items = ref([]);
            const itemsTotal = ref(0);
            const itemsLoading = ref(false);
            const limit = ref(20);
            const offset = ref(0);
            const pageSizeOpts = PAGE_SIZE_OPTIONS || [10, 20, 50, 100];
            const currentPage = computed(() =>
                limit.value > 0 ? Math.floor(offset.value / limit.value) + 1 : 1
            );

            // 查询条件
            const queryExpanded = ref(true);
            const queryScenarioDescription = ref('');
            const queryRewrittenQuestion = ref('');
            const queryRewrittenAnswer = ref('');
            const queryRewrittenRule = ref('');
            const querySourceDatasetId = ref('');
            const querySourceItemId = ref('');
            const queryScenarioType = ref('');
            const querySubScenarioType = ref('');
            const queryBatchCode = ref('');
            const queryTraceId = ref('');
            const queryStatus = ref('success'); // 默认只看成功的数据

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

            // 数据集选择（复用 Step01 的交互思路，但限制单选）
            const selectedDataset = ref(null); // { id, name }
            const datasetPickerVisible = ref(false);
            const datasetList = ref([]);
            const datasetListLoading = ref(false);
            const datasetTableRef = ref(null);

            async function openDatasetPicker() {
                datasetPickerVisible.value = true;
                datasetListLoading.value = true;
                datasetList.value = [];
                try {
                    const res = await axios.get(`${BATCH_API_PREFIX}/data-cleaning/datasets`, {
                        params: { limit: 500, offset: 0 }
                    });
                    datasetList.value = res.data?.items || [];
                } catch (err) {
                    ElMessage.error(
                        '加载数据集列表失败: ' +
                            (getApiErrorMsg ? getApiErrorMsg(err) : (err.response?.data?.detail || err.message))
                    );
                } finally {
                    datasetListLoading.value = false;
                }
                await nextTick();
                const tbl = datasetTableRef.value;
                if (tbl && typeof tbl.clearSelection === 'function') {
                    tbl.clearSelection();
                    if (selectedDataset.value?.id) {
                        const row = datasetList.value.find(r => r.id === selectedDataset.value.id);
                        if (row) tbl.toggleRowSelection(row, true);
                    }
                }
            }

            function handleDatasetSelectionChange(rows) {
                // 保持单选语义：只取最后一个选中的数据集
                const last = rows && rows.length ? rows[rows.length - 1] : null;
                selectedDataset.value = last ? { id: last.id, name: last.name || last.id } : null;
            }

            function confirmDatasetPicker() {
                const tbl = datasetTableRef.value;
                const rows =
                    (tbl && typeof tbl.getSelectionRows === 'function' && tbl.getSelectionRows()) || [];
                const last = rows && rows.length ? rows[rows.length - 1] : null;
                selectedDataset.value = last ? { id: last.id, name: last.name || last.id } : null;
                querySourceDatasetId.value = selectedDataset.value?.id || '';
                datasetPickerVisible.value = false;
            }

            function clearSelectedDataset() {
                selectedDataset.value = null;
                querySourceDatasetId.value = '';
            }

            // 查询与分页
            async function loadItems() {
                itemsLoading.value = true;
                try {
                    const params = {
                        scenario_description: queryScenarioDescription.value?.trim() || undefined,
                        rewritten_question: queryRewrittenQuestion.value?.trim() || undefined,
                        rewritten_answer: queryRewrittenAnswer.value?.trim() || undefined,
                        rewritten_rule: queryRewrittenRule.value?.trim() || undefined,
                        source_dataset_id: querySourceDatasetId.value?.trim() || undefined,
                        source_item_id: querySourceItemId.value?.trim() || undefined,
                        scenario_type: queryScenarioType.value?.trim() || undefined,
                        sub_scenario_type: querySubScenarioType.value?.trim() || undefined,
                        batch_code: queryBatchCode.value?.trim() || undefined,
                        trace_id: queryTraceId.value?.trim() || undefined,
                        status: queryStatus.value?.trim() || undefined,
                        limit: limit.value,
                        offset: offset.value
                    };
                    const res = await axios.get(`${API_PREFIX}/data-items-rewritten`, { params });
                    items.value = res.data?.items || [];
                    itemsTotal.value = res.data?.total ?? 0;
                } catch (err) {
                    items.value = [];
                    itemsTotal.value = 0;
                    ElMessage.error(
                        '加载数据失败: ' +
                            (getApiErrorMsg ? getApiErrorMsg(err) : (err.response?.data?.detail || err.message))
                    );
                } finally {
                    itemsLoading.value = false;
                }
            }

            function onSearch() {
                offset.value = 0;
                loadItems();
            }

            function onResetQuery() {
                queryScenarioDescription.value = '';
                queryRewrittenQuestion.value = '';
                queryRewrittenAnswer.value = '';
                queryRewrittenRule.value = '';
                querySourceDatasetId.value = '';
                querySourceItemId.value = '';
                queryScenarioType.value = '';
                querySubScenarioType.value = '';
                queryBatchCode.value = '';
                queryTraceId.value = '';
                queryStatus.value = 'success';
                selectedDataset.value = null;
                offset.value = 0;
                loadItems();
            }

            function onPageChange(page) {
                offset.value = (page - 1) * limit.value;
                loadItems();
            }

            function onSizeChange() {
                offset.value = 0;
                loadItems();
            }

            // 执行批量 Embedding
            const executing = ref(false);
            async function onExecuteEmbeddingBatch() {
                const datasetId = querySourceDatasetId.value?.trim();
                if (!datasetId) {
                    ElMessage.warning('请先选择数据集后再进行批量 Embedding');
                    return;
                }
                // 二次确认，避免误操作
                try {
                    await ElMessageBox.confirm(
                        '将基于当前查询条件创建 Embedding 批次任务，任务将异步执行，是否继续？',
                        '提示',
                        { type: 'warning' }
                    );
                } catch (err) {
                    if (err === 'cancel') return;
                }

                executing.value = true;
                try {
                    const queryParams = {
                        source_dataset_id: datasetId,
                        scenario_type: queryScenarioType.value?.trim() || undefined,
                        sub_scenario_type: querySubScenarioType.value?.trim() || undefined,
                        status: queryStatus.value?.trim() || undefined,
                        scenario_description: queryScenarioDescription.value?.trim() || undefined,
                        rewritten_question: queryRewrittenQuestion.value?.trim() || undefined,
                        rewritten_answer: queryRewrittenAnswer.value?.trim() || undefined,
                        rewritten_rule: queryRewrittenRule.value?.trim() || undefined,
                        source_item_id: querySourceItemId.value?.trim() || undefined,
                        batch_code: queryBatchCode.value?.trim() || undefined,
                        trace_id: queryTraceId.value?.trim() || undefined
                    };
                    const payload = {
                        job_type: 'pipeline_embedding',
                        query_params: queryParams
                    };
                    const res = await axios.post(`${BATCH_API_PREFIX}/batch-jobs/create`, payload);
                    const data = res.data || {};
                    const batchCode = data.batch_code || '';
                    const total = data.total ?? 0;
                    ElMessage.success(
                        `批次创建成功，批次编码：${batchCode || '-'}，任务数：${total}`
                    );
                } catch (err) {
                    ElMessage.error(
                        '创建 Embedding 批次失败: ' +
                            (getApiErrorMsg ? getApiErrorMsg(err) : (err.response?.data?.detail || err.message))
                    );
                } finally {
                    executing.value = false;
                }
            }

            onMounted(() => {
                // 默认以 status=success 加载一次
                loadItems();
            });

            return {
                items,
                itemsTotal,
                itemsLoading,
                queryExpanded,
                queryScenarioDescription,
                queryRewrittenQuestion,
                queryRewrittenAnswer,
                queryRewrittenRule,
                querySourceDatasetId,
                querySourceItemId,
                queryScenarioType,
                querySubScenarioType,
                queryBatchCode,
                queryTraceId,
                queryStatus,
                limit,
                offset,
                currentPage,
                PAGE_SIZE_OPTIONS: pageSizeOpts,
                selectedDataset,
                datasetPickerVisible,
                datasetList,
                datasetListLoading,
                datasetTableRef,
                openDatasetPicker,
                handleDatasetSelectionChange,
                confirmDatasetPicker,
                clearSelectedDataset,
                onSearch,
                onResetQuery,
                onPageChange,
                onSizeChange,
                onExecuteEmbeddingBatch,
                executing,
                formatDateTime: fmtDateTime,
                Search: icons.Search,
                ArrowDown: icons.ArrowDown,
                ArrowUp: icons.ArrowUp
            };
        },
        template: `
        <div style="height:100%;width:100%;min-width:0;display:flex;flex-direction:column;background:#fff;">
            <div style="padding:12px 20px;border-bottom:1px solid #e4e7ed;display:flex;justify-content:space-between;align-items:center;">
                <span style="font-weight:600;">Step03 批量创建 Embedding</span>
                <div style="display:flex;align-items:center;gap:8px;">
                    <span v-if="selectedDataset && selectedDataset.name" style="font-size:12px;color:#606266;">
                        当前数据集：{{ selectedDataset.name }}（{{ selectedDataset.id }}）
                    </span>
                    <el-button type="warning" size="small" :loading="executing" @click="onExecuteEmbeddingBatch">
                        批量Embedding
                    </el-button>
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
                    <!-- 数据集选择（来源 DataSetsId，精确） -->
                    <div style="display:flex;align-items:center;gap:8px;">
                        <span style="font-size:12px;color:#606266;">数据集：</span>
                        <el-input
                            v-model="querySourceDatasetId"
                            placeholder="dataSetsId（精确）"
                            clearable
                            style="width:180px;"
                            size="small"
                        />
                        <el-button size="small" @click.stop="openDatasetPicker">选择数据集</el-button>
                        <el-tag
                            v-if="selectedDataset"
                            size="small"
                            type="info"
                            closable
                            @close="clearSelectedDataset"
                        >
                            {{ selectedDataset.name }}（{{ selectedDataset.id }}）
                        </el-tag>
                    </div>
                    <div style="display:flex;align-items:center;gap:4px;">
                        <span style="font-size:12px;color:#606266;">场景类型：</span>
                        <el-input v-model="queryScenarioType" placeholder="包含" clearable style="width:140px;" size="small" />
                    </div>
                    <div style="display:flex;align-items:center;gap:4px;">
                        <span style="font-size:12px;color:#606266;">子场景类型：</span>
                        <el-input v-model="querySubScenarioType" placeholder="包含" clearable style="width:140px;" size="small" />
                    </div>
                    <div style="display:flex;align-items:center;gap:4px;">
                        <span style="font-size:12px;color:#606266;">执行状态：</span>
                        <el-select v-model="queryStatus" placeholder="全部" clearable style="width:120px;" size="small">
                            <el-option label="待处理" value="init" />
                            <el-option label="执行中" value="processing" />
                            <el-option label="成功" value="success" />
                            <el-option label="失败" value="failed" />
                        </el-select>
                    </div>
                    <div style="display:flex;align-items:center;gap:4px;">
                        <span style="font-size:12px;color:#606266;">场景描述：</span>
                        <el-input v-model="queryScenarioDescription" placeholder="包含" clearable style="width:160px;" size="small" />
                    </div>
                    <div style="display:flex;align-items:center;gap:4px;">
                        <span style="font-size:12px;color:#606266;">改写问题：</span>
                        <el-input v-model="queryRewrittenQuestion" placeholder="包含" clearable style="width:160px;" size="small" />
                    </div>
                    <div style="display:flex;align-items:center;gap:4px;">
                        <span style="font-size:12px;color:#606266;">改写回答：</span>
                        <el-input v-model="queryRewrittenAnswer" placeholder="包含" clearable style="width:160px;" size="small" />
                    </div>
                    <div style="display:flex;align-items:center;gap:4px;">
                        <span style="font-size:12px;color:#606266;">改写规则：</span>
                        <el-input v-model="queryRewrittenRule" placeholder="包含" clearable style="width:160px;" size="small" />
                    </div>
                    <div style="display:flex;align-items:center;gap:4px;">
                        <span style="font-size:12px;color:#606266;">来源 dataItemsId：</span>
                        <el-input v-model="querySourceItemId" placeholder="精确" clearable style="width:160px;" size="small" />
                    </div>
                    <div style="display:flex;align-items:center;gap:4px;">
                        <span style="font-size:12px;color:#606266;">批次 code：</span>
                        <el-input v-model="queryBatchCode" placeholder="包含" clearable style="width:140px;" size="small" />
                    </div>
                    <div style="display:flex;align-items:center;gap:4px;">
                        <span style="font-size:12px;color:#606266;">traceId：</span>
                        <el-input v-model="queryTraceId" placeholder="包含" clearable style="width:140px;" size="small" />
                    </div>
                </div>
            </div>
            <div style="flex:1;min-width:0;overflow:auto;padding:12px;">
                <el-table :data="items" v-loading="itemsLoading" stripe border size="small" style="width:100%">
                    <el-table-column type="expand" width="48">
                        <template #default="props">
                            <div style="padding:12px 24px;background:#fafafa;">
                                <div v-if="props.row.scenario_description"><strong>场景描述：</strong><pre style="margin:4px 0;font-size:12px;white-space:pre-wrap;word-break:break-all;">{{ props.row.scenario_description }}</pre></div>
                                <div v-if="props.row.rewritten_question"><strong>改写后的问题：</strong><pre style="margin:4px 0;font-size:12px;white-space:pre-wrap;word-break:break-all;">{{ props.row.rewritten_question }}</pre></div>
                                <div v-if="props.row.rewritten_answer"><strong>改写后的回答：</strong><pre style="margin:4px 0;font-size:12px;white-space:pre-wrap;word-break:break-all;">{{ props.row.rewritten_answer }}</pre></div>
                                <div v-if="props.row.rewritten_rule"><strong>改写后的规则：</strong><pre style="margin:4px 0;font-size:12px;white-space:pre-wrap;word-break:break-all;">{{ props.row.rewritten_rule }}</pre></div>
                                <div v-if="props.row.rewrite_basis"><strong>改写依据：</strong><pre style="margin:4px 0;font-size:12px;white-space:pre-wrap;word-break:break-all;">{{ props.row.rewrite_basis }}</pre></div>
                                <div v-if="props.row.trace_id"><strong>流程 traceId：</strong><span style="font-size:12px;">{{ props.row.trace_id }}</span></div>
                                <div v-if="props.row.batch_code"><strong>批次 code：</strong><span style="font-size:12px;">{{ props.row.batch_code }}</span></div>
                                <p v-if="!props.row.scenario_description&&!props.row.rewritten_question&&!props.row.rewritten_answer&&!props.row.rewritten_rule&&!props.row.rewrite_basis&&!props.row.trace_id&&!props.row.batch_code" style="color:#909399;">无扩展内容</p>
                            </div>
                        </template>
                    </el-table-column>
                    <el-table-column prop="id" label="ID" width="180" show-overflow-tooltip />
                    <el-table-column prop="batch_code" label="批次code" min-width="100" show-overflow-tooltip />
                    <el-table-column prop="source_dataset_id" label="来源 dataSetsId" min-width="120" show-overflow-tooltip />
                    <el-table-column prop="source_item_id" label="来源 dataItemsId" min-width="120" show-overflow-tooltip />
                    <el-table-column prop="scenario_type" label="场景类型" min-width="140" show-overflow-tooltip />
                    <el-table-column prop="sub_scenario_type" label="子场景类型" min-width="140" show-overflow-tooltip />
                    <el-table-column prop="status" label="执行状态" width="100" show-overflow-tooltip />
                    <el-table-column prop="trace_id" label="traceId" min-width="140" show-overflow-tooltip />
                    <el-table-column prop="scenario_confidence" label="场景置信度" width="120" />
                    <el-table-column prop="ai_score" label="AI 评分" width="100" />
                    <el-table-column prop="manual_score" label="人工评分" width="100" />
                    <el-table-column label="创建时间" width="180">
                        <template #default="scope">{{ formatDateTime(scope.row.created_at) }}</template>
                    </el-table-column>
                    <el-table-column label="更新时间" width="180">
                        <template #default="scope">{{ formatDateTime(scope.row.updated_at) }}</template>
                    </el-table-column>
                </el-table>
            </div>
            <div style="padding:12px 20px;border-top:1px solid #e4e7ed;display:flex;align-items:center;justify-content:space-between;">
                <span style="color:#606266;font-size:13px;">共 {{ itemsTotal }} 条，每页
                    <el-select v-model="limit" size="small" style="width:80px;margin:0 4px;" @change="onSizeChange">
                        <el-option v-for="s in PAGE_SIZE_OPTIONS" :key="s" :label="s" :value="s" />
                    </el-select>条
                </span>
                <el-pagination
                    :current-page="currentPage"
                    :page-size="limit"
                    :total="itemsTotal"
                    layout="prev,pager,next"
                    @current-change="onPageChange"
                />
            </div>

            <!-- 数据集选择弹窗 -->
            <el-dialog
                v-model="datasetPickerVisible"
                title="选择数据集"
                width="720px"
            >
                <el-table
                    ref="datasetTableRef"
                    :data="datasetList"
                    v-loading="datasetListLoading"
                    size="small"
                    style="width:100%;"
                    @selection-change="handleDatasetSelectionChange"
                >
                    <el-table-column type="selection" width="48" />
                    <el-table-column prop="id" label="ID" min-width="180" show-overflow-tooltip />
                    <el-table-column prop="name" label="名称" min-width="160" show-overflow-tooltip />
                    <el-table-column prop="path_id" label="路径ID" min-width="120" show-overflow-tooltip />
                </el-table>
                <template #footer>
                    <div style="text-align:right;">
                        <el-button @click="datasetPickerVisible=false">取 消</el-button>
                        <el-button type="primary" @click="confirmDatasetPicker">确 定</el-button>
                    </div>
                </template>
            </el-dialog>
        </div>
        `
    });
})();

