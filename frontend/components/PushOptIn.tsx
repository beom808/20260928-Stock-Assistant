"use client";

// (선택) FCM 웹푸시 구독 버튼. NEXT_PUBLIC_FIREBASE_* 환경변수가 없으면 렌더하지 않는다.
import { useState } from "react";

const cfg = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
};
const VAPID = process.env.NEXT_PUBLIC_FIREBASE_VAPID_KEY;
const API = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export function PushOptIn() {
  const [state, setState] = useState<"idle" | "busy" | "on" | "error">("idle");
  if (!cfg.apiKey || !cfg.projectId || !cfg.appId || !VAPID) return null;

  async function subscribe() {
    setState("busy");
    try {
      if ((await Notification.requestPermission()) !== "granted") throw new Error("denied");
      const { initializeApp, getApps } = await import("firebase/app");
      const { getMessaging, getToken } = await import("firebase/messaging");
      const app = getApps()[0] ?? initializeApp(cfg);
      const reg = await navigator.serviceWorker.register(
        `/firebase-messaging-sw.js?config=${encodeURIComponent(JSON.stringify(cfg))}`,
      );
      const token = await getToken(getMessaging(app), { vapidKey: VAPID, serviceWorkerRegistration: reg });
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

  return (
    <button className="push-btn" onClick={subscribe} disabled={state === "busy" || state === "on"}>
      {state === "on" ? "알림 켜짐" : state === "error" ? "알림 설정 실패" : "발행 알림 받기"}
    </button>
  );
}
