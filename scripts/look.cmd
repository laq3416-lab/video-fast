@echo off
chcp 65001 >nul
node "%~dp0look.mjs" %*
