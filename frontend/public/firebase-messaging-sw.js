/* FCM 웹푸시 서비스워커 (선택 기능). 설정값은 등록 시 쿼리스트링으로 전달된다. */
importScripts("https://www.gstatic.com/firebasejs/12.19.0/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/12.19.0/firebase-messaging-compat.js");

const params = new URL(self.location.href).searchParams;
const config = JSON.parse(params.get("config") || "{}");
if (config.apiKey) {
  firebase.initializeApp(config);
  firebase.messaging(); // notification 페이로드는 SDK 가 자동 표시
}

// 브라우저가 푸시 구독을 바꾸거나 만료시키면 열려 있는 화면에 알려, 토큰을 새로 받아 서버에 다시 등록하게 한다.
// (화면이 닫혀 있으면 다음에 사이트를 열 때 PushOptIn 의 자동 갱신이 처리한다)
self.addEventListener("pushsubscriptionchange", (event) => {
  event.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((list) => list.forEach((c) => c.postMessage({ type: "push-resubscribe" }))),
  );
});

// 앱이 업데이트되면 기다리지 않고 바로 새 서비스워커로 교체(옛 코드가 알림을 처리하는 일을 막는다)
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
