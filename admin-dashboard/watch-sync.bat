@echo off
REM S3 Sync Watch Mode for Windows
REM Auto sync dist folder to S3 and invalidate CloudFront

setlocal enabledelayedexpansion

REM Configuration from CloudFormation
set BUCKET_NAME=adminstack-adminfrontendbucket878574a2-fhkbssrz9cq2
set DISTRIBUTION_ID=E38R5G5I8DKMQE
set WATCH_DIR=dist
set REGION=ap-southeast-1

echo ================================
echo   S3 Sync Watch Mode
echo ================================
echo Bucket: %BUCKET_NAME%
echo Distribution: %DISTRIBUTION_ID%
echo Watch directory: %WATCH_DIR%
echo Region: %REGION%
echo.
echo Starting watch mode... Press Ctrl+C to stop
echo.

REM Check if dist folder exists
if not exist "%WATCH_DIR%" (
    echo Error: %WATCH_DIR% folder not found!
    echo Run 'npm run build' first to create dist folder
    exit /b 1
)

REM Initial sync
echo [%time%] Performing initial sync...
call :sync_to_s3

echo.
echo Watching for changes...
echo.

:watch_loop
REM Wait 5 seconds
timeout /t 5 /nobreak > nul

REM Check if files changed (simple timestamp check)
for /f %%i in ('dir /s /b /a-d "%WATCH_DIR%" ^| find /c /v ""') do set FILE_COUNT=%%i

if not defined LAST_FILE_COUNT (
    set LAST_FILE_COUNT=%FILE_COUNT%
    goto watch_loop
)

if not "%FILE_COUNT%"=="%LAST_FILE_COUNT%" (
    echo [%time%] Changes detected!
    call :sync_to_s3
    set LAST_FILE_COUNT=%FILE_COUNT%
)

goto watch_loop

:sync_to_s3
echo [%time%] Syncing to S3...

REM Sync static assets with long cache
aws s3 sync %WATCH_DIR% s3://%BUCKET_NAME%/ ^
    --delete ^
    --region %REGION% ^
    --cache-control "max-age=31536000,public" ^
    --exclude "*.html" ^
    --exclude "*.json"

REM Sync HTML/JSON without cache
aws s3 sync %WATCH_DIR% s3://%BUCKET_NAME%/ ^
    --delete ^
    --region %REGION% ^
    --cache-control "no-cache,no-store,must-revalidate" ^
    --exclude "*" ^
    --include "*.html" ^
    --include "*.json"

echo [%time%] Invalidating CloudFront cache...
aws cloudfront create-invalidation ^
    --distribution-id %DISTRIBUTION_ID% ^
    --paths "/*" > nul 2>&1

if %ERRORLEVEL% EQU 0 (
    echo [%time%] Sync complete!
    echo [%time%] Dashboard: https://d3soguz2qeegby.cloudfront.net
) else (
    echo [%time%] Sync complete but CloudFront invalidation failed
)

echo.
exit /b 0
