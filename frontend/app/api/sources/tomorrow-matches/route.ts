import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const backendUrl = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";
  const targetDate = request.nextUrl.searchParams.get("target_date");
  const url = new URL(`${backendUrl}/sources/tomorrow-matches`);

  if (targetDate) {
    url.searchParams.set("target_date", targetDate);
  }

  const response = await fetch(url, {
    cache: "no-store",
  });
  const text = await response.text();

  return new NextResponse(text, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") ?? "application/json",
    },
  });
}
