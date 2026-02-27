/**
 * 血压范围情况帮助模块
 * 用于计算和展示各种血压评价对应的输入值
 */

(function() {
    'use strict';
    
    const { defineComponent, ref, reactive, computed } = Vue;
    const { ElMessage } = ElementPlus;

    window.BloodPressureHelpComponent = defineComponent({
        name: 'BloodPressureHelpComponent',
        props: {
            tabId: {
                type: String,
                required: true
            }
        },
        setup(props) {
            // 目标值
            const targetSBP = ref(130);
            const targetDBP = ref(80);
            
            // 规则说明
            const rules = [
                {
                    name: '达标',
                    condition: '90 ≤ SBP ≤ 目标值 且 DBP ≤ 目标值',
                    description: '血压在正常范围内'
                },
                {
                    name: '轻度偏高',
                    condition: '任一值超目标但未超+10mmHg',
                    description: '血压略高于目标值，但未超过10mmHg'
                },
                {
                    name: '中度偏高',
                    condition: '任一值超目标+10mmHg，但 SBP<180 且 DBP<110',
                    description: '血压明显高于目标值，但未达到重度偏高'
                },
                {
                    name: '重度偏高',
                    condition: 'SBP ≥ 180 或 DBP ≥ 110',
                    description: '血压严重偏高，需要紧急处理'
                },
                {
                    name: '低压偏低',
                    condition: '20 < DBP ≤ 60 且 DBP ≤ 目标值',
                    description: '舒张压偏低'
                },
                {
                    name: '高压偏低',
                    condition: '40 ≤ SBP < 90 且 SBP ≤ 目标值',
                    description: '收缩压偏低'
                }
            ];
            
            // 计算各种场景的示例输入值
            const scenarios = computed(() => {
                const sbpTarget = targetSBP.value;
                const dbpTarget = targetDBP.value;
                
                return [
                    {
                        name: '达标',
                        examples: [
                            {
                                sbp: Math.max(90, Math.floor(sbpTarget * 0.9)),
                                dbp: Math.floor(dbpTarget * 0.9),
                                description: '正常范围示例'
                            },
                            {
                                sbp: sbpTarget,
                                dbp: dbpTarget,
                                description: '刚好达到目标值'
                            },
                            {
                                sbp: Math.max(90, Math.floor((sbpTarget + 90) / 2)),
                                dbp: Math.floor((dbpTarget + 60) / 2),
                                description: '中等水平'
                            }
                        ],
                        condition: `90 ≤ SBP ≤ ${sbpTarget} 且 DBP ≤ ${dbpTarget}`
                    },
                    {
                        name: '轻度偏高',
                        examples: [
                            {
                                sbp: sbpTarget + 1,
                                dbp: dbpTarget,
                                description: '仅高压超目标'
                            },
                            {
                                sbp: sbpTarget,
                                dbp: dbpTarget + 1,
                                description: '仅低压超目标'
                            },
                            {
                                sbp: sbpTarget + 5,
                                dbp: dbpTarget + 5,
                                description: '两者都略超目标'
                            },
                            {
                                sbp: sbpTarget + 9,
                                dbp: dbpTarget + 9,
                                description: '接近中度偏高'
                            }
                        ],
                        condition: `任一值超目标但未超+10mmHg (SBP: ${sbpTarget + 1}-${sbpTarget + 10}, DBP: ${dbpTarget + 1}-${dbpTarget + 10})`
                    },
                    {
                        name: '中度偏高',
                        examples: [
                            {
                                sbp: sbpTarget + 11,
                                dbp: dbpTarget,
                                description: '仅高压超目标+10'
                            },
                            {
                                sbp: sbpTarget,
                                dbp: dbpTarget + 11,
                                description: '仅低压超目标+10'
                            },
                            {
                                sbp: sbpTarget + 20,
                                dbp: dbpTarget + 15,
                                description: '两者都明显超目标'
                            },
                            {
                                sbp: 179,
                                dbp: 109,
                                description: '接近重度偏高'
                            }
                        ],
                        condition: `任一值超目标+10mmHg，但 SBP<180 且 DBP<110 (SBP: ${sbpTarget + 11}-179, DBP: ${dbpTarget + 11}-109)`
                    },
                    {
                        name: '重度偏高',
                        examples: [
                            {
                                sbp: 180,
                                dbp: 90,
                                description: '高压达到重度偏高'
                            },
                            {
                                sbp: 150,
                                dbp: 110,
                                description: '低压达到重度偏高'
                            },
                            {
                                sbp: 185,
                                dbp: 115,
                                description: '两者都达到重度偏高'
                            },
                            {
                                sbp: 200,
                                dbp: 120,
                                description: '严重偏高'
                            }
                        ],
                        condition: 'SBP ≥ 180 或 DBP ≥ 110'
                    },
                    {
                        name: '低压偏低',
                        examples: [
                            {
                                sbp: sbpTarget,
                                dbp: 55,
                                description: '低压偏低示例'
                            },
                            {
                                sbp: sbpTarget,
                                dbp: 50,
                                description: '低压明显偏低'
                            },
                            {
                                sbp: sbpTarget,
                                dbp: 60,
                                description: '低压临界偏低'
                            },
                            {
                                sbp: sbpTarget,
                                dbp: 45,
                                description: '低压严重偏低'
                            }
                        ],
                        condition: `20 < DBP ≤ 60 且 DBP ≤ ${dbpTarget}`
                    },
                    {
                        name: '高压偏低',
                        examples: [
                            {
                                sbp: 85,
                                dbp: dbpTarget,
                                description: '高压偏低示例'
                            },
                            {
                                sbp: 80,
                                dbp: dbpTarget,
                                description: '高压明显偏低'
                            },
                            {
                                sbp: 89,
                                dbp: dbpTarget,
                                description: '高压临界偏低'
                            },
                            {
                                sbp: 70,
                                dbp: dbpTarget,
                                description: '高压严重偏低'
                            }
                        ],
                        condition: `40 ≤ SBP < 90 且 SBP ≤ ${sbpTarget}`
                    }
                ];
            });
            
            // 验证目标值是否合理
            const validateTargets = () => {
                if (targetSBP.value < 90 || targetSBP.value >= 170) {
                    ElMessage.warning('SBP目标值建议设置在90-169之间，以确保所有场景都能触发');
                }
                if (targetDBP.value < 60 || targetDBP.value >= 100) {
                    ElMessage.warning('DBP目标值建议设置在60-99之间，以确保所有场景都能触发');
                }
            };
            
            // 计算当前输入值对应的评价
            const calculateEvaluation = (sbp, dbp) => {
                const sbpTarget = targetSBP.value;
                const dbpTarget = targetDBP.value;
                
                // 重度偏高
                if (sbp >= 180 || dbp >= 110) {
                    return '重度偏高';
                }
                
                // 高压偏低
                if (sbp >= 40 && sbp < 90 && sbp <= sbpTarget) {
                    return '高压偏低';
                }
                
                // 低压偏低
                if (dbp > 20 && dbp <= 60 && dbp <= dbpTarget) {
                    return '低压偏低';
                }
                
                // 中度偏高
                if ((sbp > sbpTarget + 10 && sbp < 180) || (dbp > dbpTarget + 10 && dbp < 110)) {
                    return '中度偏高';
                }
                
                // 轻度偏高
                if ((sbp > sbpTarget && sbp <= sbpTarget + 10) || (dbp > dbpTarget && dbp <= dbpTarget + 10)) {
                    return '轻度偏高';
                }
                
                // 达标
                if (sbp >= 90 && sbp <= sbpTarget && dbp <= dbpTarget) {
                    return '达标';
                }
                
                return '未知';
            };
            
            // 测试输入值
            const testSBP = ref(null);
            const testDBP = ref(null);
            const testResult = computed(() => {
                if (testSBP.value === null || testSBP.value === '' || 
                    testDBP.value === null || testDBP.value === '') {
                    return null;
                }
                const sbp = Number(testSBP.value);
                const dbp = Number(testDBP.value);
                if (isNaN(sbp) || isNaN(dbp)) {
                    return null;
                }
                return calculateEvaluation(sbp, dbp);
            });
            
            return {
                targetSBP,
                targetDBP,
                rules,
                scenarios,
                validateTargets,
                testSBP,
                testDBP,
                testResult
            };
        },
        template: `
            <div style="padding: 20px; height: 100%; overflow-y: auto; background: #f5f7fa;">
                <el-card shadow="never" style="margin-bottom: 20px;">
                    <template #header>
                        <div style="display: flex; align-items: center; justify-content: space-between;">
                            <h2 style="margin: 0; font-size: 18px;">血压评价规则说明</h2>
                        </div>
                    </template>
                    <div style="line-height: 1.8;">
                        <div v-for="(rule, index) in rules" :key="index" style="margin-bottom: 15px; padding: 12px; background: #f9fafb; border-radius: 4px; border-left: 3px solid #409eff;">
                            <div style="font-weight: 600; color: #303133; margin-bottom: 5px;">
                                <el-tag type="success" size="small" style="margin-right: 8px;">{{ rule.name }}</el-tag>
                            </div>
                            <div style="color: #606266; font-size: 13px; margin-bottom: 3px;">
                                <strong>条件：</strong>{{ rule.condition }}
                            </div>
                            <div style="color: #909399; font-size: 12px;">
                                {{ rule.description }}
                            </div>
                        </div>
                    </div>
                </el-card>
                
                <el-card shadow="never" style="margin-bottom: 20px;">
                    <template #header>
                        <h2 style="margin: 0; font-size: 18px;">目标值设置</h2>
                    </template>
                    <el-form :inline="true" label-width="120px">
                        <el-form-item label="SBP目标值 (mmHg)">
                            <el-input-number 
                                v-model="targetSBP" 
                                :min="80" 
                                :max="200" 
                                :step="1"
                                @change="validateTargets"
                                style="width: 150px;"
                            ></el-input-number>
                            <span style="margin-left: 10px; color: #909399; font-size: 12px;">建议范围：90-169</span>
                        </el-form-item>
                        <el-form-item label="DBP目标值 (mmHg)">
                            <el-input-number 
                                v-model="targetDBP" 
                                :min="50" 
                                :max="120" 
                                :step="1"
                                @change="validateTargets"
                                style="width: 150px;"
                            ></el-input-number>
                            <span style="margin-left: 10px; color: #909399; font-size: 12px;">建议范围：60-99</span>
                        </el-form-item>
                        <el-form-item>
                            <el-button type="primary" @click="validateTargets">验证目标值</el-button>
                        </el-form-item>
                    </el-form>
                    <el-alert 
                        type="info" 
                        :closable="false" 
                        style="margin-top: 15px;"
                    >
                        <template #default>
                            <div style="font-size: 13px;">
                                <strong>推荐设置：</strong>SBP目标值 = 130，DBP目标值 = 80<br>
                                这样可以确保所有血压评价场景都能正常触发。
                            </div>
                        </template>
                    </el-alert>
                </el-card>
                
                <el-card shadow="never" style="margin-bottom: 20px;">
                    <template #header>
                        <h2 style="margin: 0; font-size: 18px;">各场景示例输入值</h2>
                    </template>
                    <div v-for="(scenario, index) in scenarios" :key="index" style="margin-bottom: 25px;">
                        <div style="margin-bottom: 10px;">
                            <el-tag 
                                :type="scenario.name === '达标' ? 'success' : 
                                       scenario.name === '轻度偏高' ? 'warning' : 
                                       scenario.name === '中度偏高' ? 'warning' : 
                                       scenario.name === '重度偏高' ? 'danger' : 'info'" 
                                size="large"
                                style="font-size: 14px; padding: 5px 15px;"
                            >
                                {{ scenario.name }}
                            </el-tag>
                            <span style="margin-left: 10px; color: #606266; font-size: 13px;">{{ scenario.condition }}</span>
                        </div>
                        <el-table 
                            :data="scenario.examples" 
                            border 
                            size="small"
                            style="margin-top: 10px;"
                        >
                            <el-table-column prop="sbp" label="SBP (mmHg)" width="120" align="center"></el-table-column>
                            <el-table-column prop="dbp" label="DBP (mmHg)" width="120" align="center"></el-table-column>
                            <el-table-column prop="description" label="说明"></el-table-column>
                            <el-table-column label="操作" width="100" align="center">
                                <template #default="{ row }">
                                    <el-button 
                                        size="small" 
                                        type="primary" 
                                        link
                                        @click="testSBP = row.sbp; testDBP = row.dbp"
                                    >
                                        测试
                                    </el-button>
                                </template>
                            </el-table-column>
                        </el-table>
                    </div>
                </el-card>
                
                <el-card shadow="never">
                    <template #header>
                        <h2 style="margin: 0; font-size: 18px;">测试输入值</h2>
                    </template>
                    <el-form :inline="true" label-width="120px">
                        <el-form-item label="SBP (mmHg)">
                            <el-input-number 
                                v-model="testSBP" 
                                :min="40" 
                                :max="250" 
                                :step="1"
                                style="width: 150px;"
                                placeholder="输入高压值"
                            ></el-input-number>
                        </el-form-item>
                        <el-form-item label="DBP (mmHg)">
                            <el-input-number 
                                v-model="testDBP" 
                                :min="20" 
                                :max="150" 
                                :step="1"
                                style="width: 150px;"
                                placeholder="输入低压值"
                            ></el-input-number>
                        </el-form-item>
                    </el-form>
                    <div v-if="testResult" style="margin-top: 20px;">
                        <el-alert 
                            :type="testResult === '达标' ? 'success' : 
                                   testResult === '轻度偏高' || testResult === '中度偏高' ? 'warning' : 
                                   testResult === '重度偏高' ? 'error' : 'info'" 
                            :closable="false"
                        >
                            <template #default>
                                <div style="font-size: 16px;">
                                    <strong>评价结果：</strong>
                                    <el-tag 
                                        :type="testResult === '达标' ? 'success' : 
                                               testResult === '轻度偏高' || testResult === '中度偏高' ? 'warning' : 
                                               testResult === '重度偏高' ? 'danger' : 'info'" 
                                        size="large"
                                        style="margin-left: 10px; font-size: 14px;"
                                    >
                                        {{ testResult }}
                                    </el-tag>
                                </div>
                                <div style="margin-top: 10px; font-size: 13px; color: #606266;">
                                    输入值：{{ testSBP }}/{{ testDBP }} mmHg<br>
                                    目标值：{{ targetSBP }}/{{ targetDBP }} mmHg
                                </div>
                            </template>
                        </el-alert>
                    </div>
                    <div v-else-if="testSBP !== null && testDBP !== null && !testResult" style="margin-top: 20px;">
                        <el-alert type="warning" :closable="false">
                            请输入有效的血压值
                        </el-alert>
                    </div>
                </el-card>
            </div>
        `
    });
})();
