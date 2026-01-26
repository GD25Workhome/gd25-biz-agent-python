/**
 * 用户管理模块
 */

(function() {
    'use strict';
    
    const { defineComponent, ref, reactive, onMounted } = Vue;
    const { ElMessage, ElMessageBox } = ElementPlus;
    const icons = ElementPlusIconsVue;

    window.UsersComponent = defineComponent({
        name: 'UsersComponent',
        props: {
            tabId: {
                type: String,
                required: true
            }
        },
        setup(props) {
        const API_BASE = 'http://localhost:8000';
        
        // 数据
        const users = ref([]);
        const loading = ref(false);
        
        // 对话框
        const dialogVisible = ref(false);
        const submitting = ref(false);
        const formRef = ref(null);
        
        // 性别 checkbox 数组（用于 checkbox-group）
        const genderArray = ref([]);
        
        // 处理性别选择变化（确保只能选一个）
        const handleGenderChange = (value) => {
            if (value.length > 1) {
                // 如果选择了多个，只保留最后一个
                genderArray.value = [value[value.length - 1]];
            }
            // 更新 form.gender
            form.gender = genderArray.value.length > 0 ? genderArray.value[0] : '';
        };
        
        // 表单数据
        const form = reactive({
            id: null,
            user_name: '',
            age: null,
            gender: '',
            systolic_target: null,
            diastolic_target: null
        });
        
        // 表单验证规则
        const rules = {
            user_name: [
                { required: true, message: '请输入用户名', trigger: 'blur' },
                { min: 1, max: 100, message: '用户名长度：1-100字符', trigger: 'blur' }
            ],
            age: [
                {
                    validator: (rule, value, callback) => {
                        if (value === null || value === undefined || value === '') {
                            callback();
                            return;
                        }
                        const num = Number(value);
                        if (isNaN(num) || num <= 0 || !Number.isInteger(num)) {
                            callback(new Error('年龄必须是正整数'));
                        } else {
                            callback();
                        }
                    },
                    trigger: 'blur'
                }
            ],
            gender: [
                {
                    validator: (rule, value, callback) => {
                        if (value === '' || value === null || value === undefined) {
                            callback();
                            return;
                        }
                        if (value !== '男' && value !== '女') {
                            callback(new Error('性别必须是"男"或"女"'));
                        } else {
                            callback();
                        }
                    },
                    trigger: 'change'
                }
            ],
            systolic_target: [
                {
                    validator: (rule, value, callback) => {
                        if (value === null || value === undefined || value === '') {
                            callback();
                            return;
                        }
                        const num = Number(value);
                        if (isNaN(num) || num <= 0 || !Number.isInteger(num)) {
                            callback(new Error('收缩压目标值必须是正整数'));
                        } else {
                            callback();
                        }
                    },
                    trigger: 'blur'
                }
            ],
            diastolic_target: [
                {
                    validator: (rule, value, callback) => {
                        if (value === null || value === undefined || value === '') {
                            callback();
                            return;
                        }
                        const num = Number(value);
                        if (isNaN(num) || num <= 0 || !Number.isInteger(num)) {
                            callback(new Error('舒张压目标值必须是正整数'));
                        } else {
                            callback();
                        }
                    },
                    trigger: 'blur'
                }
            ]
        };
        
        // 加载数据
        const loadUsers = async () => {
            loading.value = true;
            try {
                const response = await axios.get(`${API_BASE}/api/v1/users?limit=100&offset=0`);
                // 后端返回的是 {users: [...]} 格式，需要提取 users 数组
                users.value = response.data?.users || response.data || [];
            } catch (error) {
                console.error('Error:', error);
                ElMessage.error('加载用户列表失败: ' + (error.response?.data?.detail || error.message));
                users.value = []; // 出错时设置为空数组
            } finally {
                loading.value = false;
            }
        };
        
        // 打开对话框
        const openDialog = async (user) => {
            if (user) {
                // 编辑模式：从 user_info 对象中提取字段值（使用中文 key）
                const userInfo = user.user_info || {};
                const gender = userInfo['性别'] || '';
                Object.assign(form, {
                    id: user.id,
                    user_name: user.user_name,
                    age: userInfo['年龄'] || null,
                    gender: gender,
                    systolic_target: userInfo['收缩压目标值（mmHg）'] || null,
                    diastolic_target: userInfo['舒张压目标值（mmHg）'] || null
                });
                // 设置性别 checkbox 数组
                genderArray.value = gender ? [gender] : [];
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
                user_name: '',
                age: null,
                gender: '',
                systolic_target: null,
                diastolic_target: null
            });
            genderArray.value = [];
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
                        // 构建 user_info 对象（使用中文 key）
                        const userInfo = {};
                        if (form.age !== null && form.age !== undefined && form.age !== '') {
                            userInfo['年龄'] = Number(form.age);
                        }
                        if (form.gender) {
                            userInfo['性别'] = form.gender;
                        }
                        if (form.systolic_target !== null && form.systolic_target !== undefined && form.systolic_target !== '') {
                            userInfo['收缩压目标值（mmHg）'] = Number(form.systolic_target);
                        }
                        if (form.diastolic_target !== null && form.diastolic_target !== undefined && form.diastolic_target !== '') {
                            userInfo['舒张压目标值（mmHg）'] = Number(form.diastolic_target);
                        }
                        
                        // 将 user_info 对象转换为 JSON 字符串
                        const userInfoJson = Object.keys(userInfo).length > 0 ? JSON.stringify(userInfo) : null;
                        
                        const formData = {
                            user_name: form.user_name.trim(),
                            user_info: userInfoJson
                        };
                        
                        if (form.id) {
                            // 更新
                            await axios.put(`${API_BASE}/api/v1/users/${form.id}`, formData);
                            ElMessage.success('更新成功');
                        } else {
                            // 创建
                            await axios.post(`${API_BASE}/api/v1/users`, formData);
                            ElMessage.success('创建成功');
                        }
                        
                        dialogVisible.value = false;
                        loadUsers();
                    } catch (error) {
                        console.error('Error:', error);
                        ElMessage.error((form.id ? '更新' : '创建') + '失败: ' + (error.response?.data?.detail || error.message));
                    } finally {
                        submitting.value = false;
                    }
                }
            });
        };
        
        // 删除用户
        const deleteUser = async (id) => {
            try {
                await ElMessageBox.confirm(
                    '确定要删除这个用户吗？',
                    '提示',
                    {
                        confirmButtonText: '确定',
                        cancelButtonText: '取消',
                        type: 'warning'
                    }
                );
                
                await axios.delete(`${API_BASE}/api/v1/users/${id}`);
                ElMessage.success('删除成功');
                loadUsers();
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
        });
        
        return {
            users,
            loading,
            dialogVisible,
            submitting,
            formRef,
            form,
            rules,
            genderArray,
            handleGenderChange,
            loadUsers,
            openDialog,
            resetForm,
            submitForm,
            deleteUser,
            formatDateTime
        };
    },
    template: `
        <div style="height: 100%; display: flex; flex-direction: column; background: #fff;">
            <!-- 工具栏 -->
            <div style="padding: 16px 20px; border-bottom: 1px solid #e4e7ed; display: flex; justify-content: space-between; align-items: center;">
                <el-button @click="loadUsers" :icon="Refresh">刷新</el-button>
                <el-button type="primary" @click="openDialog(null)" :icon="Plus">新建用户</el-button>
            </div>
            
            <!-- 表格 -->
            <div style="flex: 1; overflow: auto; padding: 20px;">
                <el-table
                    :data="users"
                    v-loading="loading"
                    stripe
                    border
                    style="width: 100%"
                    :default-sort="{prop: 'created_at', order: 'descending'}"
                >
                    <el-table-column prop="id" label="ID" width="80" sortable></el-table-column>
                    <el-table-column prop="user_name" label="用户名" width="150" sortable></el-table-column>
                    <el-table-column prop="user_info" label="用户信息" min-width="200">
                        <template #default="scope">
                            <div 
                                v-if="scope.row.user_info"
                                style="max-width: 400px; word-break: break-all; white-space: pre-wrap; font-family: 'Courier New', monospace; font-size: 12px; background: #f5f7fa; padding: 8px; border-radius: 4px;"
                            >
                                {{ JSON.stringify(scope.row.user_info, null, 2) }}
                            </div>
                            <span v-else style="color: #909399;">-</span>
                        </template>
                    </el-table-column>
                    <el-table-column prop="created_at" label="创建时间" width="180" sortable>
                        <template #default="scope">
                            {{ formatDateTime(scope.row.created_at) }}
                        </template>
                    </el-table-column>
                    <el-table-column prop="updated_at" label="更新时间" width="180" sortable>
                        <template #default="scope">
                            {{ scope.row.updated_at ? formatDateTime(scope.row.updated_at) : '-' }}
                        </template>
                    </el-table-column>
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
                                @click="deleteUser(scope.row.id)"
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
                :title="form.id ? '编辑用户' : '新建用户'"
                width="600px"
                @close="resetForm"
            >
                <el-form
                    ref="formRef"
                    :model="form"
                    :rules="rules"
                    label-width="120px"
                >
                    <el-form-item label="用户名" prop="user_name">
                        <el-input 
                            v-model="form.user_name" 
                            maxlength="100"
                            show-word-limit
                            placeholder="请输入用户名"
                        ></el-input>
                    </el-form-item>
                    <el-form-item label="年龄" prop="age">
                        <el-input-number 
                            v-model="form.age" 
                            :min="1"
                            :max="150"
                            :precision="0"
                            placeholder="请输入年龄"
                            style="width: 100%"
                        ></el-input-number>
                    </el-form-item>
                    <el-form-item label="性别" prop="gender">
                        <el-checkbox-group v-model="genderArray" @change="handleGenderChange">
                            <el-checkbox label="男">男</el-checkbox>
                            <el-checkbox label="女">女</el-checkbox>
                        </el-checkbox-group>
                    </el-form-item>
                    <el-form-item label="收缩压目标值（mmHg）" prop="systolic_target">
                        <el-input-number 
                            v-model="form.systolic_target" 
                            :min="1"
                            :max="300"
                            :precision="0"
                            placeholder="请输入收缩压目标值"
                            style="width: 100%"
                        ></el-input-number>
                    </el-form-item>
                    <el-form-item label="舒张压目标值（mmHg）" prop="diastolic_target">
                        <el-input-number 
                            v-model="form.diastolic_target" 
                            :min="1"
                            :max="200"
                            :precision="0"
                            placeholder="请输入舒张压目标值"
                            style="width: 100%"
                        ></el-input-number>
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
