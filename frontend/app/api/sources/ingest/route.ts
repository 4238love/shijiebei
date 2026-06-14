import { NextRequest } from "next/server";

import { proxySourceOperation } from "../source-proxy";

export async function POST(request: NextRequest) {
  return proxySourceOperation(request, "ingest");
}
