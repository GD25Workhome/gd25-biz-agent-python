/**
 * 流程预览模块
 */

(function() {
    'use strict';
    
    const { defineComponent, ref, reactive, onMounted, nextTick } = Vue;
    const { ElMessage, ElMessageBox, ElLoading } = ElementPlus;
    const icons = ElementPlusIconsVue;

    window.FlowPreviewComponent = defineComponent({
        name: 'FlowPreviewComponent',
        props: {
            tabId: {
                type: String,
                required: true
            }
        },
        setup(props) {
            const API_BASE = 'http://localhost:8000';
            const FLOWS_API_URL = `${API_BASE}/api/v1/flows`;
            
            // 流程列表数据
            const flowList = ref([]);
            const loading = ref(false);
            const selectedFlow = ref(null);
            const previewImageUrl = ref('');
            const generatingPreview = ref(false);
            
            // 加载流程列表
            const loadFlowList = async () => {
                loading.value = true;
                try {
                    const resp = await fetch(FLOWS_API_URL);
                    if (!resp.ok) throw new Error('加载流程列表失败');
                    const data = await resp.json();
                    flowList.value = data || [];
                } catch (e) {
                    console.error('加载流程列表失败:', e);
                    ElMessage.error('加载流程列表失败: ' + e.message);
                } finally {
                    loading.value = false;
                }
            };
            
            // 生成流程图预览
            const generatePreview = async (flowName, force = false) => {
                generatingPreview.value = true;
                try {
                    const url = `${FLOWS_API_URL}/${flowName}/preview${force ? '?force=true' : ''}`;
                    const resp = await fetch(url);
                    if (!resp.ok) throw new Error('生成流程图失败');
                    
                    // 获取图片URL（使用blob URL或直接使用API URL）
                    const blob = await resp.blob();
                    previewImageUrl.value = URL.createObjectURL(blob);
                    
                    ElMessage.success('流程图生成成功');
                } catch (e) {
                    console.error('生成流程图失败:', e);
                    ElMessage.error('生成流程图失败: ' + e.message);
                } finally {
                    generatingPreview.value = false;
                }
            };
            
            // 选择流程
            const selectFlow = async (flow) => {
                selectedFlow.value = flow;
                previewImageUrl.value = '';
                
                // 如果已有预览图片路径，直接使用
                if (flow.preview_image_path) {
                    previewImageUrl.value = `${API_BASE}${flow.preview_image_path}`;
                } else {
                    // 否则生成预览图
                    await generatePreview(flow.name, false);
                }
            };
            
            // 重新生成流程图
            const regeneratePreview = async () => {
                if (!selectedFlow.value) return;
                await generatePreview(selectedFlow.value.name, true);
            };
            
            // 初始化
            onMounted(async () => {
                await loadFlowList();
                // 默认选择第一个流程
                if (flowList.value.length > 0) {
                    await selectFlow(flowList.value[0]);
                }
            });
            
            return {
                flowList,
                loading,
                selectedFlow,
                previewImageUrl,
                generatingPreview,
                loadFlowList,
                selectFlow,
                regeneratePreview
            };
        },
        template: `
            <div style="height: 100%; display: flex; flex-direction: column; background: #f5f7fa;">
                <!-- 头部工具栏 -->
                <div style="padding: 16px 20px; background: #fff; border-bottom: 1px solid #e4e7ed;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <h2 style="margin: 0; font-size: 18px; color: #303133;">流程预览</h2>
                        <div style="display: flex; gap: 12px;">
                            <el-button 
                                @click="loadFlowList" 
                                :loading="loading"
                                size="small"
                            >
                                <el-icon style="margin-right: 4px;"><Refresh /></el-icon>
                                刷新列表
                            </el-button>
                            <el-button 
                                v-if="selectedFlow"
                                @click="regeneratePreview" 
                                :loading="generatingPreview"
                                type="primary"
                                size="small"
                            >
                                <el-icon style="margin-right: 4px;"><Refresh /></el-icon>
                                重新生成流程图
                            </el-button>
                        </div>
                    </div>
                </div>
                
                <!-- 主体内容 -->
                <div style="flex: 1; display: flex; overflow: hidden;">
                    <!-- 左侧流程列表 -->
                    <div style="width: 300px; background: #fff; border-right: 1px solid #e4e7ed; overflow-y: auto;">
                        <div v-if="loading" style="padding: 20px; text-align: center; color: #909399;">
                            加载中...
                        </div>
                        <div v-else-if="flowList.length === 0" style="padding: 20px; text-align: center; color: #909399;">
                            暂无流程
                        </div>
                        <div v-else style="padding: 12px;">
                            <div
                                v-for="flow in flowList"
                                :key="flow.name"
                                @click="selectFlow(flow)"
                                style="padding: 12px; border: 1px solid #e4e7ed; border-radius: 8px; margin-bottom: 8px; cursor: pointer; transition: all 0.2s;"
                                :style="selectedFlow && selectedFlow.name === flow.name ? 'background: #e0f2fe; border-color: #409eff;' : ''"
                                @mouseenter="$event.currentTarget.style.background = (selectedFlow && selectedFlow.name === flow.name) ? '#e0f2fe' : '#f3f4f6'"
                                @mouseleave="$event.currentTarget.style.background = (selectedFlow && selectedFlow.name === flow.name) ? '#e0f2fe' : '#fff'"
                            >
                                <div style="font-weight: bold; margin-bottom: 4px; color: #303133;">{{ flow.description || flow.name }}</div>
                                <div style="font-size: 12px; color: #909399; margin-bottom: 4px;">
                                    名称: {{ flow.name }} | 版本: {{ flow.version }}
                                </div>
                                <div style="font-size: 12px; color: #909399;">
                                    <span :style="flow.is_compiled ? 'color: #67c23a;' : 'color: #e6a23c;'">
                                        {{ flow.is_compiled ? '✓ 已编译' : '○ 未编译' }}
                                    </span>
                                    <span v-if="flow.preview_image_path" style="margin-left: 8px; color: #67c23a;">
                                        ✓ 有预览图
                                    </span>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- 右侧流程图预览 -->
                    <div style="flex: 1; background: #fff; display: flex; flex-direction: column; overflow: hidden;">
                        <div v-if="!selectedFlow" style="flex: 1; display: flex; align-items: center; justify-content: center; color: #909399;">
                            <div style="text-align: center;">
                                <div style="font-size: 48px; margin-bottom: 16px;">📊</div>
                                <div>请选择流程查看流程图</div>
                            </div>
                        </div>
                        <div v-else style="flex: 1; padding: 20px; overflow: auto;">
                            <!-- 流程信息 -->
                            <div style="margin-bottom: 20px; padding: 16px; background: #f5f7fa; border-radius: 8px;">
                                <h3 style="margin: 0 0 8px 0; color: #303133;">{{ selectedFlow.description || selectedFlow.name }}</h3>
                                <div style="font-size: 14px; color: #606266;">
                                    <div>流程名称: {{ selectedFlow.name }}</div>
                                    <div>版本: {{ selectedFlow.version }}</div>
                                    <div v-if="selectedFlow.description">描述: {{ selectedFlow.description }}</div>
                                </div>
                            </div>
                            
                            <!-- 流程图预览 -->
                            <div v-if="generatingPreview" style="text-align: center; padding: 40px; color: #909399;">
                                <el-icon class="is-loading" style="font-size: 32px; margin-bottom: 16px;"><Loading /></el-icon>
                                <div>正在生成流程图...</div>
                            </div>
                            <div v-else-if="previewImageUrl" style="text-align: center;">
                                <img 
                                    :src="previewImageUrl" 
                                    alt="流程图预览"
                                    style="max-width: 100%; border: 1px solid #e4e7ed; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);"
                                />
                            </div>
                            <div v-else style="text-align: center; padding: 40px; color: #909399;">
                                <div style="font-size: 48px; margin-bottom: 16px;">📋</div>
                                <div>流程图预览不可用</div>
                                <el-button @click="regeneratePreview" type="primary" style="margin-top: 16px;">
                                    生成流程图
                                </el-button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `,
        components: {
            Refresh: icons.Refresh,
            Loading: icons.Loading
        }
    });
})();

