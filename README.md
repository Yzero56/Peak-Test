# Peak-Test — 냉장고 지킴이

스마트 냉장고 대시보드 프론트엔드. 도어/가스 센서 상태, 식재료 D-day 시각화, 알림, 오늘의 추천 레시피를 보여줍니다. 자세한 프로젝트 배경과 규칙은 [CLAUDE.md](./CLAUDE.md) 참고.

[Expo](https://expo.dev) + React Native + NativeWind 기반이며, `create-expo-app`으로 스캐폴딩되었습니다.

## Get started

1. Install dependencies

   ```bash
   npm install
   ```

2. Start the app

   ```bash
   npx expo start
   ```

In the output, you'll find options to open the app in a

- [development build](https://docs.expo.dev/develop/development-builds/introduction/)
- [Android emulator](https://docs.expo.dev/workflow/android-studio-emulator/)
- [iOS simulator](https://docs.expo.dev/workflow/ios-simulator/)
- [Expo Go](https://expo.dev/go), a limited sandbox for trying out app development with Expo

You can start developing by editing the files inside the **app** directory. This project uses [file-based routing](https://docs.expo.dev/router/introduction).

이 저장소만 클론해서 `npm install` → `npx expo start`만 해도 앱은 바로 뜹니다 — 별도 설정 없이 `src/data/mock-fridge-data.ts`의 목업 데이터로 동작합니다(재고 추가/소비 등도 로컬에서만 유지됨, 앱 재시작하면 초기화). 이 상태로 UI/화면 흐름 확인은 충분합니다.

## 백엔드 연동 (선택)

재고를 실제 백엔드와 연동해서(팀원끼리 공유되는 재고로) 테스트하려면 앱 안 **설정 탭 → "백엔드 연결"** 카드에 서버 주소와 토큰을 입력해야 합니다. 두 가지 방법이 있습니다.

- **팀원이 이미 띄워둔 백엔드에 같이 접속** — 그 팀원에게 터널 URL(`https://xxxx.trycloudflare.com` 형태)과 토큰(관리자 비밀번호)을 받아서 입력. 별도 설치/실행 필요 없음. 단, 무료 Cloudflare Quick Tunnel URL은 상대방이 `cloudflared`를 재시작하면 바뀌니 매번 최신 URL을 다시 받아야 합니다.
- **자기 컴퓨터에서 직접 백엔드 실행** — `backend/README.md` 절차대로 FastAPI 백엔드를 로컬에 띄우고, 설정 화면에 `http://localhost:8000`(또는 같은 기기에서 접속 시) + 본인이 `backend/.env`에 설정한 `ADMIN_PASSWORD`를 입력. `backend/.env`는 `.gitignore`돼 있어서 저장소에 없으므로 `backend/.env.example`을 복사해서 직접 채워야 합니다. 이 경우 DB(`fridge.db`)도 완전히 별개라 팀원 백엔드와 데이터가 공유되지 않습니다.

ESP32 카메라 보드까지 연동하려면 `firmware/xiao-esp32s3-cam/README.md` 참고 (Wi-Fi/기기 토큰이 담긴 `secrets.h`도 `.gitignore`돼 있어 각자 채워야 함).

## Get a fresh project

When you're ready, run:

```bash
npm run reset-project
```

This command will move the starter code to the **app-example** directory and create a blank **app** directory where you can start developing.

### Other setup steps

- To set up ESLint for linting, run `npx expo lint`, or follow our guide on ["Using ESLint and Prettier"](https://docs.expo.dev/guides/using-eslint/)
- If you'd like to set up unit testing, follow our guide on ["Unit Testing with Jest"](https://docs.expo.dev/develop/unit-testing/)
- Learn more about the TypeScript setup in this template in our guide on ["Using TypeScript"](https://docs.expo.dev/guides/typescript/)

## Learn more

To learn more about developing your project with Expo, look at the following resources:

- [Expo documentation](https://docs.expo.dev/): Learn fundamentals, or go into advanced topics with our [guides](https://docs.expo.dev/guides).
- [Learn Expo tutorial](https://docs.expo.dev/tutorial/introduction/): Follow a step-by-step tutorial where you'll create a project that runs on Android, iOS, and the web.

## Join the community

Join our community of developers creating universal apps.

- [Expo on GitHub](https://github.com/expo/expo): View our open source platform and contribute.
- [Discord community](https://chat.expo.dev): Chat with Expo users and ask questions.
