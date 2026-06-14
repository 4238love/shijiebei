import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "世界杯预测工具",
  description: "由 DeepSeek/GPT 辅助的足球预测方法论看板。",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>
        <nav className="top-nav" aria-label="主导航">
          <a href="/">预测</a>
          <a href="/predictions">历史</a>
          <a href="/jobs">任务</a>
          <a href="/sources">数据源</a>
          <a href="/backtests">回测</a>
          <a href="/weights">权重</a>
          <a href="/reports">报告</a>
          <a href="/methodology">方法论</a>
        </nav>
        {children}
      </body>
    </html>
  );
}
