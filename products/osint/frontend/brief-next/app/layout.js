import { Spectral } from 'next/font/google';
import './globals.css';

const spectral = Spectral({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  style: ['normal', 'italic'],
  display: 'swap',
  variable: '--font-spectral',
});

export const metadata = {
  title: 'RIG OSINT · Morning Brief',
  description: "RIG OSINT — Morning Brief. The principal's first read of the day.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={spectral.variable}>
      <body>{children}</body>
    </html>
  );
}
