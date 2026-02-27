# JSONEditor 在 Drawer 内布局问题说明

## 问题现象

在数据清洗界面的 Drawer 弹窗中，PipelineJsonEditor 组件出现布局异常：

1. **内容右对齐**：树形视图中的 `object`、`{5}` 等文本显示在右侧（left=1317px）
2. **td 过宽**：`td.jsoneditor-tree` 宽度达到 1076px，占用过多空间
3. **对比**：JSON 编辑器方案对比页中的 02-JSONEditor 显示正常

## 根本原因分析

### 1. JSONEditor 内部布局依赖

jsoneditor 库的 CSS 中，树形视图使用 `float: left` 布局：

```css
/* jsoneditor 源码 */
div.jsoneditor-field, div.jsoneditor-value { float: left; ... }
```

### 2. RTL 对 float 的影响

当父元素 `direction: rtl` 时，在 RTL 上下文中：

- `float: left` 会浮到**物理右侧**
- 表格列顺序会反转
- 导致树形视图内容整体右对齐、列宽错乱

### 3. Element Plus Drawer 的 direction

- `direction="rtl"`：Drawer 从右侧滑入，同时 `el-drawer` 带有 `rtl` 类
- 该 RTL 上下文会继承到 Drawer 内部所有内容
- JSONEditor 的 float 布局在 RTL 下被错误渲染

### 4. 为什么 02-JSONEditor 正常

02-JSONEditor 在 `el-tabs` 内，不在 Drawer 中，其父级为 LTR 上下文，不受影响。

## 解决方案

### 方案 A：Drawer 使用 direction="ltr"（未生效）

将 Drawer 的 `direction` 改为 `ltr` 后，布局问题仍存在。

### 方案 B：iframe 隔离（未生效）

在 iframe 内渲染 JSONEditor 时，父窗口 JSONEditor 创建的 DOM 无法 append 到 iframe 的 document（跨文档错误）；若在 iframe 内加载脚本，存在 CSP、加载时序等问题。

### 方案 C：改用 el-dialog（未完全解决）

将弹窗从 `el-drawer` 改为 `el-dialog` 后，部分场景仍有布局异常。

### 方案 D：textarea + 独立 JSON 编辑弹窗（已采用）

表单中不再内嵌 JSON 编辑器，改为：

1. **多行文本**：用只读 textarea 显示原始 JSON 字符串
2. **「JSON 编辑器」按钮**：点击后打开独立弹窗
3. **独立弹窗**：使用 PipelineJsonEditor 编辑，确定后回填到原字段，取消则放弃

- **效果**：JSON 编辑器仅在独立弹窗中展示，无 RTL/布局问题
- **实现**：新增 `PipelineJsonField` 组件，封装 textarea + 按钮 + 编辑弹窗
- **优点**：表单简洁，编辑体验与 02-JSONEditor 一致

## 修改文件

| 文件 | 修改 |
|------|------|
| `pipeline_json_field.js` | 新增：textarea + 按钮 + JSON 编辑弹窗 |
| `pipeline_import_manage.js` | 使用 PipelineJsonField 替代 PipelineJsonEditor |
| `pipeline_set_view.js` | 三个 JSON 字段使用 PipelineJsonField |
| `pipeline_dataset_items.js` | 三个 JSON 字段使用 PipelineJsonField |
| `data-cleaning.html` | 引入 pipeline_json_field.js，注册 PipelineJsonField |

## 参考

- 设计文档：`cursor_docs/020501-JSON编辑器方案对比.md`
- 数据导入：`cursor_docs/020402-数据导入流程技术设计.md`
