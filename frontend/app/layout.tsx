import type { Metadata } from "next";
import Link from "next/link";
import { Disclaimer } from "@/components/Disclaimer";
import { PullToRefresh } from "@/components/PullToRefresh";
import { PushOptIn } from "@/components/PushOptIn";
import "./globals.css";

export const metadata: Metadata = {
  title: "한미 증시 리서치 보조",
  description: "전일 미국장·국장 관전 포인트·국장 마감 리포트 (투자자문 아님)",
  // 홈 화면에 추가한 웹앱(특히 iPhone)에서 웹 푸시를 받기 위한 설정
  manifest: "/manifest.webmanifest",
  icons: { icon: "/icon-192.png", apple: "/apple-touch-icon.png" },
  appleWebApp: { capable: true, title: "증시 리서치", statusBarStyle: "black-translucent" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>
        <PullToRefresh />
        <header className="topbar">
          <Link href="/" className="brand">
            한미 증시 리서치 보조
          </Link>
          <nav>
            <Link href="/report/us-close">미국 마감</Link>
            <Link href="/report/kr-watchlist">국장 관전 포인트</Link>
            <Link href="/report/kr-close-and-calendar">국장 마감·캘린더</Link>
          </nav>
          <PushOptIn />
        </header>
        <main className="container">{children}</main>
        <Disclaimer />
      </body>
    </html>
  );
}
