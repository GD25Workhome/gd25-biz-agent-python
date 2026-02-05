/**
 * 数据集数据项管理组件
 * 独立 Tab 页，管理指定数据集下的所有数据项
 * 设计文档：cursor_docs/020401-数据导入管理模块技术设计.md
 */
(function() {
    'use strict';

    const { defineComponent, ref, reactive, computed, watch, nextTick, onBeforeUnmount } = Vue;
    const { ElMessage, ElMessageBox, ElNotification } = ElementPlus;
    const icons = ElementPlusIconsVue;
    const { API_PREFIX, parseJsonField, getApiErrorMsg, PAGE_SIZE_OPTIONS } = window.PipelineCommon || {};

    window.PipelineDatasetItemsComponent = defineComponent({
        name: 'PipelineDatasetItemsComponent',
        props: {
            datasetId: { type: String, required: true },
            datasetName: { type: String, default: '' }
        },
        setup(props) {
            const items = ref([]);
            const itemsTotal = ref(0);
            const itemsLoading = ref(false);
            const itemDialogVisible = ref(false);
            const itemDialogMode = ref('create');
            const itemForm = reactive({ unique_key: '', input: '', output: '', metadata: '', status: 1, source: '' });
            const itemEditingId = ref(null);
            const queryExpanded = ref(false);
            const queryUniqueKey = ref('');
            const querySource = ref('');
            const queryStatus = ref('');
            const queryKeyword = ref('');
            const limit = ref(20);
            const offset = ref(0);
            const pageSizeOpts = PAGE_SIZE_OPTIONS || [10, 20, 50, 100];
            const currentPage = computed(() => (limit.value > 0 ? Math.floor(offset.value / limit.value) + 1 : 1));

            function parseJson(val) {
                return parseJsonField ? parseJsonField(val) : (() => {
                    if (!val || String(val).trim() === '') return null;
                    try { return JSON.parse(val); } catch { ElMessage.warning('JSON 格式错误'); return undefined; }
                })();
            }

            function onSearch() {
                offset.value = 0;
                loadItems();
            }
            function onResetQuery() {
                queryUniqueKey.value = '';
                querySource.value = '';
                queryStatus.value = '';
                queryKeyword.value = '';
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
                if (!props.datasetId) return;
                itemsLoading.value = true;
                try {
                    const params = {
                        unique_key: queryUniqueKey.value?.trim() || undefined,
                        source: querySource.value?.trim() || undefined,
                        status: (queryStatus.value === 0 || queryStatus.value === 1) ? queryStatus.value : undefined,
                        keyword: queryKeyword.value?.trim() || undefined,
                        limit: limit.value,
                        offset: offset.value
                    };
                    const res = await axios.get(`${API_PREFIX}/datasets/${props.datasetId}/items`, { params });
                    items.value = res.data.items || [];
                    itemsTotal.value = res.data.total ?? 0;
                } catch (err) {
                    ElMessage.error('加载数据项失败: ' + (getApiErrorMsg ? getApiErrorMsg(err) : (err.response?.data?.detail || err.message)));
                    items.value = [];
                    itemsTotal.value = 0;
                } finally {
                    itemsLoading.value = false;
                }
            }

            function openItemCreate() {
                itemDialogMode.value = 'create';
                itemForm.unique_key = '';
                itemForm.input = '';
                itemForm.output = '';
                itemForm.metadata = '';
                itemForm.status = 1;
                itemForm.source = '';
                itemEditingId.value = null;
                itemDialogVisible.value = true;
            }

            function openItemEdit(row) {
                itemDialogMode.value = 'edit';
                itemForm.unique_key = row.unique_key || '';
                itemForm.input = row.input ? JSON.stringify(row.input, null, 2) : '';
                itemForm.output = row.output ? JSON.stringify(row.output, null, 2) : '';
                itemForm.metadata = row.metadata ? JSON.stringify(row.metadata, null, 2) : '';
                itemForm.status = row.status;
                itemForm.source = row.source || '';
                itemEditingId.value = row.id;
                itemDialogVisible.value = true;
            }

            async function submitItemForm() {
                const inputObj = parseJson(itemForm.input);
                const outputObj = parseJson(itemForm.output);
                const metaObj = parseJson(itemForm.metadata);
                if (inputObj === undefined || outputObj === undefined || metaObj === undefined) return;
                try {
                    const payload = {
                        unique_key: itemForm.unique_key || null,
                        input: inputObj,
                        output: outputObj,
                        metadata: metaObj,
                        status: itemForm.status,
                        source: itemForm.source || null
                    };
                    if (itemDialogMode.value === 'create') {
                        await axios.post(`${API_PREFIX}/datasets/${props.datasetId}/items`, payload);
                        ElMessage.success('创建成功');
                    } else {
                        await axios.put(`${API_PREFIX}/datasets/${props.datasetId}/items/${itemEditingId.value}`, payload);
                        ElMessage.success('更新成功');
                    }
                    itemDialogVisible.value = false;
                    loadItems();
                } catch (err) {
                    ElMessage.error(getApiErrorMsg ? getApiErrorMsg(err) : (err.response?.data?.detail || err.message));
                }
            }

            async function deleteItem(row) {
                try {
                    await ElMessageBox.confirm('确定删除该数据项？', '提示', { type: 'warning' });
                    await axios.delete(`${API_PREFIX}/datasets/${props.datasetId}/items/${row.id}`);
                    ElMessage.success('删除成功');
                    loadItems();
                } catch (err) {
                    if (err !== 'cancel') ElMessage.error(getApiErrorMsg ? getApiErrorMsg(err) : (err.response?.data?.detail || err.message));
                }
            }

            async function clearAllItems() {
                try {
                    await ElMessageBox.confirm('确定清空该数据集下所有数据项？此操作不可恢复。', '提示', { type: 'warning' });
                    const res = await axios.delete(`${API_PREFIX}/datasets/${props.datasetId}/items`);
                    const cnt = res.data?.deleted_count ?? 0;
                    ElNotification.success({ message: '已清空 ' + cnt + ' 条数据', position: 'bottom-left' });
                    loadItems();
                } catch (err) {
                    if (err !== 'cancel') ElMessage.error(getApiErrorMsg ? getApiErrorMsg(err) : (err.response?.data?.detail || err.message));
                }
            }

            async function toggleItemStatus(row) {
                const newStatus = row.status === 1 ? 0 : 1;
                try {
                    await axios.put(`${API_PREFIX}/datasets/${props.datasetId}/items/${row.id}`, { status: newStatus });
                    ElMessage.success(newStatus === 1 ? '已激活' : '已废弃');
                    loadItems();
                } catch (err) {
                    ElMessage.error(getApiErrorMsg ? getApiErrorMsg(err) : (err.response?.data?.detail || err.message));
                }
            }

            // JSONEditor 实验弹窗（与表单 JSON 字段联动：打开时加载输入框内容，关闭时回填）
            const jsonEditorTestVisible = ref(false);
            const jsonEditorTestContainer = ref(null);
            const jsonEditorTestData = ref(null);
            const jsonEditorTestFieldKey = ref('');
            let jsonEditorTestInstance = null;

            function openJsonEditorTest(data, fieldKey) {
                jsonEditorTestFieldKey.value = fieldKey || '';
                try {
                    jsonEditorTestData.value = (data != null && typeof data === 'object') ? data : (typeof data === 'string' && data.trim() ? JSON.parse(data) : {});
                } catch (_) {
                    jsonEditorTestData.value = { _raw: String(data), _note: '解析失败' };
                }
                jsonEditorTestVisible.value = true;
            }

            function destroyJsonEditorTest(writeBack) {
                if (jsonEditorTestInstance && writeBack && jsonEditorTestFieldKey.value) {
                    try {
                        const json = jsonEditorTestInstance.get();
                        itemForm[jsonEditorTestFieldKey.value] = JSON.stringify(json, null, 2);
                    } catch (_) {}
                }
                if (jsonEditorTestInstance) {
                    try { jsonEditorTestInstance.destroy(); } catch (_) {}
                    jsonEditorTestInstance = null;
                }
            }

            watch(jsonEditorTestVisible, async (visible) => {
                if (!visible) { destroyJsonEditorTest(true); return; }
                await nextTick();
                if (!jsonEditorTestContainer.value || typeof window.JSONEditor === 'undefined') {
                    if (typeof window.JSONEditor === 'undefined') ElMessage.error('JSONEditor 库未加载');
                    return;
                }
                try {
                    let initialData = jsonEditorTestData.value;
                    if (!initialData || typeof initialData !== 'object') initialData = { _note: '空数据' };
                    jsonEditorTestInstance = new window.JSONEditor(jsonEditorTestContainer.value, {
                        mode: 'tree', modes: ['tree', 'code', 'text'], search: true
                    });
                    jsonEditorTestInstance.set(initialData);
                } catch (e) {
                    ElMessage.error('JSONEditor 初始化失败: ' + (e?.message || e));
                }
            });

            onBeforeUnmount(() => destroyJsonEditorTest(false));

            watch(() => props.datasetId, () => { offset.value = 0; loadItems(); }, { immediate: true });

            return {
                items, itemsTotal, itemsLoading,
                queryExpanded, queryUniqueKey, querySource, queryStatus, queryKeyword,
                limit, offset, currentPage, PAGE_SIZE_OPTIONS: pageSizeOpts,
                itemDialogVisible, itemDialogMode, itemForm, itemEditingId,
                jsonEditorTestVisible, jsonEditorTestContainer, openJsonEditorTest,
                loadItems, openItemCreate, openItemEdit, submitItemForm, deleteItem, clearAllItems, toggleItemStatus,
                onSearch, onResetQuery, onPageChange, onSizeChange,
                Plus: icons.Plus, Edit: icons.Edit, Delete: icons.Delete, Document: icons.Document, Search: icons.Search, ArrowDown: icons.ArrowDown, ArrowUp: icons.ArrowUp
            };
        },
        template: `
        <div style="height:100%;width:100%;min-width:0;display:flex;flex-direction:column;background:#fff;">
            <div style="padding:12px 20px;border-bottom:1px solid #e4e7ed;display:flex;justify-content:space-between;align-items:center;">
                <div style="display:flex;align-items:baseline;gap:6px;">
                    <span style="font-weight:600;">{{ datasetName || '数据项' }}</span><span v-if="datasetId" style="font-size:12px;color:#909399;">ID: {{ datasetId }}</span>
                </div>
                <div style="display:flex;gap:8px;">
                    <el-button size="small" type="primary" @click="openItemCreate" :icon="Plus">新建数据项</el-button>
                    <el-button size="small" type="danger" plain @click="clearAllItems" :icon="Delete" :disabled="itemsTotal===0">清理所有数据</el-button>
                </div>
            </div>
            <div style="border-bottom:1px solid #e4e7ed;">
                <div style="padding:8px 12px;display:flex;align-items:center;gap:8px;cursor:pointer;" @click="queryExpanded=!queryExpanded">
                    <el-icon><component :is="queryExpanded?'ArrowUp':'ArrowDown'" /></el-icon>
                    <span style="font-size:13px;color:#606266;">查询条件</span>
                    <el-button size="small" type="primary" @click.stop="onSearch" :icon="Search">查询</el-button>
                    <el-button size="small" @click.stop="onResetQuery">重置</el-button>
                </div>
                <div v-show="queryExpanded" style="padding:0 12px 12px;display:flex;flex-wrap:wrap;gap:12px;align-items:center;">
                    <el-input v-model="queryUniqueKey" placeholder="unique_key（包含）" clearable style="width:140px;" size="small" />
                    <el-input v-model="querySource" placeholder="source（包含）" clearable style="width:140px;" size="small" />
                    <el-select v-model="queryStatus" placeholder="状态" clearable style="width:100px;" size="small">
                        <el-option label="激活" :value="1" />
                        <el-option label="废弃" :value="0" />
                    </el-select>
                    <el-input v-model="queryKeyword" placeholder="关键词（input/output/metadata）" clearable style="width:200px;" size="small" />
                </div>
            </div>
            <div style="flex:1;min-width:0;overflow:auto;padding:12px;">
                <el-table :data="items" v-loading="itemsLoading" stripe border size="small" style="width:100%">
                    <el-table-column type="expand" width="48">
                        <template #default="props">
                            <div style="padding:12px 24px;background:#fafafa;">
                                <div v-if="props.row.input"><strong>input：</strong><pre style="margin:4px 0;font-size:12px;white-space:pre-wrap;word-break:break-all;">{{ JSON.stringify(props.row.input,null,2) }}</pre></div>
                                <div v-if="props.row.output"><strong>output：</strong><pre style="margin:4px 0;font-size:12px;white-space:pre-wrap;word-break:break-all;">{{ JSON.stringify(props.row.output,null,2) }}</pre></div>
                                <div v-if="props.row.metadata"><strong>metadata：</strong><pre style="margin:4px 0;font-size:12px;white-space:pre-wrap;word-break:break-all;">{{ JSON.stringify(props.row.metadata,null,2) }}</pre></div>
                                <p v-if="!props.row.input&&!props.row.output&&!props.row.metadata" style="color:#909399;">无扩展内容</p>
                            </div>
                        </template>
                    </el-table-column>
                    <el-table-column prop="id" label="ID" width="180" show-overflow-tooltip />
                    <el-table-column prop="unique_key" label="unique_key" min-width="120" show-overflow-tooltip />
                    <el-table-column prop="source" label="source" min-width="120" show-overflow-tooltip />
                    <el-table-column prop="status" label="状态" width="80"><template #default="s"><el-tag :type="s.row.status===1?'success':'info'" size="small">{{ s.row.status===1?'激活':'废弃' }}</el-tag></template></el-table-column>
                    <el-table-column label="操作" width="200" fixed="right">
                        <template #default="s">
                            <span style="white-space:nowrap;">
                                <el-button link type="primary" size="small" @click="toggleItemStatus(s.row)">{{ s.row.status===1?'废弃':'激活' }}</el-button>
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

            <el-dialog v-model="itemDialogVisible" :title="itemDialogMode==='create'?'新建数据项':'编辑数据项'" width="520px" :close-on-click-modal="false" :close-on-press-escape="true">
                <el-form :model="itemForm" label-width="100px">
                    <el-form-item label="unique_key"><el-input v-model="itemForm.unique_key" /></el-form-item>
                    <el-form-item label="input">
                        <div style="display:flex;align-items:flex-start;gap:8px;width:100%;">
                            <el-input v-model="itemForm.input" type="textarea" placeholder="JSON" :rows="3" style="flex:1;" />
                            <el-button size="small" @click="openJsonEditorTest(itemForm.input, 'input')" :icon="Document" title="JSONEditor 实验弹窗">JSONEditor</el-button>
                        </div>
                    </el-form-item>
                    <el-form-item label="output">
                        <div style="display:flex;align-items:flex-start;gap:8px;width:100%;">
                            <el-input v-model="itemForm.output" type="textarea" placeholder="JSON" :rows="3" style="flex:1;" />
                            <el-button size="small" @click="openJsonEditorTest(itemForm.output, 'output')" :icon="Document" title="JSONEditor 实验弹窗">JSONEditor</el-button>
                        </div>
                    </el-form-item>
                    <el-form-item label="metadata">
                        <div style="display:flex;align-items:flex-start;gap:8px;width:100%;">
                            <el-input v-model="itemForm.metadata" type="textarea" placeholder="JSON" :rows="2" style="flex:1;" />
                            <el-button size="small" @click="openJsonEditorTest(itemForm.metadata, 'metadata')" :icon="Document" title="JSONEditor 实验弹窗">JSONEditor</el-button>
                        </div>
                    </el-form-item>
                    <el-form-item label="status"><el-radio-group v-model="itemForm.status"><el-radio :label="1">激活</el-radio><el-radio :label="0">废弃</el-radio></el-radio-group></el-form-item>
                    <el-form-item label="source"><el-input v-model="itemForm.source" /></el-form-item>
                </el-form>
                <template #footer><el-button @click="itemDialogVisible=false">取消</el-button><el-button type="primary" @click="submitItemForm">确定</el-button></template>
            </el-dialog>

            <el-dialog v-model="jsonEditorTestVisible" title="JSONEditor 实验弹窗" width="85%" class="pipeline-json-editor-dialog" :close-on-click-modal="false" :close-on-press-escape="true" @close="jsonEditorTestVisible=false">
                <div class="pipeline-json-editor-test-wrap" style="min-height:400px;">
                    <div ref="jsonEditorTestContainer" style="width:100%;height:450px;min-height:400px;"></div>
                </div>
                <template #footer><el-button @click="jsonEditorTestVisible=false">关闭</el-button></template>
            </el-dialog>
        </div>
        `
    });
})();
