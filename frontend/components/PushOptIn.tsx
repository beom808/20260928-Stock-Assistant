"use client";

// (선택) FCM 웹푸시 '구독' 버튼. NEXT_PUBLIC_FIREBASE_* 환경변수가 없으면 렌더하지 않는다.
// - 구독: 알림 권한 → FCM 토큰 → POST /push/register (이 기기의 이전 토큰이 있으면 교체)
// - 구독 취소: POST /push/unregister + FCM 토큰 삭제
// - 구독자 수: GET /push/count (등록된 기기 토큰 수 = 기기(브라우저)당 1명)
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
const TOKEN_KEY = "push_token";

type State = "idle" | "busy" | "on" | "denied" | "unsupported" | "error";

const LABEL: Record<State, string> = {
  idle: "구독",
  busy: "처리 중…",
  on: "구독 취소",
  denied: "알림 차단됨(브라우저 설정에서 허용)",
  unsupported: "알림 미지원(iPhone은 홈 화면에 추가 후 사용)",
  error: "실패 — 다시 시도",
};

function readToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function writeToken(t: string | null) {
  try {
    if (t) localStorage.setItem(TOKEN_KEY, t);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* 저장 불가(사생활 보호 모드 등)여도 구독 자체는 동작 */
  }
}

async function post(path: string, body: object): Promise<number | null> {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(60000), // 무료 서버가 깨어나는 시간 포함
  });
  if (!res.ok) throw new Error(String(res.status));
  const j = (await res.json()) as { count?: number };
  return typeof j.count === "number" ? j.count : null;
}

async function messaging() {
  const { initializeApp, getApps } = await import("firebase/app");
  const m = await import("firebase/messaging");
  if (!(await m.isSupported())) return null;
  const app = getApps()[0] ?? initializeApp(cfg);
  return { m, messaging: m.getMessaging(app) };
}

export function PushOptIn() {
  const [state, setState] = useState<State>("idle");
  const [count, setCount] = useState<number | null>(null);
  const enabled = Boolean(cfg.apiKey && cfg.projectId && cfg.appId && cfg.messagingSenderId && VAPID);

  useEffect(() => {
    if (!enabled) return;
    const supported =
      typeof window !== "undefined" && "Notification" in window && "serviceWorker" in navigator && "PushManager" in window;
    if (!supported) setState("unsupported");
    else if (Notification.permission === "denied") setState("denied");
    else if (Notification.permission === "granted" && readToken()) setState("on");
    fetch(`${API}/push/count`, { signal: AbortSignal.timeout(60000) })
      .then((r) => (r.ok ? r.json() : null))
      .then((j: { count?: number } | null) => {
        if (j && typeof j.count === "number") setCount(j.count);
      })
      .catch(() => undefined);
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
      const fm = await messaging();
      if (!fm) {
        setState("unsupported");
        return;
      }
      const reg = await navigator.serviceWorker.register(
        `/firebase-messaging-sw.js?config=${encodeURIComponent(JSON.stringify(cfg))}`,
      );
      const token = await fm.m.getToken(fm.messaging, { vapidKey: VAPID, serviceWorkerRegistration: reg });
      if (!token) throw new Error("no token");
      const prev = readToken();
      const c = await post("/push/register", prev && prev !== token ? { token, replaces: prev } : { token });
      writeToken(token);
      if (c !== null) setCount(c);
      setState("on");
    } catch {
      setState("error");
    }
  }

  async function unsubscribe() {
    setState("busy");
    try {
      const token = readToken();
      if (token) {
        const c = await post("/push/unregister", { token });
        if (c !== null) setCount(c);
      }
      try {
        const fm = await messaging();
        if (fm) await fm.m.deleteToken(fm.messaging);
      } catch {
        /* 서버에서 이미 삭제했으므로 알림은 더 오지 않는다 */
      }
      writeToken(null);
      setState("idle");
    } catch {
      setState("error");
    }
  }

  const clickable = state === "idle" || state === "error" || state === "on";
  return (
    <div className="push">
      <button
        className={`push-btn ${state === "on" ? "on" : ""}`}
        onClick={state === "on" ? unsubscribe : subscribe}
        disabled={!clickable}
        title={state === "on" ? "누르면 발행 알림 구독을 취소합니다" : "리포트 발행 알림을 받습니다"}
      >
        {LABEL[state]}
      </button>
      <div className="push-count">구독자 {count === null ? "—" : `${count.toLocaleString("ko-KR")}명`}</div>
    </div>
  );
}
