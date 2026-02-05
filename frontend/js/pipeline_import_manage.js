/**
 * Step00导入管理组件
 * 导入配置 CRUD、新建导入任务占位
 * 设计文档：cursor_docs/020401-数据导入管理模块技术设计.md
 */
(function() {
    'use strict';

    const { defineComponent, ref, reactive, computed, onMounted } = Vue;
    const { ElMessage, ElMessageBox } = ElementPlus;
    const icons = ElementPlusIconsVue;
    const { API_PREFIX, formatDateTime, parseJsonField, getApiErrorMsg } = window.PipelineCommon || {};

    window.PipelineImportManageComponent = defineComponent({
        name: 'PipelineImportManageComponent',
        setup() {
            const items = ref([]);
            const total = ref(0);
            const loading = ref(false);
            const limit = ref(20);
            const offset = ref(0);
            const currentPage = computed(() => (limit.value > 0 ? Math.floor(offset.value / limit.value) + 1 : 1));
            const dialogVisible = ref(false);
            const dialogMode = ref('create');
            const editingId = ref(null);
            const form = reactive({ name: '', description: '', import_config: '' });


            async function loadList() {
                loading.value = true;
                try {
                    const res = await axios.get(`${API_PREFIX}/import-configs`, { params: { limit: limit.value, offset: offset.value } });
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
            async function handleExecute(row) {
                try {
                    await ElMessageBox.confirm('确定使用该配置执行导入？', '执行导入', { type: 'info' });
                    executingId.value = row.id;
                    const res = await axios.post(`${API_PREFIX}/import-configs/${row.id}/execute`);
                    const stats = res.data?.stats || {};
                    const msg = `导入完成：成功 ${stats.success ?? 0} 条，失败 ${stats.fail ?? 0} 条，跳过 ${stats.skipped ?? 0} 条`;
                    ElMessage.success(msg);
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
                dialogVisible, dialogMode, form, executingId,
                formatDateTime: formatDateTime || (s => (s ? new Date(s).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '-')),
                loadList, openCreate, openEdit, submitForm, handleDelete, handleExecute, onPageChange,
                Plus: icons.Plus, Edit: icons.Edit, Delete: icons.Delete, VideoPlay: icons.VideoPlay
            };
        },
        template: `
        <div style="height:100%;width:100%;min-width:0;display:flex;flex-direction:column;background:#fff;">
            <div style="padding:16px 20px;border-bottom:1px solid #e4e7ed;display:flex;justify-content:space-between;align-items:center;">
                <span style="font-weight:600;">导入配置管理</span>
                <el-button type="primary" @click="openCreate" :icon="Plus">新建配置</el-button>
            </div>
            <div style="flex:1;min-width:0;overflow:auto;padding:20px;">
                <el-table :data="items" v-loading="loading" stripe border style="width:100%">
                    <el-table-column prop="id" label="ID" width="180" show-overflow-tooltip />
                    <el-table-column prop="name" label="名称" min-width="140" />
                    <el-table-column prop="description" label="描述" min-width="160" show-overflow-tooltip />
                    <el-table-column label="创建时间" width="170"><template #default="s">{{ formatDateTime(s.row.created_at) }}</template></el-table-column>
                    <el-table-column label="操作" width="220" fixed="right">
                        <template #default="s">
                            <el-button link type="primary" size="small" @click="handleExecute(s.row)" :icon="VideoPlay" :loading="executingId===s.row.id">执行导入</el-button>
                            <el-button link type="primary" size="small" @click="openEdit(s.row)" :icon="Edit">编辑</el-button>
                            <el-button link type="danger" size="small" @click="handleDelete(s.row)" :icon="Delete">删除</el-button>
                        </template>
                    </el-table-column>
                </el-table>
            </div>
            <div style="padding:12px 20px;border-top:1px solid #e4e7ed;display:flex;justify-content:flex-end;">
                <el-pagination :current-page="currentPage" :page-size="limit" :total="total" layout="prev,pager,next" @current-change="onPageChange" />
            </div>

            <el-dialog v-model="dialogVisible" :title="dialogMode==='create'?'新建导入配置':'编辑导入配置'" width="500px" @close="dialogVisible=false">
                <el-form :model="form" label-width="80px">
                    <el-form-item label="名称" required><el-input v-model="form.name" placeholder="配置名称" /></el-form-item>
                    <el-form-item label="描述"><el-input v-model="form.description" type="textarea" placeholder="描述" :rows="2" /></el-form-item>
                    <el-form-item label="配置(JSON)"><el-input v-model="form.import_config" type="textarea" placeholder='{"type":"feishu_excel",...}' :rows="4" /></el-form-item>
                </el-form>
                <template #footer><el-button @click="dialogVisible=false">取消</el-button><el-button type="primary" @click="submitForm">确定</el-button></template>
            </el-dialog>

        </div>
        `
    });
})();
