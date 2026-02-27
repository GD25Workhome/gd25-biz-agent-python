/**
 * JSON 编辑器演示组件
 * 展示 4 种 JSON 友好编辑方案，供数据清洗界面选择
 * 方案：01-Textarea / 02-JSONEditor / 03-Ace / 04-Monaco
 */
(function() {
    'use strict';

    const { defineComponent, ref, onMounted, onBeforeUnmount, nextTick } = Vue;
    const { ElMessage } = ElementPlus;
    const { parseJsonField } = window.PipelineCommon || {};

    const SAMPLE_JSON = JSON.stringify({
        sourceType: 'excel',
        sourcePath: { filePath: 'static/rag_source/uat_data/example.xlsx' },
        sheetNames: null,
        cleaners: { default: 'lsk', 'Sheet1': 'sh1128_multi' },
        dataSetsId: '01ARZ3NDEKTSV4RRFFQ69G5FAV'
    }, null, 2);

    window.PipelineJsonEditorsComponent = defineComponent({
        name: 'PipelineJsonEditorsComponent',
        setup() {
            const activeEditorTab = ref('01-Textarea');
            const initializedEditors = ref(new Set());

            // 01-Textarea
            const textareaContent = ref(SAMPLE_JSON);
            const textareaValid = ref(true);

            // 02-JSONEditor
            const jsonEditorContainer = ref(null);
            let jsonEditorInstance = null;

            // 03-Ace
            const aceContainer = ref(null);
            let aceEditorInstance = null;

            // 04-Monaco
            const monacoContainer = ref(null);
            let monacoEditorInstance = null;

            function init01Textarea() {
                if (initializedEditors.value.has('01-Textarea')) return;
                textareaContent.value = SAMPLE_JSON;
                textareaValid.value = true;
                initializedEditors.value.add('01-Textarea');
            }

            function formatTextarea() {
                const parsed = parseJsonField(textareaContent.value, 'JSON 格式错误，无法格式化');
                if (parsed !== undefined) {
                    textareaContent.value = JSON.stringify(parsed, null, 2);
                    textareaValid.value = true;
                    ElMessage.success('格式化成功');
                }
            }

            function validateTextarea() {
                const parsed = parseJsonField(textareaContent.value, '');
                textareaValid.value = parsed !== undefined;
                ElMessage[textareaValid.value ? 'success' : 'warning'](textareaValid.value ? 'JSON 格式正确' : 'JSON 格式错误');
            }

            function init02JSONEditor() {
                if (initializedEditors.value.has('02-JSONEditor') || !jsonEditorContainer.value) return;
                if (typeof window.JSONEditor === 'undefined') {
                    ElMessage.error('JSONEditor 库未加载');
                    return;
                }
                try {
                    let initialData = {};
                    try {
                        initialData = JSON.parse(SAMPLE_JSON);
                    } catch (_) {}
                    jsonEditorInstance = new window.JSONEditor(jsonEditorContainer.value, {
                        mode: 'tree',
                        modes: ['tree', 'code', 'text'],
                        search: true
                    });
                    jsonEditorInstance.set(initialData);
                    initializedEditors.value.add('02-JSONEditor');
                } catch (e) {
                    ElMessage.error('JSONEditor 初始化失败: ' + (e.message || e));
                }
            }

            function init03Ace() {
                if (initializedEditors.value.has('03-Ace') || !aceContainer.value) return;
                if (typeof window.ace === 'undefined') {
                    ElMessage.error('Ace Editor 库未加载');
                    return;
                }
                try {
                    aceEditorInstance = window.ace.edit(aceContainer.value);
                    aceEditorInstance.setTheme('ace/theme/chrome');
                    aceEditorInstance.session.setMode('ace/mode/json');
                    aceEditorInstance.setValue(SAMPLE_JSON, -1);
                    aceEditorInstance.setOptions({ fontSize: '13px' });
                    initializedEditors.value.add('03-Ace');
                } catch (e) {
                    ElMessage.error('Ace 初始化失败: ' + (e.message || e));
                }
            }

            function init04Monaco() {
                if (initializedEditors.value.has('04-Monaco') || !monacoContainer.value) return;
                if (typeof window.require === 'undefined') {
                    ElMessage.error('Monaco Editor 库未加载');
                    return;
                }
                window.require.config({
                    paths: {
                        vs: 'https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs'
                    },
                    'vs/nls': { availableLanguages: {} }
                });
                window.require(['vs/editor/editor.main'], function() {
                    if (!monacoContainer.value) return;
                    try {
                        monacoEditorInstance = window.monaco.editor.create(monacoContainer.value, {
                            value: SAMPLE_JSON,
                            language: 'json',
                            theme: 'vs',
                            automaticLayout: true,
                            minimap: { enabled: false },
                            fontSize: 13
                        });
                        initializedEditors.value.add('04-Monaco');
                    } catch (e) {
                        ElMessage.error('Monaco 初始化失败: ' + (e.message || e));
                    }
                });
            }

            function onTabChange(name) {
                activeEditorTab.value = name;
                nextTick(() => {
                    if (name === '01-Textarea') init01Textarea();
                    else if (name === '02-JSONEditor') init02JSONEditor();
                    else if (name === '03-Ace') init03Ace();
                    else if (name === '04-Monaco') init04Monaco();
                });
            }

            onMounted(() => {
                init01Textarea();
            });

            onBeforeUnmount(() => {
                if (jsonEditorInstance) {
                    try { jsonEditorInstance.destroy(); } catch (_) {}
                    jsonEditorInstance = null;
                }
                if (aceEditorInstance) {
                    try { aceEditorInstance.destroy(); } catch (_) {}
                    aceEditorInstance = null;
                }
                if (monacoEditorInstance) {
                    try { monacoEditorInstance.dispose(); } catch (_) {}
                    monacoEditorInstance = null;
                }
            });

            return {
                activeEditorTab,
                textareaContent,
                textareaValid,
                jsonEditorContainer,
                aceContainer,
                monacoContainer,
                formatTextarea,
                validateTextarea,
                onTabChange
            };
        },
        template: `
        <div style="height:100%;width:100%;min-width:0;display:flex;flex-direction:column;background:#fff;">
            <div style="padding:16px 20px;border-bottom:1px solid #e4e7ed;">
                <span style="font-weight:600;">JSON 编辑器方案对比</span>
                <span style="margin-left:12px;color:#909399;font-size:13px;">选择左侧 Tab 切换不同实现，便于对比选择</span>
            </div>
            <div style="flex:1;min-width:0;overflow:hidden;padding:16px;">
                <el-tabs v-model="activeEditorTab" @tab-change="onTabChange" type="border-card" style="height:100%;">
                    <el-tab-pane name="01-Textarea" label="JSON编辑器-01-Textarea">
                        <div style="height:calc(100vh - 220px);min-height:300px;">
                            <div style="margin-bottom:8px;display:flex;gap:8px;">
                                <el-button size="small" @click="formatTextarea">格式化</el-button>
                                <el-button size="small" @click="validateTextarea">校验</el-button>
                                <el-tag v-if="textareaValid" type="success" size="small">格式正确</el-tag>
                                <el-tag v-else type="danger" size="small">格式错误</el-tag>
                            </div>
                            <el-input v-model="textareaContent" type="textarea" :rows="20" placeholder="输入 JSON 字符串"
                                :class="{ 'is-error': !textareaValid }" style="font-family:monospace;font-size:13px;" />
                        </div>
                        <div style="margin-top:8px;color:#909399;font-size:12px;">
                            方案说明：Element Plus textarea + 格式化/校验按钮。零依赖，轻量，适合简单场景。
                        </div>
                    </el-tab-pane>
                    <el-tab-pane name="02-JSONEditor" label="JSON编辑器-02-JSONEditor">
                        <div style="height:calc(100vh - 220px);min-height:300px;">
                            <div ref="jsonEditorContainer" style="width:100%;height:100%;min-height:350px;"></div>
                        </div>
                        <div style="margin-top:8px;color:#909399;font-size:12px;">
                            方案说明：jsoneditor (josdejong)。树形/代码/文本模式切换，支持搜索、格式化、校验。功能丰富。
                        </div>
                    </el-tab-pane>
                    <el-tab-pane name="03-Ace" label="JSON编辑器-03-Ace">
                        <div style="height:calc(100vh - 220px);min-height:300px;">
                            <div ref="aceContainer" style="width:100%;height:100%;min-height:350px;"></div>
                        </div>
                        <div style="margin-top:8px;color:#909399;font-size:12px;">
                            方案说明：Ace Editor。代码高亮、行号、主题。轻量级代码编辑器，JSON 模式内置。
                        </div>
                    </el-tab-pane>
                    <el-tab-pane name="04-Monaco" label="JSON编辑器-04-Monaco">
                        <div style="height:calc(100vh - 220px);min-height:300px;">
                            <div ref="monacoContainer" style="width:100%;height:100%;min-height:350px;"></div>
                        </div>
                        <div style="margin-top:8px;color:#909399;font-size:12px;">
                            方案说明：Monaco Editor (VS Code 内核)。智能提示、折叠、多光标。功能最强，体积较大。
                        </div>
                    </el-tab-pane>
                </el-tabs>
            </div>
        </div>
        `
    });
})();
