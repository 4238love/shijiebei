import { NextRequest, NextResponse } from "next/server";

type RouteContext = {
  params: Promise<{ id: string }>;
};

export async function POST(_request: NextRequest, context: RouteContext) {
  const { id } = await context.params;
  const backendUrl = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";
  const response = await fetch(`${backendUrl}/jobs/${encodeURIComponent(id)}/run`, {
    method: "POST",
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
