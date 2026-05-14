NaverPaperCrawler 배포판 사용법
==============================

1. zip 파일 압축을 풉니다.

2. Install_To_Desktop.bat 를 실행합니다.
   - 그냥 Enter를 누르면 바탕화면\NaverPaperCrawler 폴더에 설치됩니다.
   - 다른 위치에 설치하고 싶으면 원하는 폴더 경로를 입력하면 됩니다.
   - 설치가 끝나면 바탕화면에 NaverPaperCrawler 바로가기가 생깁니다.

3. 프로그램 실행
   - 바탕화면의 NaverPaperCrawler 바로가기를 실행하거나,
   - 설치 폴더 안의 Run_NaverPaperCrawler.bat 를 실행합니다.

4. 네이버 API 키 설정
   - 온라인 후보/API 보완 수집까지 쓰려면 Set_Naver_API_Key.bat 를 실행해서
     Naver Client ID와 Client Secret을 입력합니다.
   - 신문 지면 목록 수집만 쓸 때는 이 단계가 없어도 됩니다.

5. 데이터/설정 저장 위치
   프로그램 데이터는 설치 폴더가 아니라 아래 사용자 폴더에 저장됩니다.

   %USERPROFILE%\.naver_news_crawler

   설치 폴더 안의 Open_Data_Folder.bat 를 실행하면 이 폴더를 바로 열 수 있습니다.

6. 자동 실행 등록
   install_scheduler.bat 를 실행하면 Windows 작업 스케줄러에 자동 수집 작업이 등록됩니다.
   제거하려면 uninstall_scheduler.bat 를 실행합니다.

주의
----
- 배포 zip에는 제작자의 API 키가 들어있지 않습니다.
- .env 파일은 Set_Naver_API_Key.bat 를 실행한 사람의 컴퓨터에만 만들어집니다.
- Windows 보안 경고가 뜨면 "추가 정보" -> "실행"을 눌러야 할 수 있습니다.
