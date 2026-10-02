@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
cd /d "C:\Tools2\fingerbrowers\native_hook"
cl.exe /O2 /LD /MT /utf-8 /std:c++17 version_hook.cpp /Fe:version.dll /link /DEF:version.def user32.lib kernel32.lib
