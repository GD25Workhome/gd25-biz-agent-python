# JSON Schema 技术指导文档

> 基于 [JSON Schema - Miscellaneous Examples](https://json-schema.org/learn/miscellaneous-examples) 整理，涵盖常见场景与最佳实践。

## 一、概述

JSON Schema 是一种用于描述和验证 JSON 数据结构的声明式语言。本文档整理了官方示例中的核心概念与典型用法，便于在项目中快速查阅和应用。

**规范版本**：本文档示例基于 JSON Schema Draft 2020-12。

---

## 二、基础 Schema 结构

### 2.1 最小化 Schema 示例

一个典型的基础 Schema 通常包含以下关键字：

| 关键字 | 用途 |
|--------|------|
| `$id` | Schema 的唯一标识符（URI） |
| `$schema` | 声明使用的 JSON Schema 规范版本 |
| `title` | 注解关键字，用于文档说明 |
| `type` | 定义实例数据类型 |
| `properties` | 对象属性定义 |
| `description` | 属性/类型的描述注解 |
| `minimum` | 数值最小值约束 |

**示例**：

```json
{
  "$id": "https://example.com/person.schema.json",
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Person",
  "type": "object",
  "properties": {
    "firstName": {
      "type": "string",
      "description": "The person's first name."
    },
    "lastName": {
      "type": "string",
      "description": "The person's last name."
    },
    "age": {
      "description": "Age in years which must be equal to or greater than zero.",
      "type": "integer",
      "minimum": 0
    }
  }
}
```

**有效数据示例**：`{"firstName": "John", "lastName": "Doe", "age": 21}`

---

## 三、数组（Arrays）

### 3.1 字符串数组

```json
{
  "fruits": {
    "type": "array",
    "items": {
      "type": "string"
    }
  }
}
```

### 3.2 对象数组与引用（$defs + $ref）

使用 `$defs` 定义可复用子 Schema，通过 `$ref` 引用：

| 关键字 | 用途 |
|--------|------|
| `$defs` | 定义可复用的子 Schema |
| `$ref` | 引用 `$defs` 中的定义 |
| `items` | 定义数组元素类型 |

**示例**：

```json
{
  "properties": {
    "fruits": {
      "type": "array",
      "items": { "type": "string" }
    },
    "vegetables": {
      "type": "array",
      "items": { "$ref": "#/$defs/veggie" }
    }
  },
  "$defs": {
    "veggie": {
      "type": "object",
      "required": ["veggieName", "veggieLike"],
      "properties": {
        "veggieName": { "type": "string", "description": "The name of the vegetable." },
        "veggieLike": { "type": "boolean", "description": "Do I like this vegetable?" }
      }
    }
  }
}
```

**有效数据示例**：

```json
{
  "fruits": ["apple", "orange", "pear"],
  "vegetables": [
    { "veggieName": "potato", "veggieLike": true },
    { "veggieName": "broccoli", "veggieLike": false }
  ]
}
```

---

## 四、枚举值（enum）

`enum` 用于限定属性只能取指定集合中的**精确值**，支持多种类型（整数、布尔、字符串、null、数组等）。

**示例**：

```json
{
  "properties": {
    "data": {
      "enum": [42, true, "hello", null, [1, 2, 3]]
    }
  }
}
```

**有效数据**：`{"data": [1, 2, 3]}`（必须与 enum 中某一项完全一致）

---

## 五、正则表达式模式（pattern）

`pattern` 用于对字符串进行正则匹配验证。

**示例**：要求 `code` 为 3 个大写字母 + 连字符 + 3 位数字（如 `ABC-123`）

```json
{
  "properties": {
    "code": {
      "type": "string",
      "pattern": "^[A-Z]{3}-\\d{3}$"
    }
  }
}
```

**有效数据**：`{"code": "ABC-123"}`

---

## 六、复杂对象与嵌套属性

### 6.1 嵌套对象

`address` 为嵌套对象，内部有 `required` 约束：

```json
{
  "properties": {
    "name": { "type": "string" },
    "age": { "type": "integer", "minimum": 0 },
    "address": {
      "type": "object",
      "properties": {
        "street": { "type": "string" },
        "city": { "type": "string" },
        "state": { "type": "string" },
        "postalCode": { "type": "string", "pattern": "\\d{5}" }
      },
      "required": ["street", "city", "state", "postalCode"]
    },
    "hobbies": {
      "type": "array",
      "items": { "type": "string" }
    }
  },
  "required": ["name", "age"]
}
```

**有效数据示例**：

```json
{
  "name": "John Doe",
  "age": 25,
  "address": {
    "street": "123 Main St",
    "city": "New York",
    "state": "NY",
    "postalCode": "10001"
  },
  "hobbies": ["reading", "running"]
}
```

---

## 七、条件验证（Conditional Validation）

### 7.1 dependentRequired：属性依赖

当某属性存在时，要求另一属性也必须存在。

**规则**：若 `foo` 存在，则 `bar` 必填。

```json
{
  "properties": {
    "foo": { "type": "boolean" },
    "bar": { "type": "string" }
  },
  "dependentRequired": {
    "foo": ["bar"]
  }
}
```

| 数据 | 是否有效 |
|------|----------|
| `{"foo": true, "bar": "Hello World"}` | ✅ |
| `{}` | ✅ |
| `{"foo": true}` | ❌（缺少 bar） |

### 7.2 dependentSchemas：条件子 Schema

当某属性存在时，整个实例需满足额外子 Schema。

**规则**：若 `foo` 存在，则 `propertiesCount` 必填且 ≥ 7。

```json
{
  "properties": {
    "foo": { "type": "boolean" },
    "propertiesCount": { "type": "integer", "minimum": 0 }
  },
  "dependentSchemas": {
    "foo": {
      "required": ["propertiesCount"],
      "properties": {
        "propertiesCount": { "minimum": 7 }
      }
    }
  }
}
```

| 数据 | 是否有效 |
|------|----------|
| `{"foo": true, "propertiesCount": 10}` | ✅ |
| `{"propertiesCount": 5}` | ✅（foo 不存在，无额外约束） |
| `{"foo": true, "propertiesCount": 5}` | ❌（foo 存在时 propertiesCount 需 ≥ 7） |

### 7.3 if-then-else：分支条件

根据某属性值选择不同的验证规则。

**规则**：
- `isMember === true` → `membershipNumber` 必须为 10 位字符串
- `isMember !== true` → `membershipNumber` 必须为至少 15 位字符串

```json
{
  "properties": {
    "isMember": { "type": "boolean" },
    "membershipNumber": { "type": "string" }
  },
  "required": ["isMember"],
  "if": {
    "properties": { "isMember": { "const": true } }
  },
  "then": {
    "properties": {
      "membershipNumber": {
        "type": "string",
        "minLength": 10,
        "maxLength": 10
      }
    }
  },
  "else": {
    "properties": {
      "membershipNumber": {
        "type": "string",
        "minLength": 15
      }
    }
  }
}
```

| 数据 | 是否有效 |
|------|----------|
| `{"isMember": true, "membershipNumber": "1234567890"}` | ✅ |
| `{"isMember": false, "membershipNumber": "GUEST1234567890"}` | ✅ |

---

## 八、常用关键字速查

| 关键字 | 类型 | 说明 |
|--------|------|------|
| `type` | string/array | 数据类型：string, number, integer, boolean, object, array, null |
| `properties` | object | 对象属性定义 |
| `required` | array | 必填属性列表 |
| `items` | object/array | 数组元素 Schema |
| `enum` | array | 允许的精确值集合 |
| `pattern` | string | 字符串正则模式 |
| `minimum` / `maximum` | number | 数值范围 |
| `minLength` / `maxLength` | integer | 字符串长度 |
| `$ref` | string | 引用其他 Schema |
| `$defs` | object | 可复用定义 |
| `dependentRequired` | object | 属性存在时的依赖要求 |
| `dependentSchemas` | object | 属性存在时的子 Schema |
| `if` / `then` / `else` | object | 条件分支验证 |
| `const` | any | 必须等于指定值 |

---

## 九、参考链接

- [JSON Schema 官方文档](https://json-schema.org/)
- [Miscellaneous Examples 原文](https://json-schema.org/learn/miscellaneous-examples)
- [JSON Schema Glossary](https://json-schema.org/learn/glossary)
- [Modelling a file system](https://json-schema.org/learn/file-system)
