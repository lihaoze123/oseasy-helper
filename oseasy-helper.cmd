@echo off
pushd "%~dp0"
python -m oseasy_helper %*
set "oseasy_exit=%errorlevel%"
popd
exit /b %oseasy_exit%
