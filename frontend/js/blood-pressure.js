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
        const selectedUserId = ref('');
        const users = ref([]);
        const usersLoading = ref(false);
        const startDate = ref(null);
        const endDate = ref(null);
        
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
                { required: true, message: '请选择用户', trigger: 'change' }
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
        
        // 加载用户列表
        const loadUsers = async () => {
            usersLoading.value = true;
            try {
                const response = await axios.get(`${API_BASE}/api/v1/users?limit=1000&offset=0`);
                // 后端返回的是 {users: [...]} 格式，需要提取 users 数组
                users.value = response.data?.users || response.data || [];
            } catch (error) {
                console.error('Error:', error);
                ElMessage.error('加载用户列表失败: ' + (error.response?.data?.detail || error.message));
                users.value = [];
            } finally {
                usersLoading.value = false;
            }
        };
        
        // 格式化日期为 YYYY-MM-DD（用于API请求）
        const formatDate = (date) => {
            if (!date) return null;
            // 如果已经是字符串格式（YYYY-MM-DD），直接返回
            if (typeof date === 'string') {
                return date;
            }
            // 如果是Date对象，转换为字符串
            const d = new Date(date);
            const year = d.getFullYear();
            const month = String(d.getMonth() + 1).padStart(2, '0');
            const day = String(d.getDate()).padStart(2, '0');
            return `${year}-${month}-${day}`;
        };
        
        // 自动填充14天前的时间
        const fillLast14Days = () => {
            const today = new Date();
            const daysAgo14 = new Date();
            daysAgo14.setDate(today.getDate() - 14);
            
            // 格式化为 YYYY-MM-DD 字符串（因为el-date-picker的value-format设置为YYYY-MM-DD）
            const formatDateStr = (date) => {
                const year = date.getFullYear();
                const month = String(date.getMonth() + 1).padStart(2, '0');
                const day = String(date.getDate()).padStart(2, '0');
                return `${year}-${month}-${day}`;
            };
            
            startDate.value = formatDateStr(daysAgo14);
            endDate.value = formatDateStr(today);
            
            // 自动触发查询
            loadRecords();
        };
        
        // 清空时间筛选
        const clearDateFilter = () => {
            startDate.value = null;
            endDate.value = null;
            loadRecords();
        };
        
        // 加载数据
        const loadRecords = async () => {
            loading.value = true;
            try {
                let url = `${API_BASE}/api/v1/blood-pressure?limit=100&offset=0`;
                if (selectedUserId.value) {
                    url += `&user_id=${encodeURIComponent(selectedUserId.value)}`;
                }
                if (startDate.value) {
                    url += `&start_date=${formatDate(startDate.value)}`;
                }
                if (endDate.value) {
                    url += `&end_date=${formatDate(endDate.value)}`;
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
        
        // 保存上次输入的值到 localStorage
        const saveLastInput = () => {
            try {
                const lastInput = {
                    user_id: form.user_id || '',
                    systolic: form.systolic || null,
                    diastolic: form.diastolic || null,
                    heart_rate: form.heart_rate || null,
                    record_time: form.record_time || null,
                    notes: form.notes || ''
                };
                localStorage.setItem('blood_pressure_last_input', JSON.stringify(lastInput));
            } catch (error) {
                console.error('保存上次输入值失败:', error);
            }
        };
        
        // 从 localStorage 恢复上次输入的值
        const restoreLastInput = () => {
            try {
                const saved = localStorage.getItem('blood_pressure_last_input');
                if (saved) {
                    const lastInput = JSON.parse(saved);
                    Object.assign(form, {
                        id: null,
                        user_id: lastInput.user_id || '',
                        systolic: lastInput.systolic || null,
                        diastolic: lastInput.diastolic || null,
                        heart_rate: lastInput.heart_rate || null,
                        record_time: lastInput.record_time || null,
                        notes: lastInput.notes || ''
                    });
                } else {
                    // 如果没有保存的值，则完全重置
                    resetForm();
                }
            } catch (error) {
                console.error('恢复上次输入值失败:', error);
                // 出错时重置表单
                resetForm();
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
                // 新建模式：恢复上次输入的值
                restoreLastInput();
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
                            // 保存本次输入的值，供下次新建时使用
                            saveLastInput();
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
            loadUsers();
            loadRecords();
        });
        
        return {
            records,
            loading,
            selectedUserId,
            users,
            usersLoading,
            startDate,
            endDate,
            dialogVisible,
            submitting,
            formRef,
            form,
            rules,
            loadUsers,
            loadRecords,
            fillLast14Days,
            clearDateFilter,
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
            <div style="padding: 16px 20px; border-bottom: 1px solid #e4e7ed;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <div style="display: flex; gap: 12px; align-items: center;">
                        <el-select
                            v-model="selectedUserId"
                            placeholder="选择用户（可选）"
                            style="width: 250px;"
                            clearable
                            filterable
                            :loading="usersLoading"
                            @change="loadRecords"
                        >
                            <el-option
                                v-for="user in users"
                                :key="user.id"
                                :label="user.user_name + ' (ID: ' + user.id + ')'"
                                :value="user.id"
                            >
                                <span style="float: left">{{ user.user_name }}</span>
                                <span style="float: right; color: #8492a6; font-size: 13px;">ID: {{ user.id }}</span>
                            </el-option>
                        </el-select>
                        <el-button @click="loadRecords" :icon="Refresh">刷新</el-button>
                    </div>
                    <el-button type="primary" @click="openDialog(null)" :icon="Plus">新建记录</el-button>
                </div>
                <div style="display: flex; gap: 12px; align-items: center;">
                    <el-date-picker
                        v-model="startDate"
                        type="date"
                        placeholder="开始日期（可选）"
                        style="width: 180px;"
                        value-format="YYYY-MM-DD"
                        format="YYYY-MM-DD"
                        clearable
                        @change="loadRecords"
                    ></el-date-picker>
                    <span style="color: #909399;">至</span>
                    <el-date-picker
                        v-model="endDate"
                        type="date"
                        placeholder="结束日期（可选）"
                        style="width: 180px;"
                        value-format="YYYY-MM-DD"
                        format="YYYY-MM-DD"
                        clearable
                        @change="loadRecords"
                    ></el-date-picker>
                    <el-button @click="fillLast14Days" type="success" size="small">最近14天</el-button>
                    <el-button @click="clearDateFilter" size="small" v-if="startDate || endDate">清空时间</el-button>
                </div>
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
                    <el-form-item label="用户" prop="user_id">
                        <el-select
                            v-model="form.user_id"
                            placeholder="请选择用户"
                            style="width: 100%;"
                            filterable
                            :disabled="!!form.id"
                            :loading="usersLoading"
                        >
                            <el-option
                                v-for="user in users"
                                :key="user.id"
                                :label="user.user_name + ' (ID: ' + user.id + ')'"
                                :value="user.id"
                            >
                                <span style="float: left">{{ user.user_name }}</span>
                                <span style="float: right; color: #8492a6; font-size: 13px;">ID: {{ user.id }}</span>
                            </el-option>
                        </el-select>
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
            Refresh: icons.Refresh,
            Plus: icons.Plus,
            Edit: icons.Edit,
            Delete: icons.Delete
        }
    });
})();
