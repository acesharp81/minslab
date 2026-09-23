import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ㅁㅁㅈ · 뭐먹지?",
  description: "누구나, 자기 말로 주문할 수 있게.",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
