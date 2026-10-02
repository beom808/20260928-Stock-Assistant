"use client";

// 리포트를 못 불러왔을 때의 안내. 무료 서버가 깨어나는 중이면 잠시 후 자동으로 다시 불러온다.
import { useEffect, useState } from "react";

const RETRY_SEC = 20;
const MAX_AUTO = 3; // 자동 새로고침 최대 횟수(무한 반복 방지)
const KEY = "auto_retry";
const WINDOW_MS = 5 * 60 * 1000; // 마지막 자동 새로고침 후 5분이 지나면 횟수를 다시 센다

function readCount(): number {
  try {
    const v = JSON.parse(sessionStorage.getItem(KEY) || "null") as { n: number; t: number } | null;
    return v && Date.now() - v.t < WINDOW_MS ? v.n : 0;
  } catch {
    return MAX_AUTO;
  }
}

export function LoadError({ message, waking }: { message: string; waking?: boolean }) {
  const [left, setLeft] = useState<number | null>(null);

  useEffect(() => {
    if (!waking) return;
    const n = readCount();
    if (n >= MAX_AUTO) return;
    setLeft(RETRY_SEC);
    const t = setInterval(() => {
      setLeft((s) => {
        if (s === null) return s;
        if (s <= 1) {
          clearInterval(t);
          try {
            sessionStorage.setItem(KEY, JSON.stringify({ n: n + 1, t: Date.now() }));
          } catch {
            /* 저장 불가여도 새로고침은 진행 */
          }
          window.location.reload();
          return 0;
        }
        return s - 1;
      });
    }, 1000);
    return () => clearInterval(t);
  }, [waking]);

  return (
    <div className="load-error">
      <p className="muted">{message}</p>
      {waking ? (
        <p className="small">
          {left !== null ? `${left}초 후 자동으로 다시 불러옵니다 · ` : ""}
          <button type="button" className="link-btn" onClick={() => window.location.reload()}>
            지금 새로고침
          </button>
        </p>
      ) : null}
    </div>
  );
}
