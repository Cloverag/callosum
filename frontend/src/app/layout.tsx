import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import Sidebar from '@/components/Sidebar';
import Header from '@/components/Header';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'Meridian Board OS',
  description: 'Executive-level governance and institutional memory',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html className="h-full bg-[#051424]" lang="en">
      <body className={`${inter.className} h-full text-[#d4e4fa] antialiased bg-[#051424]`}>
        <div className="flex h-full">
          <Sidebar />
          <div className="flex flex-1 flex-col overflow-hidden">
            <Header />
            <main className="flex-1 overflow-y-auto bg-[#051424]">
              {children}
            </main>
          </div>
        </div>
      </body>
    </html>
  );
}
