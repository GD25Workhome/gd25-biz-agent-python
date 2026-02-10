/**
 * Step02 数据清洗管理组件
 * 管理 pipeline_data_items_rewritten 改写后数据项
 * 设计文档：doc/总体设计规划/数据归档-schema/Step2-数据初步筛选.md
 */
(function() {
    'use strict';

    const { defineComponent, ref, reactive, computed, onMounted } = Vue;
    const { ElMessage, ElMessageBox } = ElementPlus;
    const icons = ElementPlusIconsVue;
    const { API_PREFIX, formatDateTime, parseJsonField, getApiErrorMsg, PAGE_SIZE_OPTIONS } = window.PipelineCommon || {};

    window.PipelineDataItemsRewrittenComponent = defineComponent({
        name: 'PipelineDataItemsRewrittenComponent',
        props: {
            tabId: { type: String, default: '' }
        },
        setup() {
            const items = ref([]);
            const itemsTotal = ref(0);
            const itemsLoading = ref(false);
            const itemDialogVisible = ref(false);
            const itemForm = reactive({
                scenario_description: '',
                rewritten_question: '',
                rewritten_answer: '',
                rewritten_rule: '',
                source_dataset_id: '',
                source_item_id: '',
                scenario_type: '',
                sub_scenario_type: '',
                rewrite_basis: '',
                scenario_confidence: '',
                trace_id: '',
                batch_code: '',
                status: '',
                ai_score: '',
                manual_score: ''
            });
            const itemEditingId = ref(null);
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
            const queryStatus = ref('');
            const limit = ref(20);
            const offset = ref(0);
            const pageSizeOpts = PAGE_SIZE_OPTIONS || [10, 20, 50, 100];
            const currentPage = computed(() => (limit.value > 0 ? Math.floor(offset.value / limit.value) + 1 : 1));

            const fmtDateTime = formatDateTime || (s => (s ? new Date(s).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '-'));

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
                queryStatus.value = '';
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
                    items.value = res.data.items || [];
                    itemsTotal.value = res.data.total ?? 0;
                } catch (err) {
                    ElMessage.error('加载数据失败: ' + (getApiErrorMsg ? getApiErrorMsg(err) : (err.response?.data?.detail || err.message)));
                    items.value = [];
                    itemsTotal.value = 0;
                } finally {
                    itemsLoading.value = false;
                }
            }

            function openItemEdit(row) {
                itemForm.scenario_description = row.scenario_description || '';
                itemForm.rewritten_question = row.rewritten_question || '';
                itemForm.rewritten_answer = row.rewritten_answer || '';
                itemForm.rewritten_rule = row.rewritten_rule || '';
                itemForm.source_dataset_id = row.source_dataset_id || '';
                itemForm.source_item_id = row.source_item_id || '';
                itemForm.scenario_type = row.scenario_type || '';
                itemForm.sub_scenario_type = row.sub_scenario_type || '';
                itemForm.rewrite_basis = row.rewrite_basis || '';
                itemForm.scenario_confidence = row.scenario_confidence != null ? String(row.scenario_confidence) : '';
                itemForm.trace_id = row.trace_id || '';
                itemForm.batch_code = row.batch_code || '';
                itemForm.status = row.status || '';
                itemForm.ai_score = row.ai_score != null ? String(row.ai_score) : '';
                itemForm.manual_score = row.manual_score != null ? String(row.manual_score) : '';
                itemEditingId.value = row.id;
                itemDialogVisible.value = true;
            }

            async function submitItemForm() {
                try {
                    const payload = {
                        scenario_description: itemForm.scenario_description || null,
                        rewritten_question: itemForm.rewritten_question || null,
                        rewritten_answer: itemForm.rewritten_answer || null,
                        rewritten_rule: itemForm.rewritten_rule || null,
                        source_dataset_id: itemForm.source_dataset_id || null,
                        source_item_id: itemForm.source_item_id || null,
                        scenario_type: itemForm.scenario_type || null,
                        sub_scenario_type: itemForm.sub_scenario_type || null,
                        rewrite_basis: itemForm.rewrite_basis || null,
                        scenario_confidence: itemForm.scenario_confidence !== '' ? parseFloat(itemForm.scenario_confidence) : null,
                        trace_id: itemForm.trace_id || null,
                        batch_code: itemForm.batch_code || null,
                        status: itemForm.status || null,
                        ai_score: itemForm.ai_score !== '' ? parseFloat(itemForm.ai_score) : null,
                        manual_score: itemForm.manual_score !== '' ? parseFloat(itemForm.manual_score) : null
                    };
                    await axios.put(`${API_PREFIX}/data-items-rewritten/${itemEditingId.value}`, payload);
                    ElMessage.success('更新成功');
                    itemDialogVisible.value = false;
                    loadItems();
                } catch (err) {
                    ElMessage.error(getApiErrorMsg ? getApiErrorMsg(err) : (err.response?.data?.detail || err.message));
                }
            }

            async function deleteItem(row) {
                try {
                    await ElMessageBox.confirm('确定删除该数据？', '提示', { type: 'warning' });
                    await axios.delete(`${API_PREFIX}/data-items-rewritten/${row.id}`);
                    ElMessage.success('删除成功');
                    loadItems();
                } catch (err) {
                    if (err !== 'cancel') ElMessage.error(getApiErrorMsg ? getApiErrorMsg(err) : (err.response?.data?.detail || err.message));
                }
            }

            onMounted(() => loadItems());

            return {
                items, itemsTotal, itemsLoading,
                queryExpanded,
                queryScenarioDescription, queryRewrittenQuestion, queryRewrittenAnswer, queryRewrittenRule,
                querySourceDatasetId, querySourceItemId,                 queryScenarioType, querySubScenarioType,
                queryBatchCode, queryTraceId, queryStatus,
                limit, offset, currentPage, PAGE_SIZE_OPTIONS: pageSizeOpts,
                itemDialogVisible, itemForm, itemEditingId,
                formatDateTime: fmtDateTime,
                loadItems, openItemEdit, submitItemForm, deleteItem,
                onSearch, onResetQuery, onPageChange, onSizeChange,
                Edit: icons.Edit, Delete: icons.Delete, Search: icons.Search, ArrowDown: icons.ArrowDown, ArrowUp: icons.ArrowUp
            };
        },
        template: `
        <div style="height:100%;width:100%;min-width:0;display:flex;flex-direction:column;background:#fff;">
            <div style="padding:12px 20px;border-bottom:1px solid #e4e7ed;display:flex;justify-content:space-between;align-items:center;">
                <span style="font-weight:600;">Step02 数据清洗管理</span>
            </div>
            <div style="border-bottom:1px solid #e4e7ed;">
                <div style="padding:8px 12px;display:flex;align-items:center;gap:8px;cursor:pointer;" @click="queryExpanded=!queryExpanded">
                    <el-icon><component :is="queryExpanded?'ArrowUp':'ArrowDown'" /></el-icon>
                    <span style="font-size:13px;color:#606266;">查询条件</span>
                    <el-button size="small" type="primary" @click.stop="onSearch" :icon="Search">查询</el-button>
                    <el-button size="small" @click.stop="onResetQuery">重置</el-button>
                </div>
                <div v-show="queryExpanded" style="padding:0 12px 12px;display:flex;flex-wrap:wrap;gap:12px;align-items:center;">
                    <el-input v-model="queryScenarioDescription" placeholder="场景描述（包含）" clearable style="width:160px;" size="small" />
                    <el-input v-model="queryRewrittenQuestion" placeholder="改写后的问题（包含）" clearable style="width:160px;" size="small" />
                    <el-input v-model="queryRewrittenAnswer" placeholder="改写后的回答（包含）" clearable style="width:160px;" size="small" />
                    <el-input v-model="queryRewrittenRule" placeholder="改写后的规则（包含）" clearable style="width:160px;" size="small" />
                    <el-input v-model="querySourceDatasetId" placeholder="来源 dataSetsId（精确）" clearable style="width:160px;" size="small" />
                    <el-input v-model="querySourceItemId" placeholder="来源 dataItemsId（精确）" clearable style="width:160px;" size="small" />
                    <el-input v-model="queryScenarioType" placeholder="场景类型（包含）" clearable style="width:140px;" size="small" />
                    <el-input v-model="querySubScenarioType" placeholder="子场景类型（包含）" clearable style="width:140px;" size="small" />
                    <el-input v-model="queryBatchCode" placeholder="批次code（包含）" clearable style="width:140px;" size="small" />
                    <el-input v-model="queryTraceId" placeholder="traceId（包含）" clearable style="width:140px;" size="small" />
                    <el-select v-model="queryStatus" placeholder="执行状态" clearable style="width:120px;" size="small">
                        <el-option label="success" value="success" />
                        <el-option label="failed" value="failed" />
                    </el-select>
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
                                <div v-if="props.row.execution_metadata"><strong>执行元数据：</strong><pre style="margin:4px 0;font-size:12px;white-space:pre-wrap;word-break:break-all;">{{ typeof props.row.execution_metadata === 'object' ? JSON.stringify(props.row.execution_metadata, null, 2) : props.row.execution_metadata }}</pre></div>
                                <div v-if="props.row.ai_tags"><strong>AI 标签：</strong><pre style="margin:4px 0;font-size:12px;white-space:pre-wrap;word-break:break-all;">{{ typeof props.row.ai_tags === 'object' ? JSON.stringify(props.row.ai_tags, null, 2) : props.row.ai_tags }}</pre></div>
                                <p v-if="!props.row.scenario_description&&!props.row.rewritten_question&&!props.row.rewritten_answer&&!props.row.rewritten_rule&&!props.row.rewrite_basis&&!props.row.trace_id&&!props.row.batch_code&&!props.row.execution_metadata&&!props.row.ai_tags" style="color:#909399;">无扩展内容</p>
                            </div>
                        </template>
                    </el-table-column>
                    <el-table-column prop="id" label="ID" width="180" show-overflow-tooltip />
                    <el-table-column prop="batch_code" label="批次code" min-width="100" show-overflow-tooltip />
                    <el-table-column prop="source_dataset_id" label="来源 dataSetsId" min-width="120" show-overflow-tooltip />
                    <el-table-column prop="source_item_id" label="来源 dataItemsId" min-width="120" show-overflow-tooltip />
                    <el-table-column prop="scenario_type" label="场景类型" min-width="100" show-overflow-tooltip />
                    <el-table-column prop="sub_scenario_type" label="子场景类型" min-width="100" show-overflow-tooltip />
                    <el-table-column prop="status" label="状态" width="80" show-overflow-tooltip />
                    <el-table-column prop="trace_id" label="traceId" width="120" show-overflow-tooltip />
                    <el-table-column label="场景置信度" width="100"><template #default="s">{{ s.row.scenario_confidence != null ? s.row.scenario_confidence : '-' }}</template></el-table-column>
                    <el-table-column label="AI 评分" width="90"><template #default="s">{{ s.row.ai_score != null ? s.row.ai_score : '-' }}</template></el-table-column>
                    <el-table-column label="人工评分" width="90"><template #default="s">{{ s.row.manual_score != null ? s.row.manual_score : '-' }}</template></el-table-column>
                    <el-table-column label="创建时间" width="160"><template #default="s">{{ formatDateTime(s.row.created_at) }}</template></el-table-column>
                    <el-table-column label="更新时间" width="160"><template #default="s">{{ formatDateTime(s.row.updated_at) }}</template></el-table-column>
                    <el-table-column label="操作" width="140" fixed="right">
                        <template #default="s">
                            <span style="white-space:nowrap;">
                                <el-button link type="primary" size="small" @click="openItemEdit(s.row)" :icon="Edit">编辑</el-button>
                                <el-button link type="danger" size="small" @click="deleteItem(s.row)" :icon="Delete">删除</el-button>
                            </span>
                        </template>
                    </el-table-column>
                </el-table>
            </div>
            <div style="padding:12px 20px;border-top:1px solid #e4e7ed;display:flex;align-items:center;justify-content:space-between;">
                <span style="color:#606266;font-size:13px;">共 {{ itemsTotal }} 条，每页
                    <el-select v-model="limit" size="small" style="width:80px;margin:0 4px;" @change="onSizeChange">
                        <el-option v-for="s in PAGE_SIZE_OPTIONS" :key="s" :label="s" :value="s" />
                    </el-select>条
                </span>
                <el-pagination :current-page="currentPage" :page-size="limit" :total="itemsTotal" layout="prev,pager,next" @current-change="onPageChange" />
            </div>

            <el-dialog v-model="itemDialogVisible" title="编辑改写后数据项" width="640px" :close-on-click-modal="false" :close-on-press-escape="true">
                <el-form :model="itemForm" label-width="120px">
                    <el-form-item label="场景描述"><el-input v-model="itemForm.scenario_description" type="textarea" :rows="2" /></el-form-item>
                    <el-form-item label="改写后的问题"><el-input v-model="itemForm.rewritten_question" type="textarea" :rows="2" /></el-form-item>
                    <el-form-item label="改写后的回答"><el-input v-model="itemForm.rewritten_answer" type="textarea" :rows="2" /></el-form-item>
                    <el-form-item label="改写后的规则"><el-input v-model="itemForm.rewritten_rule" type="textarea" :rows="2" /></el-form-item>
                    <el-form-item label="改写依据"><el-input v-model="itemForm.rewrite_basis" type="textarea" :rows="2" /></el-form-item>
                    <el-form-item label="来源 dataSetsId"><el-input v-model="itemForm.source_dataset_id" /></el-form-item>
                    <el-form-item label="来源 dataItemsId"><el-input v-model="itemForm.source_item_id" /></el-form-item>
                    <el-form-item label="场景类型"><el-input v-model="itemForm.scenario_type" /></el-form-item>
                    <el-form-item label="子场景类型"><el-input v-model="itemForm.sub_scenario_type" /></el-form-item>
                    <el-form-item label="场景置信度"><el-input v-model="itemForm.scenario_confidence" placeholder="0-1" /></el-form-item>
                    <el-form-item label="批次 code"><el-input v-model="itemForm.batch_code" placeholder="批次code" /></el-form-item>
                    <el-form-item label="traceId"><el-input v-model="itemForm.trace_id" placeholder="流程执行 traceId" /></el-form-item>
                    <el-form-item label="执行状态"><el-select v-model="itemForm.status" placeholder="success / failed" clearable style="width:100%;"><el-option label="success" value="success" /><el-option label="failed" value="failed" /></el-select></el-form-item>
                    <el-form-item label="AI 评分"><el-input v-model="itemForm.ai_score" placeholder="数字" /></el-form-item>
                    <el-form-item label="人工评分"><el-input v-model="itemForm.manual_score" placeholder="数字" /></el-form-item>
                </el-form>
                <template #footer><el-button @click="itemDialogVisible=false">取消</el-button><el-button type="primary" @click="submitItemForm">确定</el-button></template>
            </el-dialog>
        </div>
        `
    });
})();
