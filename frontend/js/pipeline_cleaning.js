/**
 * 数据清洗主框架
 * 负责 Tab 页管理、菜单导航
 * 设计文档：cursor_docs/020401-数据导入管理模块技术设计.md
 */
(function() {
    'use strict';

    const { ref, provide, onMounted } = Vue;
    const { ElMessage } = ElementPlus;

    window.usePipelineCleaning = function() {
        const tabs = ref([]);
        const activeTabId = ref(null);
        const activeMenu = ref('');

        const tabConfigs = {
            'import-manage': { title: 'Step00导入管理', component: 'PipelineImportManageComponent', icon: 'Upload' },
            'set-view': { title: 'Step01原始数据管理', component: 'PipelineSetViewComponent', icon: 'FolderOpened' },
            'step01-items-standalone': { title: 'Step01原始数据项管理', component: 'Step01DataItemsStandalone', icon: 'Document' },
            'rewritten-batches': { title: 'Step02清洗批次管理', component: 'PipelineRewrittenBatchesComponent', icon: 'Document' },
            'data-items-rewritten': { title: 'Step02数据清洗管理', component: 'PipelineDataItemsRewrittenComponent', icon: 'Edit' },
            'embedding-batches': { title: 'Step03批量创建Embedding', component: 'PipelineEmbeddingBatchComponent', icon: 'Document' },
            'batch-jobs': { title: 'Step03-1批次任务管理', component: 'PipelineBatchJobsComponent', icon: 'Document' }
        };

        const generateTabId = (type) => `${type}_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`;

        const openTab = (type) => {
            const config = tabConfigs[type];
            if (!config) {
                ElMessage.warning('未知的功能类型');
                return;
            }
            const existingTab = tabs.value.find(tab => tab.type === type);
            if (existingTab) {
                activeTabId.value = existingTab.id;
                return;
            }
            const tabId = generateTabId(type);
            tabs.value.push({ id: tabId, type: type, title: config.title, component: config.component, icon: config.icon });
            activeTabId.value = tabId;
        };

        /** 打开数据集数据项管理 Tab，标题为「XX数据集名称-数据项管理」 */
        const openTabForDatasetItems = (datasetId, datasetName) => {
            const tabTitle = `${datasetName || '数据集'}-数据项管理`;
            const existingTab = tabs.value.find(tab => tab.type === 'dataset-items' && tab.datasetId === datasetId);
            if (existingTab) {
                activeTabId.value = existingTab.id;
                return;
            }
            const tabId = generateTabId('dataset-items');
            tabs.value.push({
                id: tabId,
                type: 'dataset-items',
                title: tabTitle,
                component: 'PipelineDatasetItemsComponent',
                icon: 'Document',
                datasetId,
                datasetName
            });
            activeTabId.value = tabId;
        };

        /** 打开批次 job 下任务列表 Tab，标题为「批次编码-任务列表」（风格参考 Step01 数据项） */
        const openTabForJobTasks = (jobId, jobCode) => {
            const tabTitle = `${jobCode || jobId || '批次'}-任务列表`;
            const existingTab = tabs.value.find(tab => tab.type === 'job-tasks' && tab.jobId === jobId);
            if (existingTab) {
                activeTabId.value = existingTab.id;
                return;
            }
            const tabId = generateTabId('job-tasks');
            tabs.value.push({
                id: tabId,
                type: 'job-tasks',
                title: tabTitle,
                component: 'PipelineBatchJobTasksComponent',
                icon: 'Document',
                jobId,
                jobCode
            });
            activeTabId.value = tabId;
        };

        const switchTab = (tabId) => { activeTabId.value = tabId; };

        const closeTab = (tabId) => {
            const index = tabs.value.findIndex(tab => tab.id === tabId);
            if (index === -1) return;
            tabs.value.splice(index, 1);
            if (activeTabId.value === tabId) {
                activeTabId.value = tabs.value.length > 0 ? tabs.value[Math.min(index, tabs.value.length - 1)].id : null;
            }
        };

        const handleMenuSelect = (index) => {
            activeMenu.value = index;
            openTab(index);
        };

        provide('pipelineTabManager', { closeTab, getActiveTabId: () => activeTabId.value, openTabForDatasetItems, openTabForJobTasks });

        onMounted(() => {
            if (tabs.value.length === 0) {
                openTab('import-manage');
                activeMenu.value = 'import-manage';
            }
        });

        return { tabs, activeTabId, activeMenu, openTab, openTabForDatasetItems, switchTab, closeTab, handleMenuSelect };
    };
})();
