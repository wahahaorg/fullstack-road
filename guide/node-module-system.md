# Node.js 模块系统

> CommonJS vs ESM，以及现代 package.json 的关键字段。

## CommonJS vs ES Module

这是 Node 面试最常见的模块题。

### CommonJS（CJS）

```js
// 导出
module.exports = { add, subtract }
// 或
exports.add = (a, b) => a + b

// 导入
const { add } = require('./math')
const fs = require('fs')
```

特点：
- `require()` 是同步执行、运行时加载
- 历史更早，Node 生态里很多老包都基于它
- 有 `__filename`、`__dirname`、`require`、`module` 等全局变量

### ES Module（ESM）

```js
// 导出
export const add = (a, b) => a + b
export default class MyClass {}

// 导入
import { add } from './math.js'
import MyClass from './my-class.js'
import('dynamic.js').then(m => m.default())  // 动态导入
```

特点：
- 语言标准模块系统
- 静态分析、支持 tree-shaking
- **默认没有** `__filename`、`__dirname`、`require`、`module.exports`

**ESM 中获取文件路径：**

```js
import { fileURLToPath } from 'url'
import { dirname } from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)
```

---

## package.json 关键字段

### `type` 字段

决定 Node 如何解释当前包内的 `.js` 文件：

```json
{ "type": "module" }    // .js 按 ESM 解析
{ "type": "commonjs" }  // .js 按 CJS 解析
// 不写：默认偏 CommonJS
```

**扩展名优先级最高：**
- `.mjs` → 始终当 ESM
- `.cjs` → 始终当 CommonJS
- `.js` → 根据最近的 `package.json` 的 `type` 字段决定

> 很多"为什么 import 不能用""为什么 require 报错"的问题，本质都是模块类型判定出了问题。

### `exports` 字段

现代包的对外入口声明，比 `main` 更强大：

```json
{
  "exports": {
    ".": {
      "import": "./dist/index.mjs",
      "require": "./dist/index.cjs"
    },
    "./utils": {
      "import": "./dist/utils.mjs",
      "require": "./dist/utils.cjs"
    }
  }
}
```

作用：
- 明确暴露哪些入口（隐藏内部文件）
- 支持条件导出（区分 `import` 与 `require`）
- `exports` 优先级高于 `main`

> ⚠️ 老项目加了 `exports` 后，原来能深层引用的路径会被拦掉，属于 breaking change。

---

## ESM 与 CJS 互操作

Node 支持互操作，但有边界：

```js
// ESM import CJS ✅ — 拿到的是 module.exports 整体作为默认导出
import cjsModule from './legacy.cjs'
const { add } = cjsModule

// CJS require ESM ❌ — 不能直接 require
const esmModule = require('./modern.mjs')  // Error!

// CJS 加载 ESM 要用动态 import()
const { add } = await import('./modern.mjs')
```

**混用时最容易踩坑的点：**
- 默认导出 vs 命名导出的映射关系
- top-level await（只有 ESM 支持）
- 执行时机不同（CJS 同步，ESM 异步）

> 项目里最好尽量统一模块风格，尤其在基础库与构建配置上。

---

## 面试高频追问

**Q: 新项目选 CJS 还是 ESM？**

新项目、偏现代工具链、库开发 → 更倾向 ESM；老项目维护 → CJS 仍很常见，不要强行迁移。

**Q: 为什么很多工具配置文件（webpack.config.js 等）还是 CJS？**

因为很多构建工具本身是 CJS，且配置文件需要同步加载，ESM 的异步特性会造成麻烦。Node 18+ 和新版工具链在逐步改善这个问题。

**Q: `import()` 动态导入和静态 `import` 有什么区别？**

| 特性 | 静态 `import` | 动态 `import()` |
|---|---|---|
| 执行时机 | 模块加载时 | 调用时（运行时） |
| 能否条件加载 | ❌ | ✅ |
| 返回值 | 绑定 | Promise |
| 在 CJS 中使用 | ❌ | ✅ |
