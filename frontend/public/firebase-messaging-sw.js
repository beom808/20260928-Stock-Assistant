/* FCM 웹푸시 서비스워커 (선택 기능). 설정값은 등록 시 쿼리스트링으로 전달된다. */
importScripts("https://www.gstatic.com/firebasejs/12.19.0/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/12.19.0/firebase-messaging-compat.js");

const params = new URL(self.location.href).searchParams;
const config = JSON.parse(params.get("config") || "{}");
if (config.apiKey) {
  firebase.initializeApp(config);
  firebase.messaging(); // notification 페이로드는 SDK 가 자동 표시
}
