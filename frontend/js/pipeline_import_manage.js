/**
 * Step00导入管理组件
 * 导入配置 CRUD、新建导入任务占位
 * 设计文档：cursor_docs/020401-数据导入管理模块技术设计.md
 */
(function() {
    'use strict';

    const { defineComponent, ref, reactive, computed, onMounted, watch, nextTick, onBeforeUnmount } = Vue;
    const { ElMessage, ElMessageBox, ElNotification } = ElementPlus;
    const icons = ElementPlusIconsVue;
    const { API_PREFIX, formatDateTime, parseJsonField, getApiErrorMsg, PAGE_SIZE_OPTIONS } = window.PipelineCommon || {};

    window.PipelineImportManageComponent = defineComponent({
        name: 'PipelineImportManageComponent',
        setup() {
            const items = ref([]);
            const total = ref(0);
            const loading = ref(false);
            const queryExpanded = ref(false);
            const queryName = ref('');
            const queryKeyword = ref('');
            const limit = ref(20);
            const offset = ref(0);
            const pageSizeOpts = PAGE_SIZE_OPTIONS || [10, 20, 50, 100];
            const currentPage = computed(() => (limit.value > 0 ? Math.floor(offset.value / limit.value) + 1 : 1));
            const dialogVisible = ref(false);
            const dialogMode = ref('create');
            const editingId = ref(null);
            const form = reactive({ name: '', description: '', import_config: '' });


            function onSearch() {
                offset.value = 0;
                loadList();
            }
            function onResetQuery() {
                queryName.value = '';
                queryKeyword.value = '';
                offset.value = 0;
                loadList();
            }
            function onSizeChange() {
                offset.value = 0;
                loadList();
            }
            async function loadList() {
                loading.value = true;
                try {
                    const params = {
                        name: queryName.value?.trim() || undefined,
                        keyword: queryKeyword.value?.trim() || undefined,
                        limit: limit.value,
                        offset: offset.value
                    };
                    const res = await axios.get(`${API_PREFIX}/import-configs`, { params });
                    items.value = res.data.items || [];
                    total.value = res.data.total ?? 0;
                } catch (err) {
                    ElMessage.error('加载失败: ' + (getApiErrorMsg ? getApiErrorMsg(err) : (err.response?.data?.detail || err.message)));
                    items.value = [];
                    total.value = 0;
                } finally {
                    loading.value = false;
                }
            }

            function openCreate() {
                dialogMode.value = 'create';
                editingId.value = null;
                form.name = '';
                form.description = '';
                form.import_config = '';
                dialogVisible.value = true;
            }

            function openEdit(row) {
                dialogMode.value = 'edit';
                editingId.value = row.id;
                form.name = row.name;
                form.description = row.description || '';
                form.import_config = row.import_config ? JSON.stringify(row.import_config, null, 2) : '';
                dialogVisible.value = true;
            }

            /** 打开复制弹窗：以当前行数据预填新建配置表单，确定时调用新建接口 */
            function openCopy(row) {
                dialogMode.value = 'create';
                editingId.value = null;
                form.name = (row.name || '') + ' 副本';
                form.description = row.description || '';
                form.import_config = row.import_config ? JSON.stringify(row.import_config, null, 2) : '';
                dialogVisible.value = true;
            }

            function parseImportConfig() {
                return parseJsonField(form.import_config, 'import_config 不是合法 JSON');
            }

            async function submitForm() {
                const importConfigObj = parseImportConfig();
                if (importConfigObj === undefined) return;
                try {
                    if (dialogMode.value === 'create') {
                        await axios.post(`${API_PREFIX}/import-configs`, {
                            name: form.name,
                            description: form.description || null,
                            import_config: importConfigObj
                        });
                        ElMessage.success('创建成功');
                    } else {
                        await axios.put(`${API_PREFIX}/import-configs/${editingId.value}`, {
                            name: form.name,
                            description: form.description || null,
                            import_config: importConfigObj
                        });
                        ElMessage.success('更新成功');
                    }
                    dialogVisible.value = false;
                    loadList();
                } catch (err) {
                    ElMessage.error(getApiErrorMsg ? getApiErrorMsg(err) : (err.response?.data?.detail || err.message));
                }
            }

            async function handleDelete(row) {
                try {
                    await ElMessageBox.confirm('确定删除该导入配置？', '提示', { type: 'warning' });
                    await axios.delete(`${API_PREFIX}/import-configs/${row.id}`);
                    ElMessage.success('删除成功');
                    loadList();
                } catch (err) {
                    if (err !== 'cancel') ElMessage.error(getApiErrorMsg(err));
                }
            }

            const executingId = ref(null);

            // JSONEditor 实验弹窗（与表单 JSON 字段联动：打开时加载输入框内容，关闭时回填）
            const jsonEditorTestVisible = ref(false);
            const jsonEditorTestContainer = ref(null);
            const jsonEditorTestData = ref(null);
            const jsonEditorTestFieldKey = ref('import_config');
            let jsonEditorTestInstance = null;

            function openJsonEditorTest(data, fieldKey) {
                jsonEditorTestFieldKey.value = fieldKey || 'import_config';
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
                        form[jsonEditorTestFieldKey.value] = JSON.stringify(json, null, 2);
                    } catch (_) {}
                }
                if (jsonEditorTestInstance) {
                    try { jsonEditorTestInstance.destroy(); } catch (_) {}
                    jsonEditorTestInstance = null;
                }
            }

            watch(jsonEditorTestVisible, async (visible) => {
                if (!visible) {
                    destroyJsonEditorTest(true);
                    return;
                }
                await nextTick();
                if (!jsonEditorTestContainer.value || typeof window.JSONEditor === 'undefined') {
                    if (typeof window.JSONEditor === 'undefined') ElMessage.error('JSONEditor 库未加载');
                    return;
                }
                try {
                    let initialData = jsonEditorTestData.value;
                    if (!initialData || typeof initialData !== 'object') initialData = { _note: '空数据' };
                    jsonEditorTestInstance = new window.JSONEditor(jsonEditorTestContainer.value, {
                        mode: 'tree',
                        modes: ['tree', 'code', 'text'],
                        search: true
                    });
                    jsonEditorTestInstance.set(initialData);
                } catch (e) {
                    ElMessage.error('JSONEditor 初始化失败: ' + (e?.message || e));
                }
            });

            onBeforeUnmount(() => destroyJsonEditorTest(false));

            async function handleExecute(row) {
                try {
                    await ElMessageBox.confirm('确定使用该配置执行导入？', '执行导入', { type: 'info' });
                    executingId.value = row.id;
                    const res = await axios.post(`${API_PREFIX}/import-configs/${row.id}/execute`);
                    const stats = res.data?.stats || {};
                    const msg = `导入完成：成功 ${stats.success ?? 0} 条，失败 ${stats.fail ?? 0} 条，跳过 ${stats.skipped ?? 0} 条`;
                    ElNotification.success({ message: msg, position: 'bottom-left' });
                } catch (err) {
                    if (err !== 'cancel') ElMessage.error(getApiErrorMsg ? getApiErrorMsg(err) : (err.response?.data?.detail || err.message));
                } finally {
                    executingId.value = null;
                }
            }

            function onPageChange(page) {
                offset.value = (page - 1) * limit.value;
                loadList();
            }

            onMounted(() => loadList());

            return {
                items, total, loading, limit, offset, currentPage,
                queryExpanded, queryName, queryKeyword, PAGE_SIZE_OPTIONS: pageSizeOpts,
                dialogVisible, dialogMode, form, executingId,
                jsonEditorTestVisible, jsonEditorTestContainer, openJsonEditorTest,
                formatDateTime: formatDateTime || (s => (s ? new Date(s).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '-')),
                loadList, openCreate, openEdit, openCopy, submitForm, handleDelete, handleExecute,
                onSearch, onResetQuery, onPageChange, onSizeChange,
                Plus: icons.Plus, Edit: icons.Edit, Delete: icons.Delete, Copy: icons.Copy || icons.DocumentCopy, VideoPlay: icons.VideoPlay, Document: icons.Document, Search: icons.Search, ArrowDown: icons.ArrowDown, ArrowUp: icons.ArrowUp
            };
        },
        template: `
        <div style="height:100%;width:100%;min-width:0;display:flex;flex-direction:column;background:#fff;">
            <div style="padding:16px 20px;border-bottom:1px solid #e4e7ed;display:flex;justify-content:space-between;align-items:center;">
                <span style="font-weight:600;">导入配置管理</span>
                <el-button type="primary" @click="openCreate" :icon="Plus">新建配置</el-button>
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
                    <el-input v-model="queryKeyword" placeholder="关键词（name/description/import_config）" clearable style="width:220px;" size="small" />
                </div>
            </div>
            <div style="flex:1;min-width:0;overflow:auto;padding:20px;">
                <el-table :data="items" v-loading="loading" stripe border size="small" style="width:100%">
                    <el-table-column type="expand" width="48">
                        <template #default="props">
                            <div style="padding:12px 24px;background:#fafafa;">
                                <div v-if="props.row.import_config"><strong>import_config：</strong><pre style="margin:4px 0;font-size:12px;white-space:pre-wrap;word-break:break-all;">{{ JSON.stringify(props.row.import_config,null,2) }}</pre></div>
                                <p v-if="!props.row.import_config" style="color:#909399;">无扩展内容</p>
                            </div>
                        </template>
                    </el-table-column>
                    <el-table-column prop="id" label="ID" width="180" show-overflow-tooltip />
                    <el-table-column prop="name" label="名称" min-width="140" />
                    <el-table-column prop="description" label="描述" min-width="160" show-overflow-tooltip />
                    <el-table-column label="创建时间" width="170"><template #default="s">{{ formatDateTime(s.row.created_at) }}</template></el-table-column>
                    <el-table-column label="操作" width="280" fixed="right">
                        <template #default="s">
                            <span style="white-space:nowrap;">
                                <el-button link type="primary" size="small" @click="handleExecute(s.row)" :icon="VideoPlay" :loading="executingId===s.row.id">执行导入</el-button>
                                <el-button link type="primary" size="small" @click="openCopy(s.row)" :icon="Copy">复制</el-button>
                                <el-button link type="primary" size="small" @click="openEdit(s.row)" :icon="Edit">编辑</el-button>
                                <el-button link type="danger" size="small" @click="handleDelete(s.row)" :icon="Delete">删除</el-button>
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
                <el-pagination :current-page="currentPage" :page-size="limit" :total="total" layout="prev,pager,next" @current-change="onPageChange" />
            </div>

            <el-dialog v-model="dialogVisible" :title="dialogMode==='create'?'新建导入配置':'编辑导入配置'" width="500px" :close-on-click-modal="false" :close-on-press-escape="true" @close="dialogVisible=false">
                <el-form :model="form" label-width="80px">
                    <el-form-item label="名称" required><el-input v-model="form.name" placeholder="配置名称" /></el-form-item>
                    <el-form-item label="描述"><el-input v-model="form.description" type="textarea" placeholder="描述" :rows="2" /></el-form-item>
                    <el-form-item label="配置(JSON)">
                        <div style="display:flex;align-items:flex-start;gap:8px;width:100%;">
                            <el-input v-model="form.import_config" type="textarea" placeholder='{"type":"feishu_excel",...}' :rows="4" style="flex:1;" />
                            <el-button size="small" @click="openJsonEditorTest(form.import_config, 'import_config')" :icon="Document" title="JSONEditor 实验弹窗">JSONEditor</el-button>
                        </div>
                    </el-form-item>
                </el-form>
                <template #footer><el-button @click="dialogVisible=false">取消</el-button><el-button type="primary" @click="submitForm">确定</el-button></template>
            </el-dialog>

            <!-- JSONEditor 实验弹窗（实验性质，仅用于测试 JSONEditor 在 Dialog 内的展示效果） -->
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
