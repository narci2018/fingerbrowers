# PhantomBrowser (工业级防关联指纹浏览器引擎)

**架构定位**：底层基于 **Apostate 定制 Chromium 防关联内核**（提供 ~120 个 C++ 源码级防检测补丁、Blink/Skia 原生伪装与亚像素微噪）+ **自研管控调度与自洽指纹编排层**（提供 Profile 物理隔离、全平台自洽 Envelope 生成、Mihomo/代理转发通道及 REST/MCP/Playwright 自动化接口）。

---

## 🌟 核心特性与架构

1. **Apostate 原生内核级指纹伪装**
   - 彻底告别脆弱易被检测的 JavaScript 原型链注入（0% Stealth 特征）。
   - 全平台统一采用 `--apostate-profile` JSON Envelope 载荷，在 C++ 启动期原生对齐 Platform、Client Hints、GPU/WebGL 硬件、屏幕、多媒体与系统全量字体白名单。
   - 确定性亚像素微噪（Seed-based Deterministic Noise）：Canvas、Audio 与 WebGL readback 哈希跨环境独立、单环境内严格恒定。

2. **Profile 完全物理隔离**
   - 独立的 `--user-data-dir` 沙箱存储，Cookies、LocalStorage、IndexedDB、缓存完全隔离。
   - 保证多账号、多环境同时运行不串号。

3. **自洽性指纹生成与全量白名单拦截**
   - 保证 User-Agent、OS Platform、屏幕物理与可用宽高、CPU、RAM 及 WebGL 显卡完全自洽。
   - 内核级字体白名单过滤（Subtractive Font Shield）：在 Windows 上模拟 macOS 时彻底阻断 Segoe UI 等 12 种 Windows 本地字体泄露，CreepJS 达成 0 Lies。

3. **双模自动化接入 (REST API + MCP Protocol)**
   - **REST API**：提供符合工业标准的 HTTP 接口，支持启动、关闭、管理环境，返回标准 CDP WebSocket 地址。
   - **Model Context Protocol (MCP)**：专为 AI Agent（Claude, Gemini, Antigravity 等）原生打造，Agent 可直接调用工具调度指纹浏览器执行自动化任务。
   - **Playwright / Puppeteer 原生驱动**：通过 CDP WebSocket 直连，无需安装定制插件。

---

## 📁 目录结构

```
c:/Tools2/fingerbrowers/
├── core/                       # 核心引擎层
│   ├── models.py               # 数据模型（Profile, Fingerprint, Proxy）
│   ├── fingerprint_generator.py# 指纹生成算法
│   ├── profile_manager.py      # Profile CRUD 与物理沙箱目录管理
│   ├── browser_launcher.py     # 浏览器生命周期与 CDP 端口分配管理
│   └── injections.py           # 原生级 Stealth 脚本与加噪注入器
├── api/                        # 控制面服务
│   └── server.py               # FastAPI RESTful 接口服务
├── mcp_server/                 # MCP 协议支持
│   └── server.py               # Model Context Protocol 工具服务
├── examples/                   # 测试与示例
│   ├── test_isolation.py       # 双环境物理沙箱与并发端口隔离测试
│   └── playwright_demo.py      # Playwright 联动与反指纹检测站测试
├── data/                       # 数据存储目录（已做 Git 隔离）
│   ├── profiles.json           # Profile 元数据配置
│   └── browser_data/           # 各 Profile 独立的沙箱运行数据
├── run_server.py               # REST API 启动脚本
└── requirements.txt            # 依赖清单
```

---

## 🚀 快速开始

### 1. 验证 Profile 物理隔离与并发测试
```powershell
python examples/test_isolation.py
```

### 2. 启动 REST API 服务
```powershell
python run_server.py --port 8998
```
访问交互式文档：`http://127.0.0.1:8998/docs`

### 3. 作为 MCP Server 供 AI Agent 调度
在 AI Agent 或 Claude Desktop 的 `claude_desktop_config.json` 中配置：
```json
{
  "mcpServers": {
    "fingerprint-browser": {
      "command": "python",
      "args": ["c:/Tools2/fingerbrowers/mcp_server/server.py"]
    }
  }
}
```

### 4. 运行 Playwright 反检测测试
```powershell
python examples/playwright_demo.py
```
