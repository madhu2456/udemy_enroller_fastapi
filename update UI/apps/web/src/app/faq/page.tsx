import type { Metadata } from 'next';
import SiteNav from '@/components/SiteNav';
import SiteFooter from '@/components/SiteFooter';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'FAQ – Udemy Enroller',
  description:
    'Answers to the most common questions about the Udemy Enroller automation tool — how it works, security, filters, and Cookie vs Email login.',
  alternates: { canonical: 'https://udemyenroller.madhudadi.in/faq' },
};

const categories = [
  {
    label: 'How it Works',
    icon: (
      <svg className="w-4 h-4 text-[#2563EB]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M13 10V3L4 14h7v7l9-11h-7z"
        />
      </svg>
    ),
    faqs: [
      {
        q: 'How does the automated Udemy course enroller work?',
        a: 'The tool continuously monitors a curated list of coupon aggregator websites — sites like Real.Discount, Discudemy, Tutorialbar, and others. The moment a new 100% off Udemy coupon is detected, the engine validates it against your smart filters and applies it to your Udemy account via the Udemy API, enrolling you instantly without any manual action.',
      },
      {
        q: 'Which coupon aggregator sites does it monitor?',
        a: 'The open-source project ships with scrapers for the most popular coupon sites, including Real.Discount, Discudemy, and Tutorialbar. New scrapers are contributed regularly by the community. You can check the GitHub repository for the current list.',
      },
      {
        q: 'How fast does enrollment happen after a coupon is posted?',
        a: 'Typically under 2 seconds from detection to enrollment. Because the engine polls continuously and applies coupons programmatically via the API, it beats manual methods by orders of magnitude — reducing the chance of a coupon expiring before you claim it.',
      },
      {
        q: 'Does the tool work 24/7 without me being online?',
        a: 'Yes. Once the engine is running (either locally or on a server), it operates continuously in the background. You do not need to keep a browser or tab open.',
      },
    ],
  },
  {
    label: 'Security & Privacy',
    icon: (
      <svg className="w-4 h-4 text-[#2563EB]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
        />
      </svg>
    ),
    faqs: [
      {
        q: 'Is it safe to connect my Udemy account?',
        a: "Yes. The tool talks directly to Udemy's official API. Your credentials are used only to obtain a session token — the same way the Udemy website itself works. No credentials are logged, persisted, or transmitted to any third-party server. Because the project is fully open source, you can audit every line of code on GitHub.",
      },
      {
        q: 'Does the tool store my email or password anywhere?',
        a: "No. When you use Email Login, your credentials are sent directly to the Udemy API and are not written to disk or any database. The session token returned is used for subsequent requests and expires on Udemy's schedule. Cookie Login avoids sending your password entirely.",
      },
      {
        q: 'What data does the tool collect about me?',
        a: 'None. The tool does not collect, store, or transmit personal data. It acts purely as a local automation layer between your browser session and the Udemy API.',
      },
    ],
  },
  {
    label: 'Authentication',
    icon: (
      <svg className="w-4 h-4 text-[#2563EB]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
        />
      </svg>
    ),
    faqs: [
      {
        q: 'What is the difference between Email Login and Cookie Login?',
        a: 'Email Login uses your Udemy email and password to authenticate via the Udemy API. It is the simplest option but may trigger a CAPTCHA challenge on server or cloud environments. Cookie Login uses session cookies you extract from your browser — specifically access_token, client_id, and csrftoken — which avoids CAPTCHA entirely and is the recommended method for reliability.',
      },
      {
        q: 'I got a CSRF error with Email Login. What do I do?',
        a: "Switch to Cookie Login. A CSRF error typically means Udemy's anti-bot system flagged the login request coming from the server's IP address. Cookie Login bypasses this because the token was already issued by Udemy to your real browser session.",
      },
      {
        q: 'How do I extract my Udemy cookies for Cookie Login?',
        a: 'Log in to udemy.com in Chrome or Firefox. Press F12 to open DevTools. Go to Application → Cookies → https://www.udemy.com. Find and copy the values for access_token, client_id, and csrftoken. Paste them into the Cookie Login form.',
      },
      {
        q: 'How long do my session cookies last before I need to refresh them?',
        a: 'Udemy session cookies typically last 30–90 days. When the engine starts returning authentication errors, simply repeat the cookie extraction process from your browser and update the values.',
      },
    ],
  },
  {
    label: 'Smart Filters',
    icon: (
      <svg className="w-4 h-4 text-[#2563EB]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2a1 1 0 01-.293.707L13 13.414V19a1 1 0 01-.553.894l-4 2A1 1 0 017 21v-7.586L3.293 6.707A1 1 0 013 6V4z"
        />
      </svg>
    ),
    faqs: [
      {
        q: 'Can I filter which courses are automatically enrolled?',
        a: 'Yes. The smart filter system lets you define a minimum course rating (e.g. only 4.0+), a preferred language (e.g. English only), and a blocklist of instructor names to skip. Only courses that pass all your filters will be enrolled.',
      },
      {
        q: 'Can I exclude courses from a specific instructor?',
        a: "Yes. Add the instructor's name to your exclusion list and the engine will skip any course published by them, regardless of rating or language.",
      },
      {
        q: 'Will it enroll me in courses outside my preferred language?',
        a: 'Only if you allow it. By setting a language filter, the engine will skip any course whose listed language does not match your preference.',
      },
    ],
  },
];

export default function FaqPage() {
  return (
    <div
      style={{ fontFamily: "'Inter', -apple-system, sans-serif" }}
      className="min-h-screen bg-white text-gray-900"
    >
      <SiteNav />

      <main>
        {/* Hero */}
        <section className="max-w-6xl mx-auto px-6 pt-14 pb-10" aria-labelledby="faq-hero-heading">
          <div className="max-w-2xl">
            <span className="inline-flex items-center gap-1.5 bg-[#EFF6FF] text-[#2563EB] rounded-full px-3 py-1 text-xs font-medium mb-4">
              Support
            </span>
            <h1
              id="faq-hero-heading"
              className="text-3xl font-semibold text-gray-900 tracking-tight mb-3"
            >
              Frequently Asked Questions
            </h1>
            <p className="text-sm text-gray-500 leading-relaxed">
              Everything you need to know about how the Udemy Enroller works, how to set it up, and
              how to keep your account secure.
            </p>
          </div>
        </section>

        {/* FAQ Categories */}
        <section className="max-w-6xl mx-auto px-6 pb-20">
          <div className="space-y-10">
            {categories.map((cat) => (
              <div key={cat.label}>
                {/* Category header */}
                <div className="flex items-center gap-2 mb-4">
                  <div className="inline-flex items-center justify-center w-7 h-7 rounded-lg bg-[#EFF6FF] border border-blue-100">
                    {cat.icon}
                  </div>
                  <h2 className="text-base font-semibold text-gray-900">{cat.label}</h2>
                </div>

                {/* Q&A list */}
                <div className="bg-white rounded-xl border border-gray-200 divide-y divide-gray-200">
                  {cat.faqs.map((faq) => (
                    <div key={faq.q} className="px-6 py-5">
                      <h3 className="text-sm font-semibold text-gray-900 mb-2">{faq.q}</h3>
                      <p className="text-sm text-gray-500 leading-relaxed">{faq.a}</p>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* Still have questions CTA */}
          <div className="mt-12 bg-[#F9FAFB] rounded-xl border border-gray-200 p-8 text-center">
            <p className="text-sm font-semibold text-gray-900 mb-1">Still have a question?</p>
            <p className="text-sm text-gray-500 mb-5">
              Open an issue on GitHub or check the guides for step-by-step walkthroughs.
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
              <a
                href="https://github.com/madhu2456/udemy_enroller_fastapi/issues"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 bg-white border border-gray-200 text-gray-700 rounded-lg px-4 py-2 text-xs font-semibold hover:border-gray-300 hover:bg-gray-50 transition-colors duration-150"
              >
                Open a GitHub Issue
              </a>
              <Link
                href="/guides"
                className="inline-flex items-center gap-2 bg-[#2563EB] text-white rounded-lg px-4 py-2 text-xs font-semibold hover:bg-blue-700 transition-colors duration-150"
              >
                Browse Guides →
              </Link>
            </div>
          </div>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
