import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export default async function HomePage() {
  if (!process.env.NEXT_PUBLIC_SUPABASE_URL || !process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY) {
    redirect("/login");
  }

  const supabase = await createClient();
  const { data, error } = await supabase.auth.getClaims();

  redirect(!error && data?.claims ? "/chat" : "/login");
}
