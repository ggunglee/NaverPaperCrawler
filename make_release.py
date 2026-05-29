import os
import shutil
import sys
import subprocess
import zipfile
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(PROJECT_DIR, "dist")
APP_NAME = "NaverPaperCrawler"
RELEASE_DIR = os.path.join(DIST_DIR, APP_NAME)

def log(msg):
    print(f"[*] {msg}", flush=True)

def run_command(cmd, shell=False):
    completed = subprocess.run(cmd, shell=shell, text=True, capture_output=True)
    if completed.returncode != 0:
        print(completed.stderr)
        raise RuntimeError(f"Command failed with exit code {completed.returncode}: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    return completed.stdout

def build_app():
    log("PyInstaller 빌드를 시작합니다. (이 작업은 1~2분 정도 소요될 수 있습니다...)")
    
    # 가상환경 경로 확인
    python_exe = sys.executable
    pyinstaller_exe = os.path.join(os.path.dirname(python_exe), "pyinstaller")
    if not os.path.exists(pyinstaller_exe) and os.name == 'nt':
        pyinstaller_exe += ".exe"
        
    if not os.path.exists(pyinstaller_exe):
        log("PyInstaller가 현재 가상환경에 설치되어 있지 않습니다. 요구사항을 설치합니다.")
        run_command([python_exe, "-m", "pip", "install", "pyinstaller", "PySide6", "requests", "beautifulsoup4"])
        
    # PyInstaller 빌드 명령 수행 (--onedir 모드로 고정 이름 빌드)
    cmd = [
        pyinstaller_exe,
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name", APP_NAME,
        "main.py"
    ]
    log(f"빌드 명령어 실행: {' '.join(cmd)}")
    run_command(cmd)
    log("PyInstaller 빌드 완료.")

def copy_additional_files():
    log("추가 배치 파일 및 설정 템플릿 파일을 생성합니다.")
    
    # 1. 실행하기 배치 파일
    run_bat_path = os.path.join(RELEASE_DIR, "1_아침보고_실행하기.bat")
    with open(run_bat_path, "w", encoding="cp949") as f:
        f.write("@echo off\n")
        f.write("cd /d \"%~dp0\"\n")
        f.write(f"start \"\" \"{APP_NAME}.exe\"\n")
        
    # 2. 작업 스케줄러 등록 배치 파일
    install_bat_path = os.path.join(RELEASE_DIR, "2_자동실행_등록하기(매일오전6시).bat")
    with open(install_bat_path, "w", encoding="cp949") as f:
        f.write("@echo off\n")
        f.write("cd /d \"%~dp0\"\n")
        f.write("echo [!] 매일 오전 6시에 자동으로 아침보고를 수집하고 텔레그램을 보내는 스케줄을 등록합니다.\n")
        f.write("echo [!] 관리자 권한이 요구될 수 있습니다.\n")
        f.write("call install_scheduler.bat\n")
        
    # 3. 작업 스케줄러 해제 배치 파일
    uninstall_bat_path = os.path.join(RELEASE_DIR, "3_자동실행_해제하기.bat")
    with open(uninstall_bat_path, "w", encoding="cp949") as f:
        f.write("@echo off\n")
        f.write("cd /d \"%~dp0\"\n")
        f.write("echo [!] 등록된 윈도우 자동실행 작업을 해제합니다.\n")
        f.write("call uninstall_scheduler.bat\n")

    # 4. 사용 설명서 텍스트 작성
    readme_path = os.path.join(RELEASE_DIR, "사용설명서.txt")
    readme_content = """[아침보고 수집 프로그램 사용설명서]

본 프로그램은 파이썬이 설치되지 않은 환경에서도 동작하도록 제작된 독립 실행 프로그램입니다.
공유받으신 압축 파일(.zip)을 편하신 경로(예: C드라이브, 바탕화면 등)에 압축 해제하여 사용해 주세요.

■ 구성 파일 목록
1. "1_아침보고_실행하기.bat"
   - 더블클릭하면 아침보고 수집 및 검색 GUI 화면을 실행합니다.
   
2. "2_자동실행_등록하기(매일오전6시).bat"
   - 이 배치 파일을 더블클릭하면 윈도우 스케줄러에 작업이 등록됩니다.
   - 매일 오전 6시에 컴퓨터가 켜져 있으면 자동으로 지면/온라인 기사를 긁어와 텔레그램으로 아침보고를 발송합니다.
   
3. "3_자동실행_해제하기.bat"
   - 등록했던 윈도우 자동실행 태스크를 삭제하고 스케줄을 해제합니다.

4. ".env" (설정 파일)
   - 텔레그램 봇 토큰(TELEGRAM_BOT_TOKEN) 및 텔레그램 수신자 ID(TELEGRAM_CHAT_ID)가 적혀있는 숨겨진 설정 파일입니다.
   - 메모장으로 열어서 값을 수정하실 수 있습니다.

■ 업데이트 및 패치 방법
- 나중에 소스 코드 업데이트가 필요한 경우, 무거운 라이브러리 전체를 다시 다운로드받으실 필요가 없습니다.
- 개발자가 전달한 'NaverPaperCrawler_UpdatePatch.zip' 내부의 "NaverPaperCrawler.exe" 파일만 이 폴더 안에 기존 파일 위로 덮어쓰기(overwrite) 하시면 즉시 업데이트가 반영됩니다.
"""
    with open(readme_path, "w", encoding="cp949") as f:
        f.write(readme_content)

    # 5. 스케줄러 설치 스크립트 등 복사
    shutil.copy(os.path.join(PROJECT_DIR, "install_scheduler.bat"), os.path.join(RELEASE_DIR, "install_scheduler.bat"))
    shutil.copy(os.path.join(PROJECT_DIR, "uninstall_scheduler.bat"), os.path.join(RELEASE_DIR, "uninstall_scheduler.bat"))
    
    # 6. env 파일 복사 (없으면 기본값 생성)
    env_src = os.path.join(PROJECT_DIR, ".env")
    env_dest = os.path.join(RELEASE_DIR, ".env")
    if os.path.exists(env_src):
        shutil.copy(env_src, env_dest)
    else:
        with open(env_dest, "w", encoding="utf-8") as f:
            f.write("TELEGRAM_BOT_TOKEN=봇_토큰_입력\nTELEGRAM_CHAT_ID=채팅_방_ID_입력\n")
            
    log("추가 파일 배치 완료.")

def compress_release_zip():
    stamp = datetime.now().strftime("%Y%m%d")
    zip_filename = f"NaverPaperCrawler_Release_{stamp}.zip"
    zip_filepath = os.path.join(DIST_DIR, zip_filename)
    
    log(f"전체 배포용 zip 파일을 압축합니다: {zip_filename}")
    with zipfile.ZipFile(zip_filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(RELEASE_DIR):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, DIST_DIR)
                zipf.write(file_path, arcname)
    log(f"배포용 ZIP 압축 완료 -> {zip_filepath}")

def compress_update_patch():
    zip_filename = "NaverPaperCrawler_UpdatePatch.zip"
    zip_filepath = os.path.join(DIST_DIR, zip_filename)
    exe_filepath = os.path.join(RELEASE_DIR, f"{APP_NAME}.exe")
    
    if not os.path.exists(exe_filepath):
        log("오류: 업데이트용 exe 파일을 찾을 수 없습니다.")
        return
        
    log(f"업데이트 전용 패치 zip 파일을 압축합니다: {zip_filename}")
    with zipfile.ZipFile(zip_filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # zip 파일 안에 폴더 경로를 유지하되 exe만 넣거나 루트에 넣음
        # 사용자가 덮어쓰기 편하게 "NaverPaperCrawler/NaverPaperCrawler.exe" 형태로 압축
        zipf.write(exe_filepath, f"{APP_NAME}/{APP_NAME}.exe")
    log(f"업데이트 패치 ZIP 압축 완료 -> {zip_filepath}")

def main():
    try:
        build_app()
        copy_additional_files()
        compress_release_zip()
        compress_update_patch()
        log("모든 배포용 패키지 제작 프로세스가 성공적으로 완료되었습니다!")
        log(f"출력 경로: {DIST_DIR}")
    except Exception as exc:
        log(f"배포 파일 제작 중 오류 발생: {exc}")
        sys.exit(1)

if __name__ == "__main__":
    main()
