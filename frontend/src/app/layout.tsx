import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import Sidebar from '@/components/Sidebar';
import Header from '@/components/Header';
import { AssistantRail } from '@/components/AssistantRail';
import { SessionGate } from '@/components/session-gate';

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
      <body className={`${inter.className} h-full antialiased`} suppressHydrationWarning>
        {/*
          The shell renders only for a session that has a principal AND a workspace.
          Showing navigation to a signed-out visitor invites them to click through
          fifteen surfaces that will each fail on their own — see `session-gate.tsx`.
          `children` stays a Server Component: it is passed through as rendered output,
          not imported into the gate's module graph.
        */}
        <SessionGate>
          <div className="flex h-screen overflow-hidden bg-surface text-foreground">
            <Sidebar />
            <div className="flex min-w-0 flex-1 flex-col">
              <Header />
              <main className="flex-1 overflow-y-auto">{children}</main>
            </div>
            <AssistantRail />
          </div>
        </SessionGate>
      </body>
    </html>
  );
}
