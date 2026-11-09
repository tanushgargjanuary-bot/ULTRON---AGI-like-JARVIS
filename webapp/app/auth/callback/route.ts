import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

function safeNextUrl(value: string | null, origin: string) {
  try {
    const candidate = new URL(value || "/chat", origin);
    if (candidate.origin === origin) return candidate;
  } catch {
    // Invalid redirect destinations fall back to the workspace.
  }
  return new URL("/chat", origin);
}

export async function GET(request: NextRequest) {
  const url = new URL(request.url);
  const code = url.searchParams.get("code");
  const destination = safeNextUrl(url.searchParams.get("next"), url.origin);

  if (code) {
    try {
      const supabase = await createClient();
      const { error } = await supabase.auth.exchangeCodeForSession(code);
      if (!error) return NextResponse.redirect(destination);
    } catch {
      // Do not expose OAuth codes or provider tokens in error responses.
    }
  }

  return NextResponse.redirect(new URL("/login?error=oauth_callback", url.origin));
}
