# AX Change Rehearsal Windows 앱

Windows x64에서 ZIP을 모두 풀고 `AXRehearsal.exe`를 실행한다. PC에 .NET 10 Desktop Runtime과 Microsoft Edge WebView2 Runtime이 필요하다. 합성 실행 엔진의 Python은 ZIP에 포함된다.

위쪽 도구막대에서 변경 확인, 사례 선택, 실행, 차이 확인, 보관 기록으로 이동한다. 화면에서 정책 팩, FAQ와 모의 API의 버전을 골라 실행한 뒤, 결과 행을 선택해 근거와 독립 관찰 상태를 확인한다. Tab과 Enter로 작업 단계를 선택할 수 있다.

앱은 기존 합성 작업대를 자체 창에 열고 현재 사용자 로컬 폴더 `%LOCALAPPDATA%\AXChangeRehearsal\Evidence`에 기록을 저장한다. 다시 열어 이전 실행을 조회할 수 있다. `AXRehearsal.exe --profile <새 폴더>`로 시험용 프로필을 별도로 쓸 수 있다. 기록은 평문 합성 증거이며 조직 인증이나 배포 승인이 아니다.

ZIP은 x64 Python 3.12와 .NET 10 SDK, 로컬 NuGet 캐시의 Microsoft.Web.WebView2 1.0.4258.31에서 빌드한다. 기존 `python serve_workbench.py` 웹 실행도 계속 지원한다.

```powershell
python tools/build_windows_app.py --output C:\package\AXRehearsal-Windows-x64.zip
```
