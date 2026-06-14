import { NextRequest, NextResponse } from "next/server";

type SourceOperation = "ingest" | "validate";

export async function proxySourceOperation(
  request: NextRequest,
  operation: SourceOperation,
) {
  const backendUrl = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";
  const payload = await readJsonBody(request);

  const response = await fetch(`${backendUrl}/sources/${operation}`, {
    method: "POST",
    cache: "no-store",
    headers: {
      "content-type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return proxyJsonResponse(response);
}

async function readJsonBody(request: NextRequest): Promise<Record<string, unknown>> {
  try {
    return (await request.json()) as Record<string, unknown>;
  } catch {
    return {};
  }
}

async function proxyJsonResponse(response: Response) {
  const text = await response.text();

  return new NextResponse(text, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") ?? "application/json",
    },
  });
}
