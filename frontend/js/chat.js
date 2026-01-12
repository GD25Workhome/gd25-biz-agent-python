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
        
        // 聊天上下文区域（默认折叠）
        const contextExpanded = ref([]); // el-collapse 需要数组格式，空数组表示默认折叠
        
        // 登录信息
        const tokenId = ref('');
        const loginInfo = ref({
            user_id: '',
            user_name: '',
            flow_name: '',
            flow_display: '',
            session_id: '',
            // 完整的用户信息
            user_full_info: null
        });
        
        // 登录弹框
        const loginDialogVisible = ref(false);
        const allUsers = ref([]);
        const userSearchKeyword = ref('');
        const filteredUsers = ref([]);
        const loginSelectedUserId = ref('');
        const loginSelectedFlow = ref('medical_agent');
        
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
        
        // 初始化流程选择
        const initFlowSelection = () => {
            // 从 localStorage 读取保存的流程选择
            const savedFlow = localStorage.getItem('chat_selected_flow');
            if (savedFlow && (savedFlow === 'medical_agent' || savedFlow === 'work_plan_agent')) {
                selectedFlow.value = savedFlow;
                loginSelectedFlow.value = savedFlow;
            }
        };
        
        // 保存流程选择到 localStorage
        const saveFlowSelection = () => {
            if (selectedFlow.value) {
                localStorage.setItem('chat_selected_flow', selectedFlow.value);
            } else {
                localStorage.removeItem('chat_selected_flow');
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
        
        // 打开登录弹框
        const openLoginDialog = async () => {
            loginDialogVisible.value = true;
            userSearchKeyword.value = '';
            loginSelectedUserId.value = '';
            loginSelectedFlow.value = selectedFlow.value || 'medical_agent';
            await loadUsers();
        };
        
        // 关闭登录弹框
        const closeLoginDialog = () => {
            loginDialogVisible.value = false;
        };
        
        // 登录：创建token和session
        const handleLogin = async () => {
            if (!loginSelectedUserId.value) {
                ElMessage.warning('请选择用户');
                return;
            }
            
            if (!loginSelectedFlow.value) {
                ElMessage.warning('请选择流程');
                return;
            }
            
            try {
                // 1. 创建Token
                const tokenResponse = await axios.post(`${API_BASE}/api/v1/login/token`, {
                    user_id: loginSelectedUserId.value
                });
                
                const tokenIdValue = tokenResponse.data.token_id;
                
                // 2. 创建Session
                const sessionResponse = await axios.post(`${API_BASE}/api/v1/login/session`, {
                    user_id: loginSelectedUserId.value,
                    flow_name: loginSelectedFlow.value
                });
                
                const sessionIdValue = sessionResponse.data.session_id;
                
                // 3. 获取Token信息
                const tokenInfoResponse = await axios.get(`${API_BASE}/api/v1/login/token/${tokenIdValue}`);
                const tokenInfo = tokenInfoResponse.data;
                
                // 4. 获取Session信息
                const sessionInfoResponse = await axios.get(`${API_BASE}/api/v1/login/session/${sessionIdValue}`);
                const sessionInfo = sessionInfoResponse.data;
                
                // 5. 更新登录信息
                const selectedUser = allUsers.value.find(u => u.id === loginSelectedUserId.value);
                loginInfo.value = {
                    user_id: tokenInfo.user_id,
                    user_name: selectedUser ? (selectedUser.username || selectedUser.user_name || '') : '',
                    flow_name: sessionInfo.flow_info.flow_key,
                    flow_display: sessionInfo.flow_info.flow_name,
                    session_id: sessionIdValue,
                    // 保存完整的用户信息
                    user_full_info: selectedUser || null
                };
                
                // 更新相关状态
                tokenId.value = tokenIdValue;
                sessionId.value = sessionIdValue;
                selectedFlow.value = loginSelectedFlow.value;
                selectedUserId.value = loginSelectedUserId.value;
                selectedUserName.value = loginInfo.value.user_name;
                
                // 更新用户信息
                if (tokenInfo.user_info) {
                    if (typeof tokenInfo.user_info === 'object') {
                        userInfo.value = JSON.stringify(tokenInfo.user_info, null, 2);
                    } else {
                        userInfo.value = tokenInfo.user_info;
                    }
                } else {
                    userInfo.value = '';
                }
                
                // 保存到localStorage
                saveFlowSelection();
                saveUserSelection();
                
                ElMessage.success('登录成功');
                closeLoginDialog();
            } catch (error) {
                console.error('登录失败:', error);
                const errorMsg = error.response?.data?.detail || error.message || '登录失败';
                ElMessage.error('登录失败: ' + errorMsg);
            }
        };
        
        // 选择登录用户（在登录弹框中）
        const selectLoginUser = (user) => {
            loginSelectedUserId.value = user.id;
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
        
        // 监听流程选择变化
        watch(selectedFlow, () => {
            saveFlowSelection();
        });
        
        // 格式化登录信息显示（多行格式）
        const formatLoginInfo = () => {
            if (!loginInfo.value.user_id) {
                return '-- 未登录 --';
            }
            
            let result = '';
            
            // 第一行：流程信息
            result += `流程: ${loginInfo.value.flow_display || loginInfo.value.flow_name}`;
            
            // 第二行开始：用户信息
            if (loginInfo.value.user_full_info) {
                const user = loginInfo.value.user_full_info;
                const userDetails = [];
                
                // 用户名
                if (user.username || user.user_name) {
                    userDetails.push(`用户名: ${user.username || user.user_name}`);
                }
                
                // 用户ID
                if (user.id) {
                    userDetails.push(`ID: ${user.id}`);
                }
                
                // 手机号
                if (user.phone) {
                    userDetails.push(`手机: ${user.phone}`);
                }
                
                // 邮箱
                if (user.email) {
                    userDetails.push(`邮箱: ${user.email}`);
                }
                
                // 第二行：基本用户信息
                if (userDetails.length > 0) {
                    result += '\n用户: ' + userDetails.join(' | ');
                }
                
                // 第三行及以后：用户详细信息（user_info）
                if (user.user_info) {
                    let userInfoStr = '';
                    if (typeof user.user_info === 'object') {
                        userInfoStr = JSON.stringify(user.user_info, null, 2);
                    } else {
                        userInfoStr = user.user_info;
                    }
                    if (userInfoStr) {
                        result += '\n详细信息:\n' + userInfoStr;
                    }
                }
            } else {
                // 如果没有完整用户信息，至少显示用户名和ID
                result += `\n用户: ${loginInfo.value.user_name || loginInfo.value.user_id}`;
            }
            
            return result;
        };
        
        // 监听患者基础信息变化
        watch(userInfo, () => {
            saveUserSelection();
        });
        
        // 发送消息
        const sendMessage = async () => {
            const message = inputMessage.value.trim();
            if (!message || isLoading.value) return;
            
            // 验证登录状态
            if (!tokenId.value && !selectedUserId.value) {
                ElMessage.warning('请先登录');
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
                    token_id: tokenId.value || selectedUserId.value,
                    conversation_history: history.length > 0 ? history : null,
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
        
        // 重置会话（只清空聊天框中的内容，历史会话重置）
        const resetSession = () => {
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
        
        // 处理键盘事件（Enter 发送，Shift+Enter 换行）
        const handleKeyDown = (event) => {
            // 如果按下的是 Enter 键
            if (event.key === 'Enter' || event.keyCode === 13) {
                // 如果同时按下了 Shift，允许默认行为（换行）
                if (event.shiftKey) {
                    return;
                }
                // 否则阻止默认行为（不换行）并发送消息
                event.preventDefault();
                sendMessage();
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
            initFlowSelection();
            initDateTimeInput();
            // 不再自动恢复用户选择，用户需要通过登录弹框登录
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
            handleKeyDown,
            // 新增字段
            traceId,
            autoTraceId,
            recordDateTime,
            selectedUserId,
            selectedUserName,
            userInfo,
            generateTraceId,
            // 聊天上下文
            contextExpanded,
            // 登录信息
            tokenId,
            loginInfo,
            formatLoginInfo,
            // 登录弹框
            loginDialogVisible,
            allUsers,
            filteredUsers,
            userSearchKeyword,
            loginSelectedUserId,
            loginSelectedFlow,
            openLoginDialog,
            closeLoginDialog,
            handleLogin,
            selectLoginUser
        };
    },
    template: `
        <div style="height: 100%; display: flex; flex-direction: column; background: #f5f7fa;">
            <!-- 聊天头部 -->
            <div style="padding: 16px 20px; background: #fff; border-bottom: 1px solid #e4e7ed;">
                <!-- 聊天上下文区域 -->
                <el-collapse v-model="contextExpanded" style="border: none;">
                    <el-collapse-item name="context" :title="'聊天上下文'">
                        <template #title>
                            <span style="font-weight: 500; color: #303133;">聊天上下文</span>
                        </template>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                            <!-- 第一列：Trace ID 和 登录信息 -->
                            <div style="display: flex; flex-direction: column; gap: 12px;">
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
                                
                                <!-- 登录信息 -->
                                <div style="position: relative;">
                                    <label style="display: block; margin-bottom: 4px; font-size: 12px; color: #606266;">登录信息</label>
                                    <el-input
                                        :value="formatLoginInfo()"
                                        type="textarea"
                                        :rows="4"
                                        readonly
                                        @click="openLoginDialog"
                                        style="cursor: pointer;"
                                        size="small"
                                    ></el-input>
                                    <el-icon 
                                        style="cursor: pointer; position: absolute; right: 8px; top: 28px; z-index: 10; color: #909399;"
                                        @click.stop="openLoginDialog"
                                    >
                                        <Edit />
                                    </el-icon>
                                </div>
                            </div>
                            
                            <!-- 第二列：记录日期时间 -->
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
                    </el-collapse-item>
                </el-collapse>
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
                        placeholder="输入您的消息... (Enter 发送，Shift+Enter 换行)"
                        @keydown="handleKeyDown"
                        :disabled="isLoading"
                        style="flex: 1;"
                    ></el-input>
                    <div style="display: flex; flex-direction: column; gap: 8px;">
                        <el-button 
                            type="primary" 
                            @click="sendMessage"
                            :loading="isLoading"
                            :disabled="!inputMessage.trim() || (!tokenId && !selectedUserId)"
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
            
            <!-- 登录弹框 -->
            <el-dialog
                v-model="loginDialogVisible"
                title="登录"
                width="600px"
            >
                <div style="display: flex; flex-direction: column; gap: 16px;">
                    <!-- 流程选择 -->
                    <div>
                        <label style="display: block; margin-bottom: 8px; font-size: 14px; color: #606266; font-weight: 500;">选择流程</label>
                        <el-select 
                            v-model="loginSelectedFlow" 
                            style="width: 100%;"
                            placeholder="请选择流程"
                        >
                            <el-option label="医疗分身Agent" value="medical_agent"></el-option>
                            <el-option label="工作计划Agent" value="work_plan_agent"></el-option>
                        </el-select>
                    </div>
                    
                    <!-- 用户选择 -->
                    <div>
                        <label style="display: block; margin-bottom: 8px; font-size: 14px; color: #606266; font-weight: 500;">选择用户</label>
                        <el-input
                            v-model="userSearchKeyword"
                            placeholder="搜索用户名（支持模糊匹配）"
                            style="margin-bottom: 12px;"
                        >
                            <template #prefix>
                                <el-icon><Search /></el-icon>
                            </template>
                        </el-input>
                        <div style="max-height: 300px; overflow-y: auto; border: 1px solid #e4e7ed; border-radius: 4px; padding: 8px;">
                            <div 
                                v-for="user in filteredUsers" 
                                :key="user.id"
                                @click="selectLoginUser(user)"
                                style="padding: 12px; border: 1px solid #e4e7ed; border-radius: 8px; margin-bottom: 8px; cursor: pointer; transition: all 0.2s;"
                                :style="loginSelectedUserId === user.id ? 'background: #e0f2fe; border-color: #409eff;' : ''"
                                @mouseenter="$event.currentTarget.style.background = loginSelectedUserId === user.id ? '#e0f2fe' : '#f3f4f6'"
                                @mouseleave="$event.currentTarget.style.background = loginSelectedUserId === user.id ? '#e0f2fe' : '#fff'"
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
                    </div>
                </div>
                
                <template #footer>
                    <div style="display: flex; justify-content: flex-end; gap: 12px;">
                        <el-button @click="closeLoginDialog">取消</el-button>
                        <el-button type="primary" @click="handleLogin" :disabled="!loginSelectedUserId || !loginSelectedFlow">确定</el-button>
                    </div>
                </template>
            </el-dialog>
        </div>
    `,
        components: {
            Promotion: icons.Promotion,
            Search: icons.Search,
            Edit: icons.Edit
        }
    });
})();
