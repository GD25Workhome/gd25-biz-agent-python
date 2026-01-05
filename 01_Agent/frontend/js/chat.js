/**
 * 聊天对话模块
 */

(function() {
    'use strict';
    
    const { defineComponent, ref, reactive, onMounted, nextTick, watch } = Vue;
    const { ElMessage, ElMessageBox } = ElementPlus;
    const icons = ElementPlusIconsVue;

    window.ChatComponent = defineComponent({
        name: 'ChatComponent',
        props: {
            tabId: {
                type: String,
                required: true
            }
        },
        setup(props) {
        const API_BASE = 'http://localhost:8000';
        const USERS_API_URL = `${API_BASE}/api/v1/users`;
        
        // 聊天数据
        const messages = ref([]);
        const inputMessage = ref('');
        const isLoading = ref(false);
        const selectedFlow = ref('medical_agent');
        const sessionId = ref(`session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`);
        const messagesContainer = ref(null);
        
        // 新增字段
        const traceId = ref('');
        const autoTraceId = ref(true);
        const recordDateTime = ref('');
        const selectedUserId = ref('');
        const selectedUserName = ref('-- 请选择用户 --');
        const userInfo = ref('');
        const conversationHistory = ref([]);
        
        // 用户选择弹框
        const userSelectDialogVisible = ref(false);
        const allUsers = ref([]);
        const userSearchKeyword = ref('');
        const filteredUsers = ref([]);
        
        // 生成 Trace ID
        const generateTraceId = () => {
            let result = '';
            const hexChars = '0123456789abcdef';
            for (let i = 0; i < 32; i++) {
                if (typeof crypto !== 'undefined' && crypto.getRandomValues) {
                    const randomBytes = new Uint8Array(1);
                    crypto.getRandomValues(randomBytes);
                    result += hexChars[randomBytes[0] % 16];
                } else {
                    result += hexChars[Math.floor(Math.random() * 16)];
                }
            }
            return result;
        };
        
        // 检测浏览器是否支持 datetime-local
        const supportsDateTimeLocal = () => {
            const input = document.createElement('input');
            input.setAttribute('type', 'datetime-local');
            return input.type === 'datetime-local';
        };
        
        // 初始化日期时间输入框
        const initDateTimeInput = () => {
            // 从 localStorage 读取保存的日期时间值
            const savedDateTime = localStorage.getItem('chat_record_datetime');
            let defaultValue = '';
            
            if (savedDateTime) {
                defaultValue = savedDateTime;
            } else {
                // 如果没有保存的值，使用当前时间
                const now = new Date();
                const year = now.getFullYear();
                const month = String(now.getMonth() + 1).padStart(2, '0');
                const day = String(now.getDate()).padStart(2, '0');
                const hours = String(now.getHours()).padStart(2, '0');
                const minutes = String(now.getMinutes()).padStart(2, '0');
                
                if (supportsDateTimeLocal()) {
                    // datetime-local 输入框需要的格式：YYYY-MM-DDTHH:mm
                    defaultValue = `${year}-${month}-${day}T${hours}:${minutes}`;
                } else {
                    // text 类型使用空格分隔的格式：YYYY-MM-DD HH:mm
                    defaultValue = `${year}-${month}-${day} ${hours}:${minutes}`;
                }
            }
            
            recordDateTime.value = defaultValue;
        };
        
        // 保存日期时间到 localStorage
        const saveDateTime = () => {
            if (recordDateTime.value) {
                localStorage.setItem('chat_record_datetime', recordDateTime.value);
            } else {
                localStorage.removeItem('chat_record_datetime');
            }
        };
        
        // 加载用户列表
        const loadUsers = async () => {
            try {
                const resp = await fetch(USERS_API_URL);
                if (!resp.ok) throw new Error('加载用户列表失败');
                const data = await resp.json();
                allUsers.value = data.users || [];
                filteredUsers.value = allUsers.value;
                return allUsers.value;
            } catch (e) {
                console.error('加载用户列表失败:', e);
                ElMessage.error('加载用户列表失败: ' + e.message);
                return [];
            }
        };
        
        // 打开用户选择弹框
        const openUserSelectDialog = async () => {
            userSelectDialogVisible.value = true;
            userSearchKeyword.value = '';
            await loadUsers();
        };
        
        // 关闭用户选择弹框
        const closeUserSelectDialog = () => {
            userSelectDialogVisible.value = false;
        };
        
        // 选择用户
        const selectUser = (user) => {
            selectedUserId.value = user.id;
            selectedUserName.value = user.username || user.user_name || '-- 请选择用户 --';
            // 自动填充患者基础信息
            if (!userInfo.value.trim() || userInfo.value === '') {
                // 如果 user_info 是对象，转换为 JSON 字符串；如果是字符串，直接使用
                if (user.user_info) {
                    if (typeof user.user_info === 'object') {
                        userInfo.value = JSON.stringify(user.user_info, null, 2);
                    } else {
                        userInfo.value = user.user_info;
                    }
                } else {
                    userInfo.value = '';
                }
            }
            closeUserSelectDialog();
            saveUserSelection();
        };
        
        // 保存用户选择到 localStorage
        const saveUserSelection = () => {
            if (selectedUserId.value) {
                localStorage.setItem('chat_selected_user_id', selectedUserId.value);
                localStorage.setItem('chat_user_info', userInfo.value);
            } else {
                localStorage.removeItem('chat_selected_user_id');
                localStorage.removeItem('chat_user_info');
            }
        };
        
        // 从 localStorage 恢复用户选择
        const restoreUserSelection = async () => {
            const savedUserId = localStorage.getItem('chat_selected_user_id');
            const savedUserInfo = localStorage.getItem('chat_user_info');
            
            await loadUsers();
            
            if (savedUserId) {
                const user = allUsers.value.find(u => u.id === savedUserId);
                if (user) {
                    selectedUserId.value = savedUserId;
                    selectedUserName.value = user.username || user.user_name || '-- 请选择用户 --';
                    if (savedUserInfo !== null) {
                        userInfo.value = savedUserInfo;
                    } else {
                        // 如果 user_info 是对象，转换为 JSON 字符串；如果是字符串，直接使用
                        if (user.user_info) {
                            if (typeof user.user_info === 'object') {
                                userInfo.value = JSON.stringify(user.user_info, null, 2);
                            } else {
                                userInfo.value = user.user_info;
                            }
                        } else {
                            userInfo.value = '';
                        }
                    }
                } else {
                    // 如果用户不存在，选择第一个用户
                    if (allUsers.value.length > 0) {
                        selectUser(allUsers.value[0]);
                    }
                }
            } else {
                // 如果没有保存的用户，选择第一个用户
                if (allUsers.value.length > 0) {
                    selectUser(allUsers.value[0]);
                }
            }
        };
        
        // 过滤用户列表
        watch(userSearchKeyword, (keyword) => {
            if (!keyword || keyword.trim() === '') {
                filteredUsers.value = allUsers.value;
            } else {
                const lowerKeyword = keyword.toLowerCase();
                filteredUsers.value = allUsers.value.filter(user => {
                    const userName = (user.username || user.user_name || '').toLowerCase();
                    return userName.includes(lowerKeyword);
                });
            }
        });
        
        // 更新 Trace ID 控件状态
        watch(autoTraceId, (isAuto) => {
            if (isAuto) {
                traceId.value = '';
            }
        });
        
        // 监听日期时间变化
        watch(recordDateTime, () => {
            saveDateTime();
        });
        
        // 监听患者基础信息变化
        watch(userInfo, () => {
            saveUserSelection();
        });
        
        // 发送消息
        const sendMessage = async () => {
            const message = inputMessage.value.trim();
            if (!message || isLoading.value) return;
            
            // 验证用户选择
            if (!selectedUserId.value) {
                ElMessage.warning('请先选择用户');
                return;
            }
            
            // 生成或获取 Trace ID
            let currentTraceId = traceId.value.trim();
            if (autoTraceId.value || !currentTraceId) {
                currentTraceId = generateTraceId();
            }
            
            // 构建 conversation_history
            const history = conversationHistory.value.map(msg => ({
                role: msg.role,
                content: msg.content
            }));
            
            // 获取日期时间（转换为 YYYY-MM-DD HH:mm 格式）
            let currentDateTime = null;
            if (recordDateTime.value) {
                if (recordDateTime.value.includes('T')) {
                    currentDateTime = recordDateTime.value.replace('T', ' ');
                } else {
                    currentDateTime = recordDateTime.value.trim();
                }
            }
            
            // 添加用户消息到界面
            messages.value.push({
                role: 'user',
                content: message,
                timestamp: new Date()
            });
            
            // 添加到历史记录
            conversationHistory.value.push({
                role: 'user',
                content: message
            });
            
            inputMessage.value = '';
            isLoading.value = true;
            
            // 滚动到底部
            await nextTick();
            scrollToBottom();
            
            try {
                // 构建请求体（将 trace_id 放在请求体中，符合后端 Schema 要求）
                const requestBody = {
                    message: message,
                    session_id: sessionId.value,
                    token_id: selectedUserId.value,
                    flow_name: selectedFlow.value,
                    conversation_history: history.length > 0 ? history : null,
                    user_info: userInfo.value.trim() || null,
                    current_date: currentDateTime,
                    trace_id: currentTraceId || undefined  // 将 traceId 放在请求体中，如果为空则不传（后端会自动生成）
                };
                
                // 发送请求
                const response = await axios.post(`${API_BASE}/api/v1/chat`, requestBody, {
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });
                
                // 添加AI回复
                const responseText = response.data.response || '抱歉，我没有收到回复。';
                messages.value.push({
                    role: 'assistant',
                    content: responseText,
                    timestamp: new Date()
                });
                
                // 添加到历史记录
                conversationHistory.value.push({
                    role: 'assistant',
                    content: responseText
                });
                
                await nextTick();
                scrollToBottom();
            } catch (error) {
                console.error('Error:', error);
                const errorMsg = error.response?.data?.detail || error.message || '未知错误';
                ElMessage.error('发送消息失败: ' + errorMsg);
                
                // 添加错误消息
                messages.value.push({
                    role: 'assistant',
                    content: '抱歉，发生了错误：' + errorMsg,
                    timestamp: new Date(),
                    isError: true
                });
            } finally {
                isLoading.value = false;
            }
        };
        
        // 重置会话
        const resetSession = () => {
            sessionId.value = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
            messages.value = [];
            conversationHistory.value = [];
            messages.value.push({
                role: 'assistant',
                content: '您好！我是您的AI助手，有什么可以帮您的吗？',
                timestamp: new Date()
            });
        };
        
        // 滚动到底部
        const scrollToBottom = () => {
            if (messagesContainer.value) {
                nextTick(() => {
                    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
                });
            }
        };
        
        // 格式化时间
        const formatTime = (date) => {
            if (!date) return '';
            const d = new Date(date);
            return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
        };
        
        // 初始化
        onMounted(async () => {
            initDateTimeInput();
            await restoreUserSelection();
            messages.value.push({
                role: 'assistant',
                content: '您好！我是您的AI助手，有什么可以帮您的吗？',
                timestamp: new Date()
            });
        });
        
        return {
            messages,
            inputMessage,
            isLoading,
            selectedFlow,
            messagesContainer,
            sendMessage,
            formatTime,
            resetSession,
            // 新增字段
            traceId,
            autoTraceId,
            recordDateTime,
            selectedUserId,
            selectedUserName,
            userInfo,
            generateTraceId,
            // 用户选择
            userSelectDialogVisible,
            filteredUsers,
            userSearchKeyword,
            openUserSelectDialog,
            closeUserSelectDialog,
            selectUser
        };
    },
    template: `
        <div style="height: 100%; display: flex; flex-direction: column; background: #f5f7fa;">
            <!-- 聊天头部 -->
            <div style="padding: 16px 20px; background: #fff; border-bottom: 1px solid #e4e7ed;">
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
                    <el-text type="info">
                        当前流程：{{ selectedFlow === 'medical_agent' ? '医疗分身Agent' : '工作计划Agent' }}
                    </el-text>
                    <el-select 
                        v-model="selectedFlow" 
                        style="width: 200px;"
                        placeholder="选择流程"
                    >
                        <el-option label="医疗分身Agent" value="medical_agent"></el-option>
                        <el-option label="工作计划Agent" value="work_plan_agent"></el-option>
                    </el-select>
                </div>
                
                <!-- 配置区域 -->
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px;">
                    <!-- Trace ID -->
                    <div>
                        <label style="display: block; margin-bottom: 4px; font-size: 12px; color: #606266;">Trace ID</label>
                        <div style="display: flex; gap: 8px;">
                            <el-input
                                v-model="traceId"
                                placeholder="留空则自动生成"
                                :disabled="autoTraceId"
                                size="small"
                                style="flex: 1;"
                            ></el-input>
                            <el-button size="small" @click="traceId = generateTraceId()" :disabled="autoTraceId">生成ID</el-button>
                        </div>
                        <el-checkbox v-model="autoTraceId" size="small" style="margin-top: 4px;">
                            每次发送重新生成traceId
                        </el-checkbox>
                    </div>
                    
                    <!-- 记录日期时间 -->
                    <div>
                        <label style="display: block; margin-bottom: 4px; font-size: 12px; color: #606266;">记录日期时间</label>
                        <el-date-picker
                            v-model="recordDateTime"
                            type="datetime"
                            placeholder="选择日期时间"
                            format="YYYY-MM-DD HH:mm"
                            value-format="YYYY-MM-DD HH:mm"
                            size="small"
                            style="width: 100%;"
                        ></el-date-picker>
                    </div>
                </div>
                
                <!-- 用户选择和患者基础信息 -->
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                    <!-- 用户选择 -->
                    <div>
                        <label style="display: block; margin-bottom: 4px; font-size: 12px; color: #606266;">用户选择</label>
                        <el-button 
                            @click="openUserSelectDialog" 
                            size="small" 
                            style="width: 100%; text-align: left;"
                        >
                            {{ selectedUserName }}
                        </el-button>
                    </div>
                    
                    <!-- 患者基础信息 -->
                    <div>
                        <label style="display: block; margin-bottom: 4px; font-size: 12px; color: #606266;">患者基础信息</label>
                        <el-input
                            v-model="userInfo"
                            type="textarea"
                            :rows="2"
                            placeholder="患者基础信息（可编辑，仅用于本次请求参数）"
                            size="small"
                        ></el-input>
                    </div>
                </div>
            </div>
            
            <!-- 消息列表 -->
            <div 
                ref="messagesContainer"
                style="flex: 1; overflow-y: auto; padding: 20px;"
            >
                <div 
                    v-for="(msg, index) in messages" 
                    :key="index"
                    :class="['message-item', msg.role]"
                    style="display: flex; margin-bottom: 20px; animation: fadeIn 0.3s ease-in;"
                >
                    <div 
                        :class="['message-avatar', msg.role]"
                        style="width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; flex-shrink: 0; margin: 0 12px;"
                        :style="msg.role === 'user' ? 'background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white;' : 'background: #e4e7ed; color: #606266;'"
                    >
                        {{ msg.role === 'user' ? '你' : 'AI' }}
                    </div>
                    <div style="flex: 1; max-width: 70%;">
                        <div 
                            :class="['message-content', msg.role]"
                            style="padding: 12px 16px; border-radius: 8px; line-height: 1.6; word-wrap: break-word;"
                            :style="msg.role === 'user' ? 'background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white;' : 'background: #fff; color: #303133; border: 1px solid #e4e7ed;'"
                        >
                            {{ msg.content }}
                        </div>
                        <div 
                            v-if="msg.timestamp"
                            style="font-size: 12px; color: #909399; margin-top: 4px; padding: 0 4px;"
                            :style="msg.role === 'user' ? 'text-align: right;' : 'text-align: left;'"
                        >
                            {{ formatTime(msg.timestamp) }}
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- 输入区域 -->
            <div style="padding: 16px 20px; background: #fff; border-top: 1px solid #e4e7ed;">
                <div style="display: flex; gap: 12px; align-items: flex-end;">
                    <el-input
                        v-model="inputMessage"
                        type="textarea"
                        :rows="3"
                        placeholder="输入您的消息... (Ctrl+Enter 或 Cmd+Enter 发送)"
                        @keydown.ctrl.enter="sendMessage"
                        @keydown.meta.enter="sendMessage"
                        :disabled="isLoading"
                        style="flex: 1;"
                    ></el-input>
                    <div style="display: flex; flex-direction: column; gap: 8px;">
                        <el-button 
                            type="primary" 
                            @click="sendMessage"
                            :loading="isLoading"
                            :disabled="!inputMessage.trim() || !selectedUserId"
                            style="min-width: 100px; height: 74px; font-size: 14px;"
                        >
                            <el-icon v-if="!isLoading" style="margin-right: 4px;"><Promotion /></el-icon>
                            <span v-if="!isLoading">发送</span>
                        </el-button>
                        <el-button 
                            @click="resetSession"
                            size="small"
                            style="min-width: 100px;"
                        >
                            重置会话
                        </el-button>
                    </div>
                </div>
            </div>
            
            <!-- 用户选择弹框 -->
            <el-dialog
                v-model="userSelectDialogVisible"
                title="选择用户"
                width="600px"
            >
                <el-input
                    v-model="userSearchKeyword"
                    placeholder="搜索用户名（支持模糊匹配）"
                    style="margin-bottom: 16px;"
                >
                    <template #prefix>
                        <el-icon><Search /></el-icon>
                    </template>
                </el-input>
                <div style="max-height: 400px; overflow-y: auto;">
                    <div 
                        v-for="user in filteredUsers" 
                        :key="user.id"
                        @click="selectUser(user)"
                        style="padding: 12px; border: 1px solid #e4e7ed; border-radius: 8px; margin-bottom: 8px; cursor: pointer; transition: all 0.2s;"
                        :style="selectedUserId === user.id ? 'background: #e0f2fe; border-color: #409eff;' : ''"
                        @mouseenter="$event.currentTarget.style.background = '#f3f4f6'"
                        @mouseleave="$event.currentTarget.style.background = selectedUserId === user.id ? '#e0f2fe' : '#fff'"
                    >
                        <div style="font-weight: bold; margin-bottom: 4px;">{{ user.username || user.user_name }}</div>
                        <div style="font-size: 12px; color: #909399;">
                            ID: {{ user.id }} | 手机: {{ user.phone || '未设置' }} | 邮箱: {{ user.email || '未设置' }}
                        </div>
                        <div v-if="user.user_info" style="font-size: 12px; color: #606266; margin-top: 4px; white-space: pre-wrap; font-family: 'Courier New', monospace;">
                            {{ typeof user.user_info === 'object' ? JSON.stringify(user.user_info, null, 2) : user.user_info }}
                        </div>
                    </div>
                    <div v-if="filteredUsers.length === 0" style="padding: 20px; text-align: center; color: #909399;">
                        暂无用户
                    </div>
                </div>
            </el-dialog>
        </div>
    `,
        components: {
            Promotion: icons.Promotion,
            Search: icons.Search
        }
    });
})();
