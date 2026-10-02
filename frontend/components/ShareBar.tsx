"use client";

// 공유: 휴대폰 기본 공유창(카카오톡 등 설치된 앱 선택) · X · 링크 복사
import { useEffect, useState } from "react";

export function ShareBar({ title }: { title: string }) {
  const [canShare, setCanShare] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setCanShare(typeof navigator !== "undefined" && typeof navigator.share === "function");
  }, []);

  const url = () => window.location.href;
  const text = `${title} — 한미 증시 리서치 보조`;

  async function share() {
    try {
      await navigator.share({ title: text, url: url() });
    } catch {
      /* 사용자가 취소한 경우 등 */
    }
  }

  function shareX() {
    const u = `https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}&url=${encodeURIComponent(url())}`;
    window.open(u, "_blank", "noopener,noreferrer");
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(url());
    } catch {
      window.prompt("아래 주소를 복사하세요", url());
      return;
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="share-bar" aria-label="공유">
      {canShare ? (
        <button type="button" className="share-btn" onClick={share} title="카카오톡 등 휴대폰에 설치된 앱으로 공유">
          카카오톡 등 공유
        </button>
      ) : null}
      <button type="button" className="share-btn" onClick={shareX}>
        X
      </button>
      <button type="button" className="share-btn" onClick={copy}>
        {copied ? "복사됨 ✓" : "링크 복사"}
      </button>
    </div>
  );
}
