#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// 原始系统 DLL 句柄
static HMODULE g_hOrigVersion = NULL;

// 动态加载原始系统 version.dll
static void EnsureOrigVersionLoaded() {
    if (!g_hOrigVersion) {
        WCHAR sysPath[MAX_PATH];
        GetSystemDirectoryW(sysPath, MAX_PATH);
        wcscat_s(sysPath, L"\\version.dll");
        g_hOrigVersion = LoadLibraryW(sysPath);
    }
}

// 转发宏定义
#define FORWARD_STUB(funcName) \
    FARPROC pFunc = NULL; \
    EnsureOrigVersionLoaded(); \
    if (g_hOrigVersion) pFunc = GetProcAddress(g_hOrigVersion, #funcName);

#define DLL_EXPORT extern "C" __declspec(dllexport)

DLL_EXPORT BOOL WINAPI GetFileVersionInfoA(LPCSTR lptstrFilename, DWORD dwHandle, DWORD dwLen, LPVOID lpData) {
    FORWARD_STUB(GetFileVersionInfoA);
    if (pFunc) return ((decltype(&GetFileVersionInfoA))pFunc)(lptstrFilename, dwHandle, dwLen, lpData);
    return FALSE;
}

DLL_EXPORT BOOL WINAPI GetFileVersionInfoW(LPCWSTR lptstrFilename, DWORD dwHandle, DWORD dwLen, LPVOID lpData) {
    FORWARD_STUB(GetFileVersionInfoW);
    if (pFunc) return ((decltype(&GetFileVersionInfoW))pFunc)(lptstrFilename, dwHandle, dwLen, lpData);
    return FALSE;
}

DLL_EXPORT BOOL WINAPI GetFileVersionInfoExA(DWORD dwFlags, LPCSTR lpwstrFilename, DWORD dwHandle, DWORD dwLen, LPVOID lpData) {
    FORWARD_STUB(GetFileVersionInfoExA);
    if (pFunc) return ((decltype(&GetFileVersionInfoExA))pFunc)(dwFlags, lpwstrFilename, dwHandle, dwLen, lpData);
    return FALSE;
}

DLL_EXPORT BOOL WINAPI GetFileVersionInfoExW(DWORD dwFlags, LPCWSTR lpwstrFilename, DWORD dwHandle, DWORD dwLen, LPVOID lpData) {
    FORWARD_STUB(GetFileVersionInfoExW);
    if (pFunc) return ((decltype(&GetFileVersionInfoExW))pFunc)(dwFlags, lpwstrFilename, dwHandle, dwLen, lpData);
    return FALSE;
}

DLL_EXPORT DWORD WINAPI GetFileVersionInfoSizeA(LPCSTR lptstrFilename, LPDWORD lpdwHandle) {
    FORWARD_STUB(GetFileVersionInfoSizeA);
    if (pFunc) return ((decltype(&GetFileVersionInfoSizeA))pFunc)(lptstrFilename, lpdwHandle);
    return 0;
}

DLL_EXPORT DWORD WINAPI GetFileVersionInfoSizeW(LPCWSTR lptstrFilename, LPDWORD lpdwHandle) {
    FORWARD_STUB(GetFileVersionInfoSizeW);
    if (pFunc) return ((decltype(&GetFileVersionInfoSizeW))pFunc)(lptstrFilename, lpdwHandle);
    return 0;
}

DLL_EXPORT DWORD WINAPI GetFileVersionInfoSizeExA(DWORD dwFlags, LPCSTR lpwstrFilename, LPDWORD lpdwHandle) {
    FORWARD_STUB(GetFileVersionInfoSizeExA);
    if (pFunc) return ((decltype(&GetFileVersionInfoSizeExA))pFunc)(dwFlags, lpwstrFilename, lpdwHandle);
    return 0;
}

DLL_EXPORT DWORD WINAPI GetFileVersionInfoSizeExW(DWORD dwFlags, LPCWSTR lpwstrFilename, LPDWORD lpdwHandle) {
    FORWARD_STUB(GetFileVersionInfoSizeExW);
    if (pFunc) return ((decltype(&GetFileVersionInfoSizeExW))pFunc)(dwFlags, lpwstrFilename, lpdwHandle);
    return 0;
}

DLL_EXPORT BOOL WINAPI VerQueryValueA(LPCVOID pBlock, LPCSTR lpSubBlock, LPVOID *lplpBuffer, PUINT puLen) {
    FORWARD_STUB(VerQueryValueA);
    if (pFunc) return ((decltype(&VerQueryValueA))pFunc)(pBlock, lpSubBlock, lplpBuffer, puLen);
    return FALSE;
}

DLL_EXPORT BOOL WINAPI VerQueryValueW(LPCVOID pBlock, LPCWSTR lpSubBlock, LPVOID *lplpBuffer, PUINT puLen) {
    FORWARD_STUB(VerQueryValueW);
    if (pFunc) return ((decltype(&VerQueryValueW))pFunc)(pBlock, lpSubBlock, lplpBuffer, puLen);
    return FALSE;
}

DLL_EXPORT DWORD WINAPI VerLanguageNameA(DWORD wLang, LPSTR szLang, DWORD nSize) {
    FORWARD_STUB(VerLanguageNameA);
    if (pFunc) return ((decltype(&VerLanguageNameA))pFunc)(wLang, szLang, nSize);
    return 0;
}

DLL_EXPORT DWORD WINAPI VerLanguageNameW(DWORD wLang, LPWSTR szLang, DWORD nSize) {
    FORWARD_STUB(VerLanguageNameW);
    if (pFunc) return ((decltype(&VerLanguageNameW))pFunc)(wLang, szLang, nSize);
    return 0;
}

// 日志输出辅助
static void WriteHookLog(const char* fmt, ...) {
    char buf[1024];
    va_list args;
    va_start(args, fmt);
    vsnprintf(buf, sizeof(buf), fmt, args);
    va_end(args);

    FILE* f = fopen("C:\\Tools2\\fingerbrowers\\native_hook\\hook.log", "a");
    if (f) {
        SYSTEMTIME st;
        GetLocalTime(&st);
        fprintf(f, "[%02d:%02d:%02d.%03d] %s\n", st.wHour, st.wMinute, st.wSecond, st.wMilliseconds, buf);
        fclose(f);
    }
}

// 原始 GetCommandLineW 函数指针
typedef LPWSTR (WINAPI *pfnGetCommandLineW)(VOID);
static pfnGetCommandLineW g_origGetCommandLineW = NULL;
static WCHAR g_cleanCommandLine[8192] = {0};

// Hooked GetCommandLineW: 剥离自动化敏感参数
LPWSTR WINAPI Hooked_GetCommandLineW(VOID) {
    if (g_cleanCommandLine[0] != L'\0') {
        return g_cleanCommandLine;
    }

    LPWSTR raw = g_origGetCommandLineW ? g_origGetCommandLineW() : GetCommandLineW();
    if (!raw) return raw;

    wcsncpy_s(g_cleanCommandLine, raw, sizeof(g_cleanCommandLine) / sizeof(WCHAR) - 1);

    const WCHAR* sensitiveFlags[] = {
        L"--enable-automation",
        L"--test-type",
        L"--disable-blink-features=AutomationControlled"
    };

    for (size_t i = 0; i < sizeof(sensitiveFlags) / sizeof(sensitiveFlags[0]); i++) {
        WCHAR* pos = wcsstr(g_cleanCommandLine, sensitiveFlags[i]);
        while (pos != NULL) {
            size_t len = wcslen(sensitiveFlags[i]);
            for (size_t k = 0; k < len; k++) {
                pos[k] = L' ';
            }
            pos = wcsstr(pos + len, sensitiveFlags[i]);
        }
    }

    WriteHookLog("GetCommandLineW() hooked -> sensitive automation flags purged.");
    return g_cleanCommandLine;
}

// IAT Hook 引擎
static BOOL HookIAT(HMODULE hMod, const char* targetDll, const char* funcName, void* newFunc, void** oldFunc) {
    if (!hMod) return FALSE;

    PIMAGE_DOS_HEADER dosHeader = (PIMAGE_DOS_HEADER)hMod;
    if (dosHeader->e_magic != IMAGE_DOS_SIGNATURE) return FALSE;

    PIMAGE_NT_HEADERS ntHeaders = (PIMAGE_NT_HEADERS)((BYTE*)hMod + dosHeader->e_lfanew);
    if (ntHeaders->Signature != IMAGE_NT_SIGNATURE) return FALSE;

    PIMAGE_IMPORT_DESCRIPTOR importDesc = (PIMAGE_IMPORT_DESCRIPTOR)((BYTE*)hMod + 
        ntHeaders->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT].VirtualAddress);

    if (!importDesc) return FALSE;

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
                        VirtualProtect(&thunk->u1.Function, sizeof(void*), PAGE_EXECUTE_READWRITE, &oldProtect);
                        if (oldFunc && *oldFunc == NULL) {
                            *oldFunc = (void*)thunk->u1.Function;
                        }
                        thunk->u1.Function = (ULONG_PTR)newFunc;
                        VirtualProtect(&thunk->u1.Function, sizeof(void*), oldProtect, &oldProtect);
                        return TRUE;
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

// 监视与挂钩线程
static DWORD WINAPI MonitorThread(LPVOID lpParam) {
    WriteHookLog("Phantom Hook monitor thread started. Waiting for chrome.dll...");
    for (int i = 0; i < 50; i++) {
        HMODULE hChrome = GetModuleHandleW(L"chrome.dll");
        if (hChrome) {
            WriteHookLog("chrome.dll detected at %p. Applying IAT hooks...", hChrome);
            if (HookIAT(hChrome, "KERNEL32.dll", "GetCommandLineW", (void*)Hooked_GetCommandLineW, (void**)&g_origGetCommandLineW)) {
                WriteHookLog("GetCommandLineW IAT Hook active in chrome.dll!");
            }
            break;
        }
        Sleep(100);
    }
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpReserved) {
    if (fdwReason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hinstDLL);
        EnsureOrigVersionLoaded();

        char exePath[MAX_PATH];
        GetModuleFileNameA(NULL, exePath, sizeof(exePath));
        WriteHookLog("Phantom Hook attached to process: %s", exePath);

        if (strstr(exePath, "chrome.exe") || strstr(exePath, "msedge.exe")) {
            CreateThread(NULL, 0, MonitorThread, NULL, 0, NULL);
        }
    } else if (fdwReason == DLL_PROCESS_DETACH) {
        if (g_hOrigVersion) {
            FreeLibrary(g_hOrigVersion);
            g_hOrigVersion = NULL;
        }
    }
    return TRUE;
}
