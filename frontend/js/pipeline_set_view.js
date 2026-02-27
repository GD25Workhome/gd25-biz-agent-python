/**
 * Step01原始数据管理组件
 * dataSetsPath 树、dataSets 列表；数据项通过「数据项」按钮在独立 Tab 中管理
 * 设计文档：cursor_docs/020401-数据导入管理模块技术设计.md
 */
(function() {
    'use strict';

    const { defineComponent, ref, reactive, computed, onMounted, watch, inject, nextTick, onBeforeUnmount } = Vue;
    const { ElMessage, ElMessageBox } = ElementPlus;
    const icons = ElementPlusIconsVue;
    const { API_PREFIX, formatDateTime, parseJsonField, getApiErrorMsg, PAGE_SIZE_OPTIONS } = window.PipelineCommon || {};

    window.PipelineSetViewComponent = defineComponent({
        name: 'PipelineSetViewComponent',
        setup() {
            const { openTabForDatasetItems } = inject('pipelineTabManager', { openTabForDatasetItems: () => {} });

            const pathTree = ref([]);
            const pathTreeLoading = ref(false);
            const selectedPathId = ref(null);
            const datasets = ref([]);
            const datasetsTotal = ref(0);
            const datasetsLoading = ref(false);
            const queryExpanded = ref(false);
            const queryName = ref('');
            const queryKeyword = ref('');
            const limit = ref(20);
            const offset = ref(0);
            const pageSizeOpts = PAGE_SIZE_OPTIONS || [10, 20, 50, 100];
            const currentPage = computed(() => (limit.value > 0 ? Math.floor(offset.value / limit.value) + 1 : 1));

            const pathDialogVisible = ref(false);
            const pathDialogMode = ref('create');
            const pathForm = reactive({ id: '', id_path: '', name: '', description: '' });
            const pathFormParentId = ref(null);

            const datasetDialogVisible = ref(false);
            const datasetDialogMode = ref('create');
            const datasetForm = reactive({ name: '', path_id: '', input_schema: '', output_schema: '', metadata: '' });
            const datasetEditingId = ref(null);

            const fmtDateTime = formatDateTime || (s => (s ? new Date(s).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '-'));

            function onSearch() {
                offset.value = 0;
                loadDatasets();
            }
            function onResetQuery() {
                queryName.value = '';
                queryKeyword.value = '';
                offset.value = 0;
                loadDatasets();
            }
            function onPageChange(page) {
                offset.value = (page - 1) * limit.value;
                loadDatasets();
            }
            function onSizeChange() {
                offset.value = 0;
                loadDatasets();
            }

            async function loadPathTree() {
                pathTreeLoading.value = true;
                try {
                    const res = await axios.get(`${API_PREFIX}/paths/tree`);
                    pathTree.value = res.data || [];
                } catch (err) {
                    ElMessage.error('加载路径树失败: ' + (getApiErrorMsg ? getApiErrorMsg(err) : (err.response?.data?.detail || err.message)));
                    pathTree.value = [];
                } finally {
                    pathTreeLoading.value = false;
                }
            }

            async function loadDatasets() {
                datasetsLoading.value = true;
                try {
                    const params = {
                        path_id: selectedPathId.value || undefined,
                        name: queryName.value?.trim() || undefined,
                        keyword: queryKeyword.value?.trim() || undefined,
                        limit: limit.value,
                        offset: offset.value
                    };
                    const res = await axios.get(`${API_PREFIX}/datasets`, { params });
                    datasets.value = res.data.items || [];
                    datasetsTotal.value = res.data.total ?? 0;
                } catch (err) {
                    ElMessage.error('加载数据集失败: ' + (getApiErrorMsg ? getApiErrorMsg(err) : (err.response?.data?.detail || err.message)));
                    datasets.value = [];
                    datasetsTotal.value = 0;
                } finally {
                    datasetsLoading.value = false;
                }
            }

            function onPathSelect(node) {
                selectedPathId.value = node ? node.id : null;
                loadDatasets();
            }

            watch(selectedPathId, () => { offset.value = 0; loadDatasets(); });

            function openPathCreate(parentNode) {
                pathDialogMode.value = 'create';
                pathForm.id = '';
                pathForm.id_path = parentNode ? parentNode.id : '';
                pathForm.name = '';
                pathForm.description = '';
                pathFormParentId.value = parentNode ? parentNode.id : null;
                pathDialogVisible.value = true;
            }

            function openPathEdit(nodeData) {
                pathDialogMode.value = 'edit';
                pathForm.id = nodeData.id;
                pathForm.id_path = nodeData.id_path || '';
                pathForm.name = nodeData.name;
                pathForm.description = nodeData.description || '';
                pathFormParentId.value = null;
                pathDialogVisible.value = true;
            }

            async function submitPathForm() {
                if (!pathForm.id && pathDialogMode.value === 'create') {
                    pathForm.id = 'path_' + Date.now();
                }
                if (!pathForm.name?.trim()) { ElMessage.warning('请输入名称'); return; }
                try {
                    if (pathDialogMode.value === 'create') {
                        await axios.post(`${API_PREFIX}/paths`, {
                            id: pathForm.id || 'path_' + Date.now(),
                            id_path: pathForm.id_path || null,
                            name: pathForm.name.trim(),
                            description: pathForm.description || null
                        });
                        ElMessage.success('创建成功');
                    } else {
                        await axios.put(`${API_PREFIX}/paths/${pathForm.id}`, {
                            id_path: pathForm.id_path || null,
                            name: pathForm.name.trim(),
                            description: pathForm.description || null
                        });
                        ElMessage.success('更新成功');
                    }
                    pathDialogVisible.value = false;
                    loadPathTree();
                    loadDatasets();
                } catch (err) {
                    ElMessage.error(getApiErrorMsg ? getApiErrorMsg(err) : (err.response?.data?.detail || err.message));
                }
            }

            function openDatasetCreate() {
                datasetDialogMode.value = 'create';
                datasetForm.name = '';
                datasetForm.path_id = selectedPathId.value || '';
                datasetForm.input_schema = '';
                datasetForm.output_schema = '';
                datasetForm.metadata = '';
                datasetEditingId.value = null;
                datasetDialogVisible.value = true;
            }

            function openDatasetEdit(row) {
                datasetDialogMode.value = 'edit';
                datasetForm.name = row.name;
                datasetForm.path_id = row.path_id || '';
                datasetForm.input_schema = row.input_schema ? JSON.stringify(row.input_schema, null, 2) : '';
                datasetForm.output_schema = row.output_schema ? JSON.stringify(row.output_schema, null, 2) : '';
                datasetForm.metadata = row.metadata ? JSON.stringify(row.metadata, null, 2) : '';
                datasetEditingId.value = row.id;
                datasetDialogVisible.value = true;
            }

            function parseJson(val) {
                return parseJsonField ? parseJsonField(val) : (() => {
                    if (!val || String(val).trim() === '') return null;
                    try { return JSON.parse(val); } catch { ElMessage.warning('JSON 格式错误'); return undefined; }
                })();
            }

            async function submitDatasetForm() {
                if (!datasetForm.name?.trim()) { ElMessage.warning('请输入名称'); return; }
                const inputSchema = parseJson(datasetForm.input_schema);
                const outputSchema = parseJson(datasetForm.output_schema);
                const metadata = parseJson(datasetForm.metadata);
                if (inputSchema === undefined || outputSchema === undefined || metadata === undefined) return;
                try {
                    if (datasetDialogMode.value === 'create') {
                        await axios.post(`${API_PREFIX}/datasets`, {
                            name: datasetForm.name.trim(),
                            path_id: datasetForm.path_id || null,
                            input_schema: inputSchema,
                            output_schema: outputSchema,
                            metadata: metadata
                        });
                        ElMessage.success('创建成功');
                    } else {
                        await axios.put(`${API_PREFIX}/datasets/${datasetEditingId.value}`, {
                            name: datasetForm.name.trim(),
                            path_id: datasetForm.path_id || null,
                            input_schema: inputSchema,
                            output_schema: outputSchema,
                            metadata: metadata
                        });
                        ElMessage.success('更新成功');
                    }
                    datasetDialogVisible.value = false;
                    loadDatasets();
                } catch (err) {
                    ElMessage.error(getApiErrorMsg ? getApiErrorMsg(err) : (err.response?.data?.detail || err.message));
                }
            }

            async function deleteDataset(row) {
                try {
                    await ElMessageBox.confirm('确定删除该数据集？将级联删除其下所有数据项。', '提示', { type: 'warning' });
                    await axios.delete(`${API_PREFIX}/datasets/${row.id}`);
                    ElMessage.success('删除成功');
                    loadDatasets();
                } catch (err) {
                    if (err !== 'cancel') ElMessage.error(getApiErrorMsg ? getApiErrorMsg(err) : (err.response?.data?.detail || err.message));
                }
            }

            function openDatasetItems(row) {
                openTabForDatasetItems(row.id, row.name);
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
                        datasetForm[jsonEditorTestFieldKey.value] = JSON.stringify(json, null, 2);
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

            onMounted(() => {
                loadPathTree();
            });

            return {
                pathTree, pathTreeLoading, selectedPathId, datasets, datasetsTotal, datasetsLoading,
                queryExpanded, queryName, queryKeyword, limit, offset, currentPage, PAGE_SIZE_OPTIONS: pageSizeOpts,
                pathDialogVisible, pathDialogMode, pathForm, pathFormParentId,
                datasetDialogVisible, datasetDialogMode, datasetForm, datasetEditingId,
                jsonEditorTestVisible, jsonEditorTestContainer, openJsonEditorTest,
                formatDateTime: fmtDateTime,
                loadPathTree, loadDatasets, onSearch, onResetQuery, onPageChange, onSizeChange,
                onPathSelect,
                openPathCreate, openPathEdit, submitPathForm,
                openDatasetCreate, openDatasetEdit, submitDatasetForm, deleteDataset, openDatasetItems,
                Plus: icons.Plus, Edit: icons.Edit, Delete: icons.Delete, Document: icons.Document, Search: icons.Search, Refresh: icons.Refresh, ArrowDown: icons.ArrowDown, ArrowUp: icons.ArrowUp
            };
        },
        template: `
        <div style="height:100%;width:100%;min-width:0;display:flex;background:#fff;">
            <div style="width:260px;border-right:1px solid #e4e7ed;display:flex;flex-direction:column;">
                <div style="padding:12px;border-bottom:1px solid #e4e7ed;display:flex;justify-content:space-between;align-items:center;">
                    <span style="font-weight:600;">文件夹</span>
                    <el-button size="small" type="primary" @click="openPathCreate(null)" :icon="Plus">新建</el-button>
                </div>
                <div style="flex:1;overflow:auto;padding:8px;" v-loading="pathTreeLoading">
                    <el-tree :data="pathTree" :props="{label:'name',children:'children'}" node-key="id" highlight-current :current-node-key="selectedPathId" @node-click="(n)=>onPathSelect(n)" default-expand-all>
                        <template #default="{node,data}">
                            <span style="flex:1">{{ node.label }}</span>
                            <el-button link size="small" type="primary" @click.stop="openPathCreate(data)" :icon="Plus" style="margin-left:2px;" />
                            <el-button link size="small" @click.stop="openPathEdit(data)" :icon="Edit" style="margin-left:2px;" />
                        </template>
                    </el-tree>
                </div>
            </div>
            <div style="flex:1;min-width:0;display:flex;flex-direction:column;overflow:hidden;">
                <div style="padding:12px;border-bottom:1px solid #e4e7ed;display:flex;justify-content:space-between;align-items:center;">
                    <span style="font-weight:600;">数据集</span>
                    <el-button size="small" type="primary" @click="openDatasetCreate" :icon="Plus">新建</el-button>
                </div>
                <div style="border-bottom:1px solid #e4e7ed;">
                    <div style="padding:8px 12px;display:flex;align-items:center;gap:8px;cursor:pointer;" @click="queryExpanded=!queryExpanded">
                        <el-icon><component :is="queryExpanded?'ArrowUp':'ArrowDown'" /></el-icon>
                        <span style="font-size:13px;color:#606266;">查询条件</span>
                        <el-button size="small" type="primary" @click.stop="onSearch" :icon="Search">查询</el-button>
                        <el-button size="small" @click.stop="onResetQuery">重置</el-button>
                    </div>
                    <div v-show="queryExpanded" style="padding:0 12px 12px;display:flex;flex-wrap:wrap;gap:12px;align-items:center;">
                        <el-input v-model="queryName" placeholder="名称（包含）" clearable style="width:160px;" size="small" />
                        <el-input v-model="queryKeyword" placeholder="关键词（input_schema/output_schema/metadata）" clearable style="width:220px;" size="small" />
                    </div>
                </div>
                <div style="flex:1;min-width:0;overflow:auto;padding:12px;">
                    <el-table :data="datasets" v-loading="datasetsLoading" stripe border size="small" style="width:100%">
                        <el-table-column type="expand" width="48">
                            <template #default="props">
                                <div style="padding:12px 24px;background:#fafafa;">
                                    <div v-if="props.row.input_schema"><strong>input_schema：</strong><pre style="margin:4px 0;font-size:12px;white-space:pre-wrap;word-break:break-all;">{{ JSON.stringify(props.row.input_schema,null,2) }}</pre></div>
                                    <div v-if="props.row.output_schema"><strong>output_schema：</strong><pre style="margin:4px 0;font-size:12px;white-space:pre-wrap;word-break:break-all;">{{ JSON.stringify(props.row.output_schema,null,2) }}</pre></div>
                                    <div v-if="props.row.metadata"><strong>metadata：</strong><pre style="margin:4px 0;font-size:12px;white-space:pre-wrap;word-break:break-all;">{{ JSON.stringify(props.row.metadata,null,2) }}</pre></div>
                                    <p v-if="!props.row.input_schema&&!props.row.output_schema&&!props.row.metadata" style="color:#909399;">无扩展内容</p>
                                </div>
                            </template>
                        </el-table-column>
                        <el-table-column prop="id" label="ID" width="180" show-overflow-tooltip />
                        <el-table-column prop="name" label="名称" min-width="120" />
                        <el-table-column label="创建时间" width="160"><template #default="s">{{ formatDateTime(s.row.created_at) }}</template></el-table-column>
                        <el-table-column label="操作" width="200" fixed="right">
                            <template #default="s">
                                <span style="white-space:nowrap;">
                                    <el-button link type="primary" size="small" @click="openDatasetItems(s.row)" :icon="Document">数据项</el-button>
                                    <el-button link type="primary" size="small" @click="openDatasetEdit(s.row)" :icon="Edit">编辑</el-button>
                                    <el-button link type="danger" size="small" @click="deleteDataset(s.row)" :icon="Delete">删除</el-button>
                                </span>
                            </template>
                        </el-table-column>
                    </el-table>
                </div>
                <div style="padding:12px 20px;border-top:1px solid #e4e7ed;display:flex;align-items:center;justify-content:space-between;">
                    <span style="color:#606266;font-size:13px;">共 {{ datasetsTotal }} 条，每页
                        <el-select v-model="limit" size="small" style="width:80px;margin:0 4px;" @change="onSizeChange">
                            <el-option v-for="s in PAGE_SIZE_OPTIONS" :key="s" :label="s" :value="s" />
                        </el-select>条
                    </span>
                    <el-pagination :current-page="currentPage" :page-size="limit" :total="datasetsTotal" layout="prev,pager,next" @current-change="onPageChange" />
                </div>
            </div>

            <el-dialog v-model="pathDialogVisible" title="路径" width="420px" :close-on-click-modal="false" :close-on-press-escape="true">
                <el-form :model="pathForm" label-width="80px">
                    <el-form-item label="ID" v-if="pathDialogMode==='create'"><el-input v-model="pathForm.id" placeholder="留空自动生成" /></el-form-item>
                    <el-form-item label="上级路径"><el-input v-model="pathForm.id_path" placeholder="根节点留空" /></el-form-item>
                    <el-form-item label="名称" required><el-input v-model="pathForm.name" /></el-form-item>
                    <el-form-item label="描述"><el-input v-model="pathForm.description" type="textarea" :rows="2" /></el-form-item>
                </el-form>
                <template #footer><el-button @click="pathDialogVisible=false">取消</el-button><el-button type="primary" @click="submitPathForm">确定</el-button></template>
            </el-dialog>

            <el-dialog v-model="datasetDialogVisible" :title="datasetDialogMode==='create'?'新建数据集':'编辑数据集'" width="500px" :close-on-click-modal="false" :close-on-press-escape="true">
                <el-form :model="datasetForm" label-width="100px">
                    <el-form-item label="名称" required><el-input v-model="datasetForm.name" /></el-form-item>
                    <el-form-item label="路径ID"><el-input v-model="datasetForm.path_id" placeholder="关联的 path id" /></el-form-item>
                    <el-form-item label="input_schema">
                        <div style="display:flex;align-items:flex-start;gap:8px;width:100%;">
                            <el-input v-model="datasetForm.input_schema" type="textarea" placeholder="JSON" :rows="2" style="flex:1;" />
                            <el-button size="small" @click="openJsonEditorTest(datasetForm.input_schema, 'input_schema')" :icon="Document" title="JSONEditor 实验弹窗">JSONEditor</el-button>
                        </div>
                    </el-form-item>
                    <el-form-item label="output_schema">
                        <div style="display:flex;align-items:flex-start;gap:8px;width:100%;">
                            <el-input v-model="datasetForm.output_schema" type="textarea" placeholder="JSON" :rows="2" style="flex:1;" />
                            <el-button size="small" @click="openJsonEditorTest(datasetForm.output_schema, 'output_schema')" :icon="Document" title="JSONEditor 实验弹窗">JSONEditor</el-button>
                        </div>
                    </el-form-item>
                    <el-form-item label="metadata">
                        <div style="display:flex;align-items:flex-start;gap:8px;width:100%;">
                            <el-input v-model="datasetForm.metadata" type="textarea" placeholder="JSON" :rows="2" style="flex:1;" />
                            <el-button size="small" @click="openJsonEditorTest(datasetForm.metadata, 'metadata')" :icon="Document" title="JSONEditor 实验弹窗">JSONEditor</el-button>
                        </div>
                    </el-form-item>
                </el-form>
                <template #footer><el-button @click="datasetDialogVisible=false">取消</el-button><el-button type="primary" @click="submitDatasetForm">确定</el-button></template>
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
