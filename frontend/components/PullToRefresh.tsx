"use client";

// 홈 화면에 추가한 웹앱(iPhone 등)에는 브라우저의 '당겨서 새로고침'이 없다.
// 그 경우에만 화면 맨 위에서 아래로 당기면 새로고침(F5)되도록 직접 구현한다.
// (일반 브라우저 탭에서는 브라우저 자체 기능이 있으므로 중복 동작하지 않게 켜지 않는다)
import { useEffect, useState } from "react";

const THRESHOLD = 70; // 이만큼(px) 당긴 뒤 놓으면 새로고침
const MAX = 110;

function isStandalone(): boolean {
  if (typeof window === "undefined") return false;
  const nav = navigator as Navigator & { standalone?: boolean };
  return window.matchMedia("(display-mode: standalone)").matches || nav.standalone === true;
}

export function PullToRefresh() {
  const [pull, setPull] = useState(0);
  const [reloading, setReloading] = useState(false);

  useEffect(() => {
    if (!isStandalone() || !("ontouchstart" in window)) return;
    let startY: number | null = null;
    let dist = 0;

    const onStart = (e: TouchEvent) => {
      startY = window.scrollY <= 0 && e.touches.length === 1 ? e.touches[0].clientY : null;
      dist = 0;
    };
    const onMove = (e: TouchEvent) => {
      if (startY === null) return;
      const dy = e.touches[0].clientY - startY;
      if (dy <= 0 || window.scrollY > 0) {
        dist = 0;
        setPull(0);
        return;
      }
      e.preventDefault(); // 화면 전체가 같이 늘어나는(바운스) 동작 대신 표시만 움직인다
      dist = Math.min(MAX, dy * 0.5);
      setPull(dist);
    };
    const onEnd = () => {
      if (startY !== null && dist >= THRESHOLD) {
        setReloading(true);
        window.location.reload();
      } else {
        setPull(0);
      }
      startY = null;
      dist = 0;
    };

    window.addEventListener("touchstart", onStart, { passive: true });
    window.addEventListener("touchmove", onMove, { passive: false });
    window.addEventListener("touchend", onEnd);
    window.addEventListener("touchcancel", onEnd);
    return () => {
      window.removeEventListener("touchstart", onStart);
      window.removeEventListener("touchmove", onMove);
      window.removeEventListener("touchend", onEnd);
      window.removeEventListener("touchcancel", onEnd);
    };
  }, []);

  if (!reloading && pull <= 0) return null;
  const ready = pull >= THRESHOLD;
  return (
    <div className="ptr" style={{ transform: `translate(-50%, ${reloading ? 24 : pull - 40}px)` }} aria-live="polite">
      {reloading ? "새로고침 중…" : ready ? "↑ 놓으면 새로고침" : "↓ 당겨서 새로고침"}
    </div>
  );
}
