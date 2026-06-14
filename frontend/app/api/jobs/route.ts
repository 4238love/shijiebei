import { NextResponse } from "next/server";

export async function GET() {
  const backendUrl = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";
  const response = await fetch(`${backendUrl}/jobs`, { cache: "no-store" });
  const text = await response.text();

  return new NextResponse(text, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") ?? "application/json",
    },
  });
}
