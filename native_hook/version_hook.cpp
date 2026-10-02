#define _INC_WINVER
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dwrite.h>

#pragma comment(lib, "user32.lib")
#pragma comment(lib, "kernel32.lib")
#pragma comment(lib, "gdi32.lib")

// ============================================================================
// 1. 系统底层 version.dll 透明中继通道 (Zero-Side-Effect System Forwarder)
// ============================================================================
static HMODULE g_hOrigVersion = NULL;

static void EnsureOrigVersionLoaded() {
    if (!g_hOrigVersion) {
        WCHAR sysPath[MAX_PATH];
        GetSystemDirectoryW(sysPath, MAX_PATH);
        wcscat_s(sysPath, L"\\version.dll");
        g_hOrigVersion = LoadLibraryW(sysPath);
    }
}

#define FORWARD_PROXY(returnType, funcName, paramDefs, paramPass) \
    extern "C" __declspec(dllexport) returnType WINAPI Proxy_##funcName paramDefs { \
        EnsureOrigVersionLoaded(); \
        if (g_hOrigVersion) { \
            typedef returnType (WINAPI *pfn) paramDefs; \
            pfn f = (pfn)GetProcAddress(g_hOrigVersion, #funcName); \
            if (f) return f paramPass; \
        } \
        return 0; \
    }

FORWARD_PROXY(BOOL, GetFileVersionInfoA, (LPCSTR a, DWORD b, DWORD c, LPVOID d), (a, b, c, d))
FORWARD_PROXY(BOOL, GetFileVersionInfoW, (LPCWSTR a, DWORD b, DWORD c, LPVOID d), (a, b, c, d))
FORWARD_PROXY(BOOL, GetFileVersionInfoExA, (DWORD a, LPCSTR b, DWORD c, DWORD d, LPVOID e), (a, b, c, d, e))
FORWARD_PROXY(BOOL, GetFileVersionInfoExW, (DWORD a, LPCWSTR b, DWORD c, DWORD d, LPVOID e), (a, b, c, d, e))
FORWARD_PROXY(DWORD, GetFileVersionInfoSizeA, (LPCSTR a, LPDWORD b), (a, b))
FORWARD_PROXY(DWORD, GetFileVersionInfoSizeW, (LPCWSTR a, LPDWORD b), (a, b))
FORWARD_PROXY(DWORD, GetFileVersionInfoSizeExA, (DWORD a, LPCSTR b, LPDWORD c), (a, b, c))
FORWARD_PROXY(DWORD, GetFileVersionInfoSizeExW, (DWORD a, LPCWSTR b, LPDWORD c), (a, b, c))
FORWARD_PROXY(BOOL, VerQueryValueA, (LPCVOID a, LPCSTR b, LPVOID* c, PUINT d), (a, b, c, d))
FORWARD_PROXY(BOOL, VerQueryValueW, (LPCVOID a, LPCWSTR b, LPVOID* c, PUINT d), (a, b, c, d))
FORWARD_PROXY(DWORD, VerLanguageNameA, (DWORD a, LPSTR b, DWORD c), (a, b, c))
FORWARD_PROXY(DWORD, VerLanguageNameW, (DWORD a, LPWSTR b, DWORD c), (a, b, c))

// ============================================================================
// 2. 日志系统与安全诊断 (Logging & Diagnostics)
// ============================================================================
static CRITICAL_SECTION g_logLock;
static bool g_logLockInit = false;

static void WriteHookLog(const char* fmt, ...) {
    if (!g_logLockInit) {
        InitializeCriticalSection(&g_logLock);
        g_logLockInit = true;
    }
    EnterCriticalSection(&g_logLock);

    char buf[2048];
    va_list args;
    va_start(args, fmt);
    vsnprintf(buf, sizeof(buf), fmt, args);
    va_end(args);

    static char s_logPath[MAX_PATH] = { 0 };
    if (!s_logPath[0]) {
        HMODULE hThis = NULL;
        GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT, (LPCSTR)WriteHookLog, &hThis);
        if (hThis) {
            GetModuleFileNameA(hThis, s_logPath, MAX_PATH);
            char* lastSlash = strrchr(s_logPath, '\\');
            if (lastSlash) *(lastSlash + 1) = '\0';
            strcat_s(s_logPath, "hook.log");
        } else {
            strcpy_s(s_logPath, "hook.log");
        }
    }

    FILE* f = fopen(s_logPath, "a");
    if (f) {
        SYSTEMTIME st;
        GetLocalTime(&st);
        fprintf(f, "[%02d:%02d:%02d.%03d] [KernelHook] %s\n", 
            st.wHour, st.wMinute, st.wSecond, st.wMilliseconds, buf);
        fclose(f);
    }
    LeaveCriticalSection(&g_logLock);
}

// ============================================================================
// 3. 商业级 Profile 指纹参数集与确定性 PRNG 算法 (Farbling Math Engine)
// ============================================================================
struct FingerprintProfile {
    uint32_t seed;
    DWORD    cpuCores;
    uint64_t ramBytes;
    int      screenWidth;
    int      screenHeight;
    bool     initialized;
};

static FingerprintProfile g_fpConfig = { 0, 8, 16ULL * 1024 * 1024 * 1024, 1920, 1080, false };

// XorShift128+ 高性能确定性伪随机数生成器 (Brave Farbling 标准算法)
struct XorShift128Plus {
    uint64_t s[2];
    void init(uint64_t seed) {
        s[0] = seed ^ 0x9E3779B97F4A7C15ULL;
        s[1] = (seed << 31) | (seed >> 33);
        if (s[0] == 0 && s[1] == 0) { s[0] = 1; }
    }
    uint64_t next() {
        uint64_t s1 = s[0];
        const uint64_t s0 = s[1];
        s[0] = s0;
        s1 ^= s1 << 23;
        s[1] = s1 ^ s0 ^ (s1 >> 17) ^ (s0 >> 26);
        return s[1] + s0;
    }
    double nextDouble() {
        return (next() >> 11) * (1.0 / 9007199254740992.0);
    }
};

static XorShift128Plus g_prng;

static void InitProfileConfig() {
    if (g_fpConfig.initialized) return;

    // 1. 读取确定性混淆种子
    const char* envSeed = getenv("PHANTOM_FP_SEED");
    if (envSeed) {
        g_fpConfig.seed = (uint32_t)strtoul(envSeed, NULL, 10);
    } else {
        g_fpConfig.seed = 1234567;
    }
    g_prng.init(g_fpConfig.seed);

    // 2. 读取硬件并发核数
    const char* envCpu = getenv("PHANTOM_CPU_CORES");
    if (envCpu) {
        int c = atoi(envCpu);
        if (c > 0 && c <= 128) g_fpConfig.cpuCores = (DWORD)c;
    }

    // 3. 读取物理内存大小 (GB)
    const char* envRam = getenv("PHANTOM_RAM_GB");
    if (envRam) {
        int r = atoi(envRam);
        if (r > 0 && r <= 512) g_fpConfig.ramBytes = (uint64_t)r * 1024ULL * 1024ULL * 1024ULL;
    }

    // 4. 读取屏幕分辨率
    const char* envSw = getenv("PHANTOM_SCREEN_WIDTH");
    const char* envSh = getenv("PHANTOM_SCREEN_HEIGHT");
    if (envSw && envSh) {
        g_fpConfig.screenWidth = atoi(envSw);
        g_fpConfig.screenHeight = atoi(envSh);
    }

    g_fpConfig.initialized = true;
    WriteHookLog("Profile loaded: Seed=%u, Cores=%u, RAM=%llu GB, Screen=%dx%d",
        g_fpConfig.seed, g_fpConfig.cpuCores, g_fpConfig.ramBytes / (1024*1024*1024),
        g_fpConfig.screenWidth, g_fpConfig.screenHeight);
}

// ============================================================================
// 4. 原生硬件伪装: KERNEL32 硬件与内存参数拦截 (Hardware Concurrency & RAM)
// ============================================================================
typedef VOID (WINAPI *pfnGetSystemInfo)(LPSYSTEM_INFO lpSystemInfo);
static pfnGetSystemInfo g_origGetSystemInfo = NULL;

VOID WINAPI Hooked_GetSystemInfo(LPSYSTEM_INFO lpSystemInfo) {
    if (g_origGetSystemInfo) g_origGetSystemInfo(lpSystemInfo);
    else GetSystemInfo(lpSystemInfo);

    if (lpSystemInfo && g_fpConfig.cpuCores > 0) {
        lpSystemInfo->dwNumberOfProcessors = g_fpConfig.cpuCores;
    }
}

typedef VOID (WINAPI *pfnGetNativeSystemInfo)(LPSYSTEM_INFO lpSystemInfo);
static pfnGetNativeSystemInfo g_origGetNativeSystemInfo = NULL;

VOID WINAPI Hooked_GetNativeSystemInfo(LPSYSTEM_INFO lpSystemInfo) {
    if (g_origGetNativeSystemInfo) g_origGetNativeSystemInfo(lpSystemInfo);
    else GetNativeSystemInfo(lpSystemInfo);

    if (lpSystemInfo && g_fpConfig.cpuCores > 0) {
        lpSystemInfo->dwNumberOfProcessors = g_fpConfig.cpuCores;
    }
}

typedef BOOL (WINAPI *pfnGlobalMemoryStatusEx)(LPMEMORYSTATUSEX lpBuffer);
static pfnGlobalMemoryStatusEx g_origGlobalMemoryStatusEx = NULL;

BOOL WINAPI Hooked_GlobalMemoryStatusEx(LPMEMORYSTATUSEX lpBuffer) {
    BOOL ret = g_origGlobalMemoryStatusEx ? g_origGlobalMemoryStatusEx(lpBuffer) : GlobalMemoryStatusEx(lpBuffer);
    if (ret && lpBuffer && g_fpConfig.ramBytes > 0) {
        lpBuffer->ullTotalPhys = g_fpConfig.ramBytes;
        lpBuffer->ullAvailPhys = (DWORDLONG)(g_fpConfig.ramBytes * 0.62); // 保持真实内存占用率
        lpBuffer->ullTotalPageFile = (DWORDLONG)(g_fpConfig.ramBytes * 1.25);
        lpBuffer->ullAvailPageFile = (DWORDLONG)(lpBuffer->ullTotalPageFile * 0.70);
    }
    return ret;
}

// ============================================================================
// 5. 命令行与自动化特征深度净化 (GetCommandLineW Sanitizer)
// ============================================================================
typedef LPWSTR (WINAPI *pfnGetCommandLineW)(VOID);
static pfnGetCommandLineW g_origGetCommandLineW = NULL;
static WCHAR g_cleanCommandLine[16384] = {0};

LPWSTR WINAPI Hooked_GetCommandLineW(VOID) {
    if (g_cleanCommandLine[0] != L'\0') {
        return g_cleanCommandLine;
    }

    LPWSTR raw = g_origGetCommandLineW ? g_origGetCommandLineW() : GetCommandLineW();
    if (!raw) return raw;

    wcsncpy_s(g_cleanCommandLine, raw, sizeof(g_cleanCommandLine) / sizeof(WCHAR) - 1);

    // 需彻底剥离的自动化参数特征库
    const WCHAR* blacklistedFlags[] = {
        L"--enable-automation",
        L"--test-type",
        L"--disable-blink-features=AutomationControlled",
        L"--flag-switches-begin",
        L"--flag-switches-end",
        L"--disable-default-apps",
        L"--no-default-browser-check"
    };

    for (size_t i = 0; i < sizeof(blacklistedFlags) / sizeof(blacklistedFlags[0]); i++) {
        WCHAR* pos = wcsstr(g_cleanCommandLine, blacklistedFlags[i]);
        while (pos != NULL) {
            size_t len = wcslen(blacklistedFlags[i]);
            for (size_t k = 0; k < len; k++) pos[k] = L' ';
            pos = wcsstr(pos + len, blacklistedFlags[i]);
        }
    }

    WriteHookLog("GetCommandLineW() sanitized and delivered to Chromium engine.");
    return g_cleanCommandLine;
}

// ============================================================================
// 6. 物理屏幕分辨率与多显示器伪造 (USER32 Display Metrics Spoofing)
// ============================================================================
typedef int (WINAPI *pfnGetSystemMetrics)(int nIndex);
static pfnGetSystemMetrics g_origGetSystemMetrics = NULL;

int WINAPI Hooked_GetSystemMetrics(int nIndex) {
    int val = g_origGetSystemMetrics ? g_origGetSystemMetrics(nIndex) : GetSystemMetrics(nIndex);

    if (g_fpConfig.screenWidth > 0 && g_fpConfig.screenHeight > 0) {
        switch (nIndex) {
            case SM_CXSCREEN:
            case SM_CXVIRTUALSCREEN:
                return g_fpConfig.screenWidth;
            case SM_CYSCREEN:
            case SM_CYVIRTUALSCREEN:
                return g_fpConfig.screenHeight;
            case SM_CMONITORS:
                return 1; // 统一单显示器环境，消除物理多屏指纹泄漏
        }
    }
    return val;
}

// ============================================================================
// 7. 工业级 IAT (Import Address Table) 递归注入引擎
// ============================================================================
static BOOL PatchIAT(HMODULE hMod, const char* targetDll, const char* funcName, void* newFunc, void** oldFunc) {
    if (!hMod) return FALSE;

    PIMAGE_DOS_HEADER dosHeader = (PIMAGE_DOS_HEADER)hMod;
    if (dosHeader->e_magic != IMAGE_DOS_SIGNATURE) return FALSE;

    PIMAGE_NT_HEADERS ntHeaders = (PIMAGE_NT_HEADERS)((BYTE*)hMod + dosHeader->e_lfanew);
    if (ntHeaders->Signature != IMAGE_NT_SIGNATURE) return FALSE;

    IMAGE_DATA_DIRECTORY importDir = ntHeaders->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    if (importDir.VirtualAddress == 0 || importDir.Size == 0) return FALSE;

    PIMAGE_IMPORT_DESCRIPTOR importDesc = (PIMAGE_IMPORT_DESCRIPTOR)((BYTE*)hMod + importDir.VirtualAddress);

    while (importDesc->Name) {
        const char* moduleName = (const char*)((BYTE*)hMod + importDesc->Name);
        if (_stricmp(moduleName, targetDll) == 0) {
            PIMAGE_THUNK_DATA thunk = (PIMAGE_THUNK_DATA)((BYTE*)hMod + importDesc->FirstThunk);
            PIMAGE_THUNK_DATA origThunk = (PIMAGE_THUNK_DATA)((BYTE*)hMod + importDesc->OriginalFirstThunk);
            if (!origThunk) origThunk = thunk;

            while (thunk->u1.Function) {
                if (!(origThunk->u1.Ordinal & IMAGE_ORDINAL_FLAG)) {
                    PIMAGE_IMPORT_BY_NAME importByName = (PIMAGE_IMPORT_BY_NAME)((BYTE*)hMod + origThunk->u1.AddressOfData);
                    if (strcmp((char*)importByName->Name, funcName) == 0) {
                        DWORD oldProtect = 0;
                        if (VirtualProtect(&thunk->u1.Function, sizeof(void*), PAGE_EXECUTE_READWRITE, &oldProtect)) {
                            if (oldFunc && *oldFunc == NULL) {
                                *oldFunc = (void*)thunk->u1.Function;
                            }
                            thunk->u1.Function = (ULONG_PTR)newFunc;
                            VirtualProtect(&thunk->u1.Function, sizeof(void*), oldProtect, &oldProtect);
                            return TRUE;
                        }
                    }
                }
                thunk++;
                origThunk++;
            }
        }
        importDesc++;
    }
    return FALSE;
}

// 延迟导入表 (Delay Import Table) 注入引擎
static BOOL PatchDelayIAT(HMODULE hMod, const char* targetDll, const char* funcName, void* newFunc, void** oldFunc) {
    if (!hMod) return FALSE;

    PIMAGE_DOS_HEADER dosHeader = (PIMAGE_DOS_HEADER)hMod;
    if (dosHeader->e_magic != IMAGE_DOS_SIGNATURE) return FALSE;

    PIMAGE_NT_HEADERS ntHeaders = (PIMAGE_NT_HEADERS)((BYTE*)hMod + dosHeader->e_lfanew);
    if (ntHeaders->Signature != IMAGE_NT_SIGNATURE) return FALSE;

    IMAGE_DATA_DIRECTORY delayDir = ntHeaders->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT];
    if (delayDir.VirtualAddress == 0 || delayDir.Size == 0) return FALSE;

    // 延迟导入描述符结构
    typedef struct _IMAGE_DELAYLOAD_DESCRIPTOR {
        DWORD Attributes;
        DWORD DllNameRVA;
        DWORD ModuleHandleRVA;
        DWORD ImportAddressTableRVA;
        DWORD ImportNameTableRVA;
        DWORD BoundImportAddressTableRVA;
        DWORD UnloadInformationTableRVA;
        DWORD TimeDateStamp;
    } IMAGE_DELAYLOAD_DESCRIPTOR, *PIMAGE_DELAYLOAD_DESCRIPTOR;

    PIMAGE_DELAYLOAD_DESCRIPTOR delayDesc = (PIMAGE_DELAYLOAD_DESCRIPTOR)((BYTE*)hMod + delayDir.VirtualAddress);

    while (delayDesc->DllNameRVA) {
        const char* moduleName = (const char*)((BYTE*)hMod + delayDesc->DllNameRVA);
        if (_stricmp(moduleName, targetDll) == 0) {
            PIMAGE_THUNK_DATA thunk = (PIMAGE_THUNK_DATA)((BYTE*)hMod + delayDesc->ImportAddressTableRVA);
            PIMAGE_THUNK_DATA nameThunk = (PIMAGE_THUNK_DATA)((BYTE*)hMod + delayDesc->ImportNameTableRVA);

            while (thunk->u1.Function) {
                if (!(nameThunk->u1.Ordinal & IMAGE_ORDINAL_FLAG)) {
                    PIMAGE_IMPORT_BY_NAME importByName = (PIMAGE_IMPORT_BY_NAME)((BYTE*)hMod + nameThunk->u1.AddressOfData);
                    if (strcmp((char*)importByName->Name, funcName) == 0) {
                        DWORD oldProtect = 0;
                        if (VirtualProtect(&thunk->u1.Function, sizeof(void*), PAGE_EXECUTE_READWRITE, &oldProtect)) {
                            if (oldFunc && *oldFunc == NULL) {
                                *oldFunc = (void*)thunk->u1.Function;
                            }
                            thunk->u1.Function = (ULONG_PTR)newFunc;
                            VirtualProtect(&thunk->u1.Function, sizeof(void*), oldProtect, &oldProtect);
                            return TRUE;
                        }
                    }
                }
                thunk++;
                nameThunk++;
            }
        }
        delayDesc++;
    }
    return FALSE;
}

// ============================================================================
// 9. 全模块装载与多级挂钩监控流水线 (Core Orchestration Pipeline)
// ============================================================================
static void ApplyComprehensiveHooks(HMODULE hTargetModule) {
    if (!hTargetModule) return;

    WriteHookLog("Applying full industrial-grade hooks to module: %p", hTargetModule);

    // 1. 挂钩 KERNEL32 (命令行、CPU 核心数、物理内存)
    if (PatchIAT(hTargetModule, "KERNEL32.dll", "GetCommandLineW", (void*)Hooked_GetCommandLineW, (void**)&g_origGetCommandLineW)) {
        WriteHookLog("  [HOOKED] KERNEL32!GetCommandLineW");
    }
    if (PatchIAT(hTargetModule, "KERNEL32.dll", "GetSystemInfo", (void*)Hooked_GetSystemInfo, (void**)&g_origGetSystemInfo)) {
        WriteHookLog("  [HOOKED] KERNEL32!GetSystemInfo -> Spoofed CPU Cores: %u", g_fpConfig.cpuCores);
    }
    if (PatchIAT(hTargetModule, "KERNEL32.dll", "GetNativeSystemInfo", (void*)Hooked_GetNativeSystemInfo, (void**)&g_origGetNativeSystemInfo)) {
        WriteHookLog("  [HOOKED] KERNEL32!GetNativeSystemInfo -> Spoofed CPU Cores: %u", g_fpConfig.cpuCores);
    }
    if (PatchIAT(hTargetModule, "KERNEL32.dll", "GlobalMemoryStatusEx", (void*)Hooked_GlobalMemoryStatusEx, (void**)&g_origGlobalMemoryStatusEx)) {
        WriteHookLog("  [HOOKED] KERNEL32!GlobalMemoryStatusEx -> Spoofed RAM: %llu GB", g_fpConfig.ramBytes / (1024*1024*1024));
    }

    // 2. 挂钩 USER32 延迟导入表 (屏幕物理分辨率与显示器指标)
    if (PatchDelayIAT(hTargetModule, "USER32.dll", "GetSystemMetrics", (void*)Hooked_GetSystemMetrics, (void**)&g_origGetSystemMetrics)) {
        WriteHookLog("  [HOOKED] USER32!GetSystemMetrics -> Spoofed Resolution: %dx%d", g_fpConfig.screenWidth, g_fpConfig.screenHeight);
    }
}

// 异步监视线程：自旋监控并挂钩 chrome.dll
static DWORD WINAPI MonitorThread(LPVOID lpParam) {
    WriteHookLog("Monitor thread active. Scanning for chrome.dll in process memory space...");
    for (int i = 0; i < 100; i++) {
        HMODULE hChrome = GetModuleHandleW(L"chrome.dll");
        if (hChrome) {
            WriteHookLog("chrome.dll confirmed at base %p. Initiating hook matrix...", hChrome);
            ApplyComprehensiveHooks(hChrome);
            break;
        }
        Sleep(50);
    }
    return 0;
}

// ============================================================================
// 10. DllMain 入口接管 (PE Entry Point)
// ============================================================================
BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpReserved) {
    if (fdwReason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hinstDLL);
        EnsureOrigVersionLoaded();
        InitProfileConfig();

        char exePath[MAX_PATH];
        GetModuleFileNameA(NULL, exePath, sizeof(exePath));
        WriteHookLog("Phantom Kernel Hook loaded into: %s", exePath);

        // 如果注入到主浏览器或子进程中，启动监控与拦截线程
        if (strstr(exePath, "chrome.exe") || strstr(exePath, "msedge.exe")) {
            CreateThread(NULL, 0, MonitorThread, NULL, 0, NULL);
        }
    } else if (fdwReason == DLL_PROCESS_DETACH) {
        if (g_hOrigVersion) {
            FreeLibrary(g_hOrigVersion);
            g_hOrigVersion = NULL;
        }
        if (g_logLockInit) {
            DeleteCriticalSection(&g_logLock);
            g_logLockInit = false;
        }
    }
    return TRUE;
}
