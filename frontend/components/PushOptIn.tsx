"use client";

// (선택) FCM 웹푸시 구독 버튼. NEXT_PUBLIC_FIREBASE_* 환경변수가 없으면 렌더하지 않는다.
// iPhone(iOS)은 사파리에서 '홈 화면에 추가'한 웹앱에서만 웹 푸시를 받을 수 있는 것으로 알려져 있다.
import { useEffect, useState } from "react";

const cfg = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
};
const VAPID = process.env.NEXT_PUBLIC_FIREBASE_VAPID_KEY;
const API = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/+$/, "");

type State = "idle" | "busy" | "on" | "denied" | "unsupported" | "error";

const LABEL: Record<State, string> = {
  idle: "발행 알림 받기",
  busy: "설정 중…",
  on: "알림 켜짐",
  denied: "알림이 차단됨(브라우저 설정에서 허용)",
  unsupported: "이 브라우저는 알림 미지원(iPhone은 홈 화면에 추가 후 사용)",
  error: "알림 설정 실패 — 다시 시도",
};

export function PushOptIn() {
  const [state, setState] = useState<State>("idle");
  const enabled = Boolean(cfg.apiKey && cfg.projectId && cfg.appId && cfg.messagingSenderId && VAPID);

  useEffect(() => {
    if (!enabled) return;
    const supported =
      typeof window !== "undefined" && "Notification" in window && "serviceWorker" in navigator && "PushManager" in window;
    if (!supported) setState("unsupported");
    else if (Notification.permission === "denied") setState("denied");
  }, [enabled]);

  if (!enabled) return null;

  async function subscribe() {
    setState("busy");
    try {
      const perm = await Notification.requestPermission();
      if (perm !== "granted") {
        setState(perm === "denied" ? "denied" : "idle");
        return;
      }
      const { initializeApp, getApps } = await import("firebase/app");
      const { getMessaging, getToken, isSupported } = await import("firebase/messaging");
      if (!(await isSupported())) {
        setState("unsupported");
        return;
      }
      const app = getApps()[0] ?? initializeApp(cfg);
      const reg = await navigator.serviceWorker.register(
        `/firebase-messaging-sw.js?config=${encodeURIComponent(JSON.stringify(cfg))}`,
      );
      const token = await getToken(getMessaging(app), { vapidKey: VAPID, serviceWorkerRegistration: reg });
      if (!token) throw new Error("no token");
      const res = await fetch(`${API}/push/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token }),
      });
      if (!res.ok) throw new Error(String(res.status));
      setState("on");
    } catch {
      setState("error");
    }
  }

  const clickable = state === "idle" || state === "error";
  return (
    <button className="push-btn" onClick={subscribe} disabled={!clickable}>
      {LABEL[state]}
    </button>
  );
}
