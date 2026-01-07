import type { Metadata } from 'next';
import { Space_Grotesk } from 'next/font/google';
import './globals.css';
import Providers from './providers';

const grotesk = Space_Grotesk({
  subsets: ['latin'],
  variable: '--font-grotesk'
});

export const metadata: Metadata = {
  title: 'Dawn — Immersive Data Copilot',
  description:
    'Upload workbooks, curate context, and pilot the Dawn agent swarm in a cinematic, responsive UI.',
  icons: [{ rel: 'icon', url: '/favicon.ico' }]
};

export default function RootLayout({
  children
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={`${grotesk.variable} bg-dawn-background text-slate-100`}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
