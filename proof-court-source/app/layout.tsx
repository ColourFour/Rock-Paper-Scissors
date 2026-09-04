import type { Metadata } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import './globals.css';

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
});

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
});

export const metadata: Metadata = {
  title: 'Court of Proof',
  description: 'A courtroom game for learning mathematical proof.',
  openGraph: {
    title: 'Court of Proof',
    description: 'Make your case. Prove it.',
    type: 'website',
    images: [{ url: 'https://court-of-proof.sbrooker02.chatgpt.site/og.png', width: 1734, height: 907, alt: 'Court of Proof — Make your case. Prove it.' }],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Court of Proof',
    description: 'Make your case. Prove it.',
    images: ['https://court-of-proof.sbrooker02.chatgpt.site/og.png'],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
