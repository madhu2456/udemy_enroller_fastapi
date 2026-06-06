import type { ReactNode } from 'react';
import type { Metadata } from 'next';
import './global.css';
import { Providers } from './providers';

const SITE_URL = 'https://udemyenroller.madhudadi.in';
const SITE_NAME = 'Udemy Enroller – Free Udemy Courses Automation';
const SITE_DESCRIPTION =
  'Automatically claim 100% off Udemy courses and free Udemy coupons. Our automated Udemy course enroller monitors top coupon aggregator sites and enrolls you instantly — no manual hunting required.';

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: 'Free Udemy Courses Automation | Udemy Enroller by Madhu Dadi',
    template: '%s | Udemy Enroller',
  },
  description: SITE_DESCRIPTION,
  keywords: [
    'free udemy courses',
    'udemy 100% off coupons',
    'automated udemy enroller',
    'udemy free coupon 2025',
    'udemy course automation',
    'udemy promo codes',
    'free online courses with certificates',
    'udemy enroller tool',
    'udemy coupon scraper',
  ],
  authors: [{ name: 'Madhu Dadi', url: 'https://madhudadi.in' }],
  creator: 'Madhu Dadi',
  publisher: 'Madhu Dadi',
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      'max-video-preview': -1,
      'max-image-preview': 'large',
      'max-snippet': -1,
    },
  },
  openGraph: {
    type: 'website',
    locale: 'en_US',
    url: SITE_URL,
    siteName: SITE_NAME,
    title: 'Free Udemy Courses Automation | Udemy Enroller by Madhu Dadi',
    description: SITE_DESCRIPTION,
    images: [
      {
        url: `${SITE_URL}/og-image.png`,
        width: 1200,
        height: 630,
        alt: 'Udemy Enroller – Automate Free Udemy Course Enrollment',
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Free Udemy Courses Automation | Udemy Enroller',
    description: SITE_DESCRIPTION,
    creator: '@madhudadi',
    images: [`${SITE_URL}/og-image.png`],
  },
  alternates: {
    canonical: SITE_URL,
  },
  icons: {
    icon: '/favicon.png',
    shortcut: '/favicon.png',
    apple: '/favicon.png',
  },
  category: 'education',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  const jsonLd = {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'WebSite',
        '@id': `${SITE_URL}/#website`,
        url: SITE_URL,
        name: 'Udemy Enroller',
        description: SITE_DESCRIPTION,
        publisher: { '@id': `${SITE_URL}/#organization` },
        inLanguage: 'en-US',
      },
      {
        '@type': 'Organization',
        '@id': `${SITE_URL}/#organization`,
        name: 'Madhu Dadi',
        url: 'https://madhudadi.in',
        sameAs: ['https://github.com/madhu2456'],
      },
      {
        '@type': 'SoftwareApplication',
        '@id': `${SITE_URL}/#app`,
        name: 'Udemy Enroller',
        url: SITE_URL,
        applicationCategory: 'EducationalApplication',
        operatingSystem: 'Web',
        offers: {
          '@type': 'Offer',
          price: '0',
          priceCurrency: 'USD',
        },
        description:
          'An open-source automated tool that monitors coupon aggregator sites and enrolls users into free 100% off Udemy courses automatically.',
        creator: { '@id': `${SITE_URL}/#organization` },
        featureList: [
          'Automated Udemy course enrollment',
          '100% off coupon monitoring',
          'Smart filters by rating, language, and instructor',
          'Email and Cookie-based Udemy authentication',
          'Real-time savings tracker',
        ],
      },
      {
        '@type': 'FAQPage',
        '@id': `${SITE_URL}/#faq`,
        mainEntity: [
          {
            '@type': 'Question',
            name: 'How does the automated Udemy course enroller work?',
            acceptedAnswer: {
              '@type': 'Answer',
              text: 'The Udemy Enroller monitors popular coupon aggregator websites in real-time. When a new 100% off Udemy coupon is detected, it automatically applies the coupon to your Udemy account and enrolls you in the course — all without manual intervention.',
            },
          },
          {
            '@type': 'Question',
            name: 'Is it safe to use my Udemy credentials?',
            acceptedAnswer: {
              '@type': 'Answer',
              text: "Yes. The tool uses Udemy's direct API integration. Your credentials are used only to generate a temporary authentication token. No credentials are stored on any server. You can also use Cookie Login as an alternative to avoid sharing your password.",
            },
          },
          {
            '@type': 'Question',
            name: 'What is the difference between Email Login and Cookie Login?',
            acceptedAnswer: {
              '@type': 'Answer',
              text: 'Email Login uses your Udemy email and password to authenticate, but may trigger a CAPTCHA on some servers. Cookie Login uses your Udemy session cookies (access_token, client_id, csrftoken) extracted from your browser, which is more reliable and avoids CAPTCHA challenges.',
            },
          },
          {
            '@type': 'Question',
            name: 'How do I get free Udemy courses with 100% off coupons?',
            acceptedAnswer: {
              '@type': 'Answer',
              text: 'Connect your Udemy account using either Email or Cookie Login, set your preferred filters (language, minimum rating, excluded instructors), and the tool will automatically find and apply 100% off Udemy coupons to enroll you in free courses.',
            },
          },
          {
            '@type': 'Question',
            name: 'Is the Udemy Enroller free and open source?',
            acceptedAnswer: {
              '@type': 'Answer',
              text: 'Yes. The Udemy Enroller is completely free to use and is open source. The source code is available on GitHub. You can star the repository to stay updated with new coupon source scrapers.',
            },
          },
          {
            '@type': 'Question',
            name: 'Can I filter which Udemy courses are automatically enrolled?',
            acceptedAnswer: {
              '@type': 'Answer',
              text: 'Yes. The smart filter system lets you exclude specific instructors, filter by language, and set a minimum course rating threshold. This ensures the tool only enrolls you in courses that match your learning preferences.',
            },
          },
        ],
      },
      {
        '@type': 'HowTo',
        '@id': `${SITE_URL}/#howto`,
        name: 'How to automatically enroll in free Udemy courses',
        description:
          'Step-by-step guide to connect your Udemy account and start automatically claiming free 100% off Udemy courses.',
        step: [
          {
            '@type': 'HowToStep',
            position: 1,
            name: 'Connect Your Udemy Account',
            text: 'Choose Email Login or Cookie Login to authenticate your Udemy account with the enroller tool.',
          },
          {
            '@type': 'HowToStep',
            position: 2,
            name: 'Set Your Smart Filters',
            text: 'Configure your preferences: minimum course rating, preferred language, and instructors to exclude.',
          },
          {
            '@type': 'HowToStep',
            position: 3,
            name: 'Start the Automation',
            text: 'Activate the engine. It will continuously monitor coupon aggregator sites and automatically enroll you in free Udemy courses.',
          },
          {
            '@type': 'HowToStep',
            position: 4,
            name: 'Track Your Savings',
            text: 'Watch your lifetime educational savings grow in real-time as courses are claimed automatically.',
          },
        ],
        tool: {
          '@type': 'HowToTool',
          name: 'Udemy Enroller Tool',
        },
      },
    ],
  };

  return (
    <html lang="en">
      <head>
        <link
          rel="stylesheet"
          href="/fontawesome/releases/v6.3.0/css/pro.min.css?token=2c15cc0cc7"
        />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
        />
      </head>
      <body style={{ fontFamily: "'Inter', -apple-system, sans-serif" }}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
