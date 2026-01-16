/**
 * 整体框架管理模块
 * 负责Tab页管理、菜单导航等核心功能
 */

(function() {
    'use strict';
    
    const { ref, reactive, provide, inject, onMounted } = Vue;
    const { ElMessage } = ElementPlus;

    // Tab页管理
    window.useFramework = function() {
        const tabs = ref([]);
        const activeTabId = ref(null);
        const activeMenu = ref('');
        
        // Tab页配置
        const tabConfigs = {
            'chat': {
                title: '聊天对话',
                component: 'ChatComponent',
                icon: 'ChatDotRound'
            },
            'chat-v2': {
                title: '聊天对话—V2',
                component: 'ChatV2Component',
                icon: 'ChatDotRound'
            },
            'blood-pressure': {
                title: '血压记录',
                component: 'BloodPressureComponent',
                icon: 'DataLine'
            },
            'users': {
                title: '用户管理',
                component: 'UsersComponent',
                icon: 'User'
            },
            'flow-preview': {
                title: '流程预览',
                component: 'FlowPreviewComponent',
                icon: 'Document'
            }
        };
        
        // 生成唯一ID
        const generateTabId = (type) => {
            return `${type}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        };
        
        // 打开Tab页
        const openTab = (type) => {
            const config = tabConfigs[type];
            if (!config) {
                ElMessage.warning('未知的功能类型');
                return;
            }
            
            // 检查是否已存在相同类型的Tab
            const existingTab = tabs.value.find(tab => tab.type === type);
            if (existingTab) {
                // 如果已存在，切换到该Tab
                activeTabId.value = existingTab.id;
                return;
            }
            
            // 创建新Tab
            const tabId = generateTabId(type);
            const newTab = {
                id: tabId,
                type: type,
                title: config.title,
                component: config.component,
                icon: config.icon
            };
            
            tabs.value.push(newTab);
            activeTabId.value = tabId;
        };
        
        // 切换Tab
        const switchTab = (tabId) => {
            activeTabId.value = tabId;
        };
        
        // 关闭Tab
        const closeTab = (tabId) => {
            const index = tabs.value.findIndex(tab => tab.id === tabId);
            if (index === -1) return;
            
            tabs.value.splice(index, 1);
            
            // 如果关闭的是当前激活的Tab，切换到其他Tab
            if (activeTabId.value === tabId) {
                if (tabs.value.length > 0) {
                    // 优先切换到右侧的Tab，如果没有则切换到左侧
                    const nextIndex = index < tabs.value.length ? index : index - 1;
                    activeTabId.value = tabs.value[nextIndex].id;
                } else {
                    activeTabId.value = null;
                }
            }
        };
        
        // 菜单选择处理
        const handleMenuSelect = (index) => {
            activeMenu.value = index;
            openTab(index);
        };
        
        // 提供Tab管理功能给子组件
        provide('tabManager', {
            closeTab: closeTab,
            getActiveTabId: () => activeTabId.value
        });
        
        // 初始化：默认打开聊天对话标签页
        onMounted(() => {
            if (tabs.value.length === 0) {
                openTab('chat');
                activeMenu.value = 'chat';
            }
        });
        
        return {
            tabs,
            activeTabId,
            activeMenu,
            openTab,
            switchTab,
            closeTab,
            handleMenuSelect
        };
    };
})();
