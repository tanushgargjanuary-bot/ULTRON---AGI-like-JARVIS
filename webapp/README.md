# ULTRON Web — first slice

This folder contains a separate Next.js web client. It does not replace the Windows desktop application.

## Included

- Next.js App Router.
- Google sign-in through Supabase Auth.
- Cookie-based server-side sessions.
- Verified server-side claims for the protected workspace.
- Sign-out.
- A clear placeholder until the Python agent service is connected.

This first slice does not run ULTRON's Python agent, store chat messages, or collect analytics. The composer stays disabled until a secure backend is available.

## Local setup

1. Create a Supabase project.
2. Copy .env.example to .env.local.
3. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY.
4. In Supabase Auth, enable the Google provider.
5. Create a Google OAuth Web application in Google Cloud.
6. Add your local and production site origins in Google Cloud.
7. Add the Supabase callback URL shown in the Supabase Google provider settings to Google's Authorized redirect URIs.
8. In Supabase URL Configuration, set the Site URL and allow these app callback URLs:
   - http://localhost:3000/auth/callback
   - https://YOUR-VERCEL-DOMAIN/auth/callback
9. Install and run:

       npm install
       npm run dev

The Google OAuth client secret belongs in the Supabase provider configuration. Do not put it in this repository or in a NEXT_PUBLIC_ variable.

## Vercel deployment

Create a Vercel project from this repository and set its Root Directory to webapp.

Add the two Supabase environment variables from .env.local to Vercel's Production and Preview environments. Add the final Vercel domain to Supabase's allowed redirect URLs and Google Cloud's authorized JavaScript origins.

## Security boundaries

- The browser receives only the Supabase publishable key. Never add a Supabase service-role key to this app.
- Server-side page checks use verified JWT claims.
- The Google login requests identity only. It does not request Gmail, Drive, Contacts, or other Google services.
- Do not store or sell raw conversations, personal details, or user memories.
- Before enabling chat storage, add per-user database policies, retention rules, export, and deletion controls.
- Before connecting the agent, put the Python service behind an authenticated API. Derive the user identity from the verified session on the server. Never trust a user ID sent by the browser.
- Keep AI provider keys server-side. A later BYOK flow must not put provider secrets in browser storage or client-visible environment variables.

## Next implementation slice

Connect /api/chat to a separately hosted Python worker. Vercel Functions are request-scoped and are not a persistent agent process. Use a job/streaming design that fits function limits, or keep the agent worker on a separate service.
