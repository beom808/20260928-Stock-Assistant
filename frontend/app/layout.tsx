import type { Metadata } from "next";
import Link from "next/link";
import { Disclaimer } from "@/components/Disclaimer";
import { PushOptIn } from "@/components/PushOptIn";
import "./globals.css";

export const metadata: Metadata = {
  title: "한미 증시 리서치 보조",
  description: "전일 미국장·한국장 관전 포인트·국내 마감 리포트 (투자자문 아님)",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>
        <header className="topbar">
          <Link href="/" className="brand">
            한미 증시 리서치 보조
          </Link>
          <nav>
            <Link href="/report/us-close">미국 마감</Link>
            <Link href="/report/kr-watchlist">관전 포인트</Link>
            <Link href="/report/kr-close-and-calendar">국내 마감·캘린더</Link>
          </nav>
          <PushOptIn />
        </header>
        <main className="container">{children}</main>
        <Disclaimer />
      </body>
    </html>
  );
}
