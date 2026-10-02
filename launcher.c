#include <windows.h>
#include <stdio.h>
#include <stdlib.h>

int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance, LPSTR lpCmdLine, int nCmdShow) {
    char currentDir[MAX_PATH];
    if (!GetModuleFileNameA(NULL, currentDir, MAX_PATH)) {
        return 1;
    }
    char *lastSlash = strrchr(currentDir, '\\');
    if (lastSlash) {
        *lastSlash = '\0';
    }

    // 优先寻找纯图形无窗口子系统的 pythonw.exe (彻底杜绝任何黑框控制台闪烁)
    const char *pythonCandidates[] = {
        "C:\\Users\\narci\\miniconda3\\pythonw.exe",
        "C:\\ProgramData\\miniconda3\\pythonw.exe",
        "C:\\Python311\\pythonw.exe",
        "C:\\Python310\\pythonw.exe",
        "pythonw.exe"
    };

    char pythonExe[MAX_PATH] = {0};
    int found = 0;
    for (size_t i = 0; i < sizeof(pythonCandidates)/sizeof(pythonCandidates[0]); i++) {
        if (GetFileAttributesA(pythonCandidates[i]) != INVALID_FILE_ATTRIBUTES) {
            strncpy(pythonExe, pythonCandidates[i], sizeof(pythonExe) - 1);
            found = 1;
            break;
        }
    }
    if (!found) {
        strncpy(pythonExe, "pythonw.exe", sizeof(pythonExe) - 1);
    }

    char cmd[2048];
    snprintf(cmd, sizeof(cmd), "\"%s\" \"%s\\app_gui.py\"", pythonExe, currentDir);

    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    si.lpDesktop = "WinSta0\\Default";
    ZeroMemory(&pi, sizeof(pi));

    DWORD flags = 0;

    BOOL ok = CreateProcessA(
        NULL,
        cmd,
        NULL,
        NULL,
        FALSE,
        flags,
        NULL,
        currentDir,
        &si,
        &pi
    );

    if (ok) {
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
    } else {
        char errBuf[512];
        snprintf(errBuf, sizeof(errBuf), "无法启动 Phantom Browser 核心。\n请确认已安装 Python 环境。\n错误码: %lu", GetLastError());
        MessageBoxA(NULL, errBuf, "Phantom Browser 错误", MB_OK | MB_ICONERROR);
        return 1;
    }

    return 0;
}
