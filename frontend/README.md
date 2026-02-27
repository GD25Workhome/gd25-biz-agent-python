# 前端模块化架构说明

## 文件结构

```
frontend/
├── index.html          # 主框架文件，包含整体布局和Tab页管理
├── js/
│   ├── framework.js    # 框架管理模块（Tab页管理、菜单导航）
│   ├── chat.js         # 聊天对话模块
│   ├── blood-pressure.js # 血压记录管理模块
│   └── users.js        # 用户管理模块
└── README.md           # 本文件
```

## 功能特性

### 1. 模块化设计
- **framework.js**: 负责整体框架管理，包括Tab页的打开、关闭、切换等
- **chat.js**: 独立的聊天对话组件
- **blood-pressure.js**: 独立的血压记录管理组件
- **users.js**: 独立的用户管理组件

### 2. 浏览器式Tab页
- 点击左侧菜单会在中间区域打开新的Tab页
- 支持多个Tab页同时打开
- 每个Tab页可以独立关闭
- Tab页标题显示功能名称

### 3. 聊天功能
- 支持多轮对话
- 支持流程选择（医疗分身Agent/工作计划Agent）
- 支持 Ctrl+Enter 或 Cmd+Enter 快速发送
- 发送按钮清晰可见，带图标和文字
- 自动滚动到最新消息

### 4. 数据管理
- 血压记录：完整的CRUD功能，支持筛选、排序
- 用户管理：完整的CRUD功能，支持JSON格式用户信息

## 使用说明

1. 直接打开 `index.html` 即可使用（无需构建工具）
2. 确保后端服务运行在 `http://localhost:8000`
3. 点击左侧菜单打开对应的功能页面
4. 每个功能页面以Tab页形式显示，可以同时打开多个

## 技术栈

- Vue 3 (Composition API) - 通过 CDN 引入
- Element Plus - UI组件库
- Element Plus Icons - 图标库
- Axios - HTTP请求库

## 扩展说明

### 添加新功能模块

1. 在 `js/` 目录下创建新的模块文件（如 `new-feature.js`）
2. 使用 `defineComponent` 定义组件
3. 在 `index.html` 中引入脚本
4. 在 `framework.js` 的 `tabConfigs` 中添加配置
5. 在主应用的 `components` 中注册组件

### 示例：添加新模块

```javascript
// js/new-feature.js
const NewFeatureComponent = defineComponent({
    name: 'NewFeatureComponent',
    props: {
        tabId: { type: String, required: true }
    },
    setup(props) {
        // 组件逻辑
        return {};
    },
    template: `<div>新功能内容</div>`
});
```

然后在 `framework.js` 中添加：
```javascript
const tabConfigs = {
    // ... 其他配置
    'new-feature': {
        title: '新功能',
        component: 'NewFeatureComponent',
        icon: 'Setting'
    }
};
```

