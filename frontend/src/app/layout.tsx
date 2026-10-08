import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import { AppShell } from '@/components/app-shell';
import { SessionGate } from '@/components/session-gate';
import { TooltipProvider } from '@/components/vendor/tooltip';
import { THEME_SCRIPT } from '@/components/theme';

const inter = Inter({ subsets: ['latin'], display: 'swap' });

export const metadata: Metadata = {
  title: 'Meridian Board OS',
  description: 'The governed institutional-memory layer for startup boards.',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/*
          Resolves the stored theme before first paint. Inline and synchronous
          on purpose: anything deferred runs after the document has already
          painted with the light tokens, which is the flash of wrong theme.
          It only ever writes an attribute this app defines.
        */}
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className={`${inter.className} h-full antialiased`} suppressHydrationWarning>
        {/*
          The shell renders only for a session that has a principal AND a workspace.
          Showing navigation to a signed-out visitor invites them to click through
          fifteen surfaces that will each fail on their own — see `session-gate.tsx`.
          `children` stays a Server Component: it is passed through as rendered output,
          not imported into the gate's module graph.
        */}
        {/*
          Base UI's tooltip reads its delay from a provider, where the Animate UI
          component it replaced wrapped each `<Tooltip>` in its own. One provider
          at the root is the same behaviour with one instance instead of N.
          `children` still passes through as rendered output, so it stays a
          Server Component across both client boundaries.
        */}
        <TooltipProvider>
          <SessionGate>
            <AppShell>{children}</AppShell>
          </SessionGate>
        </TooltipProvider>
      </body>
    </html>
  );
}
