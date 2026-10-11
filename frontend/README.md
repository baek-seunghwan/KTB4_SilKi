# SILKI Frontend

## 음성 주문 실행

QR 코드에서 매장 UUID를 읽은 뒤 Spring 주문 세션과 단기 AI 토큰을 발급하고, 브라우저가
FastAPI의 `/ai/ws`에 직접 연결합니다. 마이크 입력은 AudioWorklet에서 16 kHz, mono,
PCM16 little-endian 20 ms(640 byte) 프레임으로 변환합니다. WebRTC/P2P/STUN/TURN은
사용하지 않습니다.

```bash
cp .env.example .env.local
npm install
npm run dev
```

CloudFront가 같은 오리진의 `/api/*`와 `/ai/ws`를 각각 Spring/FastAPI로 라우팅하는 운영
환경에서는 `VITE_API_BASE_URL`과 `VITE_AI_WS_URL`을 비워둘 수 있습니다. 서로 다른 개발
서버를 사용할 때만 `.env.local`에 전체 주소를 지정합니다.

AI 액세스 토큰은 `session.start` 전송을 위한 함수 지역 변수에만 존재하며 React 상태,
URL, `localStorage`, `sessionStorage`, 로그에 저장하지 않습니다. WebSocket을 다시 연결할
때마다 Spring에서 새 토큰을 발급합니다.

인증 완료 전에는 마이크를 열거나 오디오를 보내지 않습니다. FE는 `session.ready`의
`orderSessionId`와 `storeId`가 Spring 주문 세션 응답과 정확히 같은지 확인하고, 다르면
WebSocket을 1008로 종료합니다. 후보와 안내 음성은 `sessionId`·`turnId`로 상관관계를
검증하며 이전 턴에서 늦게 도착한 응답은 화면과 재생에서 제외합니다.

AI의 `tts.audio`는 `mediaType`과 `audioBase64`를 사용해 재생합니다. 재생 중에는 마이크를
일시 중지해 안내 음성이 새 발화로 인식되지 않게 합니다. 서버 음성 재생이 실패하면 브라우저
한국어 음성 합성을 짧게 시도하고, 시작하지 않더라도 모달을 잠그지 않습니다. 모달의
`안내 다시 듣기`로 재생을 다시 시도할 수 있으며, 재생 실패는 추천 결과나 WebSocket을
종료하지 않습니다.

`/voice-order`는 기존 상단 바와 음성 입력 화면을 유지하고, 질문·최종 확인만 화면 내부
모달로 표시합니다. 인라인 추천 카드와 장바구니 영역은 표시하지 않습니다. 모달의 `×` 또는
Escape로 음성 대화를 취소하면 마이크와 AI WebSocket만 정리되고 Spring 주문 세션과 이미
반영된 장바구니는 유지됩니다.

브라우저 마이크 API는 보안 컨텍스트가 필요하므로 배포 환경은 HTTPS/WSS를 사용해야 합니다.

## Vite 기본 안내

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and [`typescript-eslint`](https://typescript-eslint.io) in your project.
