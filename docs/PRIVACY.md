# 개인정보 처리방침 — Session Keeper for Claude Code

최종 수정: 2026-11-03

Session Keeper for Claude Code(이하 "앱")는 **어떤 개인정보도 수집하거나 외부로 전송하지 않습니다.** 앱은 네트워크 통신 기능이 없습니다.

## 앱이 이 PC에서 읽는 정보
- 실행 중인 프로세스 목록, 각 프로세스의 실행 경로, 명령줄, 작업 폴더: Claude Code와 Claude Desktop을 찾는 데 씁니다.
- Claude Desktop 창의 제목과 위치: 창 배치를 복원하는 데 씁니다.
- `%USERPROFILE%\.claude\projects\` 안 대화 기록 파일의 앞부분: 세션 제목(첫 질문)을 표시하는 데 씁니다.

## 앱이 이 PC에 쓰는 정보
- 스냅샷, 설정, 세션 매핑 기록: 앱 데이터 폴더(설정 탭에 경로 표시)
- `%USERPROFILE%\.claude\settings.json`: 사용자가 **훅 설치/제거 버튼을 누를 때만** 수정하며, 수정 전 백업을 만듭니다.
- 포터블 버전의 "Windows 시작 시 실행": `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`

## 삭제
- 훅 제거 후 앱 데이터 폴더를 삭제하면 앱이 남긴 정보가 모두 지워집니다.
- 스토어 버전은 앱을 제거하면 데이터 폴더도 함께 삭제됩니다. 훅은 제거 전에 앱에서 직접 해제하세요.

## 문의
<GitHub 저장소 Issues URL>
