/**
 * 血压记录管理模块
 */

(function() {
    'use strict';
    
    const { defineComponent, ref, reactive, onMounted } = Vue;
    const { ElMessage, ElMessageBox } = ElementPlus;
    const icons = ElementPlusIconsVue;

    window.BloodPressureComponent = defineComponent({
        name: 'BloodPressureComponent',
        props: {
            tabId: {
                type: String,
                required: true
            }
        },
        setup(props) {
        const API_BASE = 'http://localhost:8000';
        
        // 数据
        const records = ref([]);
        const loading = ref(false);
        const filter = ref('');
        
        // 对话框
        const dialogVisible = ref(false);
        const submitting = ref(false);
        const formRef = ref(null);
        
        // 表单数据
        const form = reactive({
            id: null,
            user_id: '',
            systolic: null,
            diastolic: null,
            heart_rate: null,
            record_time: null,
            notes: ''
        });
        
        // 表单验证规则
        const rules = {
            user_id: [
                { required: true, message: '请输入用户ID', trigger: 'blur' }
            ],
            systolic: [
                { required: true, message: '请输入收缩压', trigger: 'blur' },
                { type: 'number', min: 50, max: 250, message: '收缩压范围：50-250 mmHg', trigger: 'blur' }
            ],
            diastolic: [
                { required: true, message: '请输入舒张压', trigger: 'blur' },
                { type: 'number', min: 30, max: 200, message: '舒张压范围：30-200 mmHg', trigger: 'blur' }
            ],
            heart_rate: [
                { type: 'number', min: 30, max: 200, message: '心率范围：30-200 bpm', trigger: 'blur' }
            ]
        };
        
        // 加载数据
        const loadRecords = async () => {
            loading.value = true;
            try {
                let url = `${API_BASE}/api/v1/blood-pressure?limit=100&offset=0`;
                if (filter.value.trim()) {
                    url += `&user_id=${encodeURIComponent(filter.value.trim())}`;
                }
                
                const response = await axios.get(url);
                records.value = response.data;
            } catch (error) {
                console.error('Error:', error);
                ElMessage.error('加载血压记录失败: ' + (error.response?.data?.detail || error.message));
            } finally {
                loading.value = false;
            }
        };
        
        // 打开对话框
        const openDialog = async (record) => {
            if (record) {
                // 编辑模式
                Object.assign(form, {
                    id: record.id,
                    user_id: record.user_id,
                    systolic: record.systolic,
                    diastolic: record.diastolic,
                    heart_rate: record.heart_rate,
                    record_time: record.record_time ? record.record_time.replace('Z', '').substring(0, 19) : null,
                    notes: record.notes || ''
                });
            } else {
                // 新建模式
                resetForm();
            }
            dialogVisible.value = true;
        };
        
        // 重置表单
        const resetForm = () => {
            Object.assign(form, {
                id: null,
                user_id: '',
                systolic: null,
                diastolic: null,
                heart_rate: null,
                record_time: null,
                notes: ''
            });
            if (formRef.value) {
                formRef.value.clearValidate();
            }
        };
        
        // 提交表单
        const submitForm = async () => {
            if (!formRef.value) return;
            
            await formRef.value.validate(async (valid) => {
                if (valid) {
                    submitting.value = true;
                    try {
                        const formData = {
                            user_id: form.user_id,
                            systolic: form.systolic,
                            diastolic: form.diastolic,
                            heart_rate: form.heart_rate || null,
                            record_time: form.record_time ? new Date(form.record_time).toISOString() : null,
                            notes: form.notes.trim() || null
                        };
                        
                        if (form.id) {
                            // 更新
                            await axios.put(`${API_BASE}/api/v1/blood-pressure/${form.id}`, formData);
                            ElMessage.success('更新成功');
                        } else {
                            // 创建
                            await axios.post(`${API_BASE}/api/v1/blood-pressure`, formData);
                            ElMessage.success('创建成功');
                        }
                        
                        dialogVisible.value = false;
                        loadRecords();
                    } catch (error) {
                        console.error('Error:', error);
                        ElMessage.error((form.id ? '更新' : '创建') + '失败: ' + (error.response?.data?.detail || error.message));
                    } finally {
                        submitting.value = false;
                    }
                }
            });
        };
        
        // 删除记录
        const deleteRecord = async (id) => {
            try {
                await ElMessageBox.confirm(
                    '确定要删除这条血压记录吗？',
                    '提示',
                    {
                        confirmButtonText: '确定',
                        cancelButtonText: '取消',
                        type: 'warning'
                    }
                );
                
                await axios.delete(`${API_BASE}/api/v1/blood-pressure/${id}`);
                ElMessage.success('删除成功');
                loadRecords();
            } catch (error) {
                if (error !== 'cancel') {
                    console.error('Error:', error);
                    ElMessage.error('删除失败: ' + (error.response?.data?.detail || error.message));
                }
            }
        };
        
        // 格式化时间
        const formatDateTime = (dateTimeStr) => {
            if (!dateTimeStr) return '-';
            const date = new Date(dateTimeStr);
            return date.toLocaleString('zh-CN', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            });
        };
        
        // 初始化
        onMounted(() => {
            loadRecords();
        });
        
        return {
            records,
            loading,
            filter,
            dialogVisible,
            submitting,
            formRef,
            form,
            rules,
            loadRecords,
            openDialog,
            resetForm,
            submitForm,
            deleteRecord,
            formatDateTime
        };
    },
    template: `
        <div style="height: 100%; display: flex; flex-direction: column; background: #fff;">
            <!-- 工具栏 -->
            <div style="padding: 16px 20px; border-bottom: 1px solid #e4e7ed; display: flex; justify-content: space-between; align-items: center;">
                <div style="display: flex; gap: 12px; align-items: center;">
                    <el-input
                        v-model="filter"
                        placeholder="筛选用户ID（可选）"
                        style="width: 200px;"
                        clearable
                        @keyup.enter="loadRecords"
                    >
                        <template #prefix>
                            <el-icon><Search /></el-icon>
                        </template>
                    </el-input>
                    <el-button @click="loadRecords" :icon="Refresh">刷新</el-button>
                </div>
                <el-button type="primary" @click="openDialog(null)" :icon="Plus">新建记录</el-button>
            </div>
            
            <!-- 表格 -->
            <div style="flex: 1; overflow: auto; padding: 20px;">
                <el-table
                    :data="records"
                    v-loading="loading"
                    stripe
                    border
                    style="width: 100%"
                    :default-sort="{prop: 'created_at', order: 'descending'}"
                >
                    <el-table-column prop="id" label="ID" width="80" sortable></el-table-column>
                    <el-table-column prop="user_id" label="用户ID" width="120" sortable></el-table-column>
                    <el-table-column prop="systolic" label="收缩压" width="100" sortable>
                        <template #default="scope">
                            <el-tag type="danger">{{ scope.row.systolic }} mmHg</el-tag>
                        </template>
                    </el-table-column>
                    <el-table-column prop="diastolic" label="舒张压" width="100" sortable>
                        <template #default="scope">
                            <el-tag type="warning">{{ scope.row.diastolic }} mmHg</el-tag>
                        </template>
                    </el-table-column>
                    <el-table-column prop="heart_rate" label="心率" width="100" sortable>
                        <template #default="scope">
                            {{ scope.row.heart_rate ? scope.row.heart_rate + ' bpm' : '-' }}
                        </template>
                    </el-table-column>
                    <el-table-column prop="record_time" label="记录时间" width="180" sortable>
                        <template #default="scope">
                            {{ formatDateTime(scope.row.record_time) }}
                        </template>
                    </el-table-column>
                    <el-table-column prop="notes" label="备注" min-width="150" show-overflow-tooltip></el-table-column>
                    <el-table-column label="操作" width="150" fixed="right">
                        <template #default="scope">
                            <el-button 
                                type="primary" 
                                size="small" 
                                @click="openDialog(scope.row)"
                                :icon="Edit"
                            >
                                编辑
                            </el-button>
                            <el-button 
                                type="danger" 
                                size="small" 
                                @click="deleteRecord(scope.row.id)"
                                :icon="Delete"
                            >
                                删除
                            </el-button>
                        </template>
                    </el-table-column>
                </el-table>
            </div>
            
            <!-- 表单对话框 -->
            <el-dialog
                v-model="dialogVisible"
                :title="form.id ? '编辑血压记录' : '新建血压记录'"
                width="600px"
                @close="resetForm"
            >
                <el-form
                    ref="formRef"
                    :model="form"
                    :rules="rules"
                    label-width="120px"
                >
                    <el-form-item label="用户ID" prop="user_id">
                        <el-input v-model="form.user_id" :disabled="!!form.id"></el-input>
                    </el-form-item>
                    <el-form-item label="收缩压 (mmHg)" prop="systolic">
                        <el-input-number 
                            v-model="form.systolic" 
                            :min="50" 
                            :max="250"
                            style="width: 100%;"
                        ></el-input-number>
                    </el-form-item>
                    <el-form-item label="舒张压 (mmHg)" prop="diastolic">
                        <el-input-number 
                            v-model="form.diastolic" 
                            :min="30" 
                            :max="200"
                            style="width: 100%;"
                        ></el-input-number>
                    </el-form-item>
                    <el-form-item label="心率 (bpm)" prop="heart_rate">
                        <el-input-number 
                            v-model="form.heart_rate" 
                            :min="30" 
                            :max="200"
                            style="width: 100%;"
                        ></el-input-number>
                    </el-form-item>
                    <el-form-item label="记录时间" prop="record_time">
                        <el-date-picker
                            v-model="form.record_time"
                            type="datetime"
                            placeholder="选择日期时间"
                            style="width: 100%;"
                            value-format="YYYY-MM-DDTHH:mm:ss"
                        ></el-date-picker>
                    </el-form-item>
                    <el-form-item label="备注" prop="notes">
                        <el-input 
                            v-model="form.notes" 
                            type="textarea" 
                            :rows="3"
                            placeholder="请输入备注信息"
                        ></el-input>
                    </el-form-item>
                </el-form>
                <template #footer>
                    <el-button @click="dialogVisible = false">取消</el-button>
                    <el-button type="primary" @click="submitForm" :loading="submitting">
                        确定
                    </el-button>
                </template>
            </el-dialog>
        </div>
    `,
        components: {
            Search: icons.Search,
            Refresh: icons.Refresh,
            Plus: icons.Plus,
            Edit: icons.Edit,
            Delete: icons.Delete
        }
    });
})();
