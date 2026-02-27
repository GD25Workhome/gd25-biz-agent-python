/**
 * 知识库查询页面
 * 设计文档：cursor_docs/012803-知识库表与前端查询界面设计.md
 * 功能：左模糊查询（场景摘要、优化问题、场景分类、输入标签、回复标签）、分页列表
 */
(function() {
    'use strict';

    const { defineComponent, ref, reactive, onMounted, computed } = Vue;
    const { ElMessage } = ElementPlus;
    const icons = ElementPlusIconsVue;

    const API_BASE = typeof window !== 'undefined' && window.location && window.location.origin
        ? window.location.origin
        : 'http://localhost:8000';

    const PAGE_SIZE_OPTIONS = [10, 20, 50, 100];

    window.KnowledgeBasePage = defineComponent({
        name: 'KnowledgeBasePage',
        setup() {
            const items = ref([]);
            const total = ref(0);
            const loading = ref(false);

            const sceneSummary = ref('');
            const optimizationQuestion = ref('');
            const sceneCategory = ref('');
            const inputTags = ref('');
            const responseTags = ref('');

            const limit = ref(20);
            const offset = ref(0);

            const currentPage = computed(() =>
                limit.value > 0 ? Math.floor(offset.value / limit.value) + 1 : 1
            );
            const totalPages = computed(() =>
                limit.value > 0 ? Math.max(1, Math.ceil(total.value / limit.value)) : 1
            );

            function truncate(str, maxLen = 60) {
                if (str == null || str === '') return '-';
                const s = String(str);
                return s.length <= maxLen ? s : s.slice(0, maxLen) + '…';
            }

            function formatDateTime(dateTimeStr) {
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
            }

            function renderTags(arr) {
                if (!Array.isArray(arr) || arr.length === 0) return '-';
                return arr.map(t => (typeof t === 'string' ? t : JSON.stringify(t)));
            }

            async function loadList() {
                loading.value = true;
                try {
                    const params = new URLSearchParams();
                    params.set('limit', String(limit.value));
                    params.set('offset', String(offset.value));
                    if (sceneSummary.value && sceneSummary.value.trim())
                        params.set('scene_summary', sceneSummary.value.trim());
                    if (optimizationQuestion.value && optimizationQuestion.value.trim())
                        params.set('optimization_question', optimizationQuestion.value.trim());
                    if (sceneCategory.value && sceneCategory.value.trim())
                        params.set('scene_category', sceneCategory.value.trim());
                    if (inputTags.value && inputTags.value.trim())
                        params.set('input_tags', inputTags.value.trim());
                    if (responseTags.value && responseTags.value.trim())
                        params.set('response_tags', responseTags.value.trim());

                    const url = `${API_BASE}/api/v1/knowledge-base?${params.toString()}`;
                    const res = await axios.get(url);
                    items.value = res.data.items || [];
                    total.value = res.data.total != null ? res.data.total : 0;
                } catch (err) {
                    console.error(err);
                    ElMessage.error('加载列表失败: ' + (err.response?.data?.detail || err.message));
                    items.value = [];
                    total.value = 0;
                } finally {
                    loading.value = false;
                }
            }

            function onSearch() {
                offset.value = 0;
                loadList();
            }

            function onRefresh() {
                loadList();
            }

            function onPageChange(page) {
                offset.value = (page - 1) * limit.value;
                loadList();
            }

            function onSizeChange() {
                offset.value = 0;
                loadList();
            }

            onMounted(() => {
                loadList();
            });

            return {
                items,
                total,
                loading,
                sceneSummary,
                optimizationQuestion,
                sceneCategory,
                inputTags,
                responseTags,
                limit,
                offset,
                currentPage,
                totalPages,
                PAGE_SIZE_OPTIONS,
                truncate,
                formatDateTime,
                renderTags,
                loadList,
                onSearch,
                onRefresh,
                onPageChange,
                onSizeChange,
                Search: icons.Search,
                Refresh: icons.Refresh,
                ArrowLeft: icons.ArrowLeft,
                ArrowRight: icons.ArrowRight
            };
        },
        template: `
        <div style="height: 100%; display: flex; flex-direction: column; background: #fff;">
            <!-- 查询区域 -->
            <div style="padding: 16px 20px; border-bottom: 1px solid #e4e7ed;">
                <div style="display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-start;">
                    <el-input
                        v-model="sceneSummary"
                        placeholder="场景摘要（左模糊）"
                        clearable
                        style="width: 180px;"
                    />
                    <el-input
                        v-model="optimizationQuestion"
                        placeholder="优化问题（左模糊）"
                        clearable
                        style="width: 180px;"
                    />
                    <el-input
                        v-model="sceneCategory"
                        placeholder="场景分类（左模糊）"
                        clearable
                        style="width: 160px;"
                    />
                    <el-input
                        v-model="inputTags"
                        placeholder="输入标签（左模糊）"
                        clearable
                        style="width: 160px;"
                    />
                    <el-input
                        v-model="responseTags"
                        placeholder="回复标签（左模糊）"
                        clearable
                        style="width: 160px;"
                    />
                    <el-button type="primary" @click="onSearch" :icon="Search">查询</el-button>
                    <el-button @click="onRefresh" :icon="Refresh">刷新</el-button>
                </div>
            </div>

            <!-- 表格 -->
            <div style="flex: 1; overflow: auto; padding: 20px;">
                <el-table
                    :data="items"
                    v-loading="loading"
                    stripe
                    border
                    style="width: 100%"
                >
                    <el-table-column prop="id" label="ID" width="120" show-overflow-tooltip />
                    <el-table-column label="场景摘要" min-width="140">
                        <template #default="scope">
                            {{ truncate(scope.row.scene_summary, 50) }}
                        </template>
                    </el-table-column>
                    <el-table-column label="优化问题" min-width="140">
                        <template #default="scope">
                            {{ truncate(scope.row.optimization_question, 50) }}
                        </template>
                    </el-table-column>
                    <el-table-column prop="scene_category" label="场景分类" width="120" show-overflow-tooltip />
                    <el-table-column label="输入标签" width="140">
                        <template #default="scope">
                            <div class="tag-array" v-if="scope.row.input_tags && scope.row.input_tags.length">
                                <el-tag v-for="(t, i) in scope.row.input_tags" :key="i" size="small">{{ t }}</el-tag>
                            </div>
                            <span v-else>-</span>
                        </template>
                    </el-table-column>
                    <el-table-column label="回复标签" width="140">
                        <template #default="scope">
                            <div class="tag-array" v-if="scope.row.response_tags && scope.row.response_tags.length">
                                <el-tag v-for="(t, i) in scope.row.response_tags" :key="i" size="small" type="info">{{ t }}</el-tag>
                            </div>
                            <span v-else>-</span>
                        </template>
                    </el-table-column>
                    <el-table-column label="创建时间" width="160">
                        <template #default="scope">
                            {{ formatDateTime(scope.row.created_at) }}
                        </template>
                    </el-table-column>
                    <el-table-column type="expand" width="48">
                        <template #default="props">
                            <div style="padding: 12px 24px;">
                                <p v-if="props.row.reply_example_or_rule"><strong>回复示例或规则：</strong>{{ props.row.reply_example_or_rule }}</p>
                                <div v-if="props.row.technical_tag_classification && Object.keys(props.row.technical_tag_classification).length"><strong>技术标记分类：</strong><pre style="margin:4px 0;font-size:12px;">{{ JSON.stringify(props.row.technical_tag_classification, null, 2) }}</pre></div>
                                <div v-if="props.row.business_tag_classification && Object.keys(props.row.business_tag_classification).length"><strong>业务标记分类：</strong><pre style="margin:4px 0;font-size:12px;">{{ JSON.stringify(props.row.business_tag_classification, null, 2) }}</pre></div>
                            </div>
                        </template>
                    </el-table-column>
                </el-table>
            </div>

            <!-- 分页 -->
            <div style="padding: 12px 20px; border-top: 1px solid #e4e7ed; display: flex; align-items: center; justify-content: space-between;">
                <span style="color: #606266; font-size: 13px;">
                    共 {{ total }} 条，每页
                    <el-select v-model="limit" size="small" style="width: 80px; margin: 0 4px;" @change="onSizeChange()">
                        <el-option v-for="s in PAGE_SIZE_OPTIONS" :key="s" :label="s" :value="s" />
                    </el-select>
                    条
                </span>
                <el-pagination
                    :current-page="currentPage"
                    :page-size="limit"
                    :total="total"
                    layout="prev, pager, next"
                    @current-change="onPageChange"
                />
            </div>
        </div>
        `
    });
})();
