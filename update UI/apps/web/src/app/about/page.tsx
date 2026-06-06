import type { Metadata } from 'next';
import SiteNav from '@/components/SiteNav';
import SiteFooter from '@/components/SiteFooter';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'About – Udemy Enroller',
  description:
    'Learn about the Udemy Enroller project — an open-source automation tool built by Madhu Dadi to help learners automatically claim 100% off Udemy courses.',
  alternates: { canonical: 'https://udemyenroller.madhudadi.in/about' },
};

const values = [
  {
    title: 'Open Source First',
    description:
      'Every line of code is public on GitHub. No black boxes, no hidden scrapers, no mystery. Fork it, audit it, improve it.',
    icon: (
      <svg className="w-4 h-4 text-[#2563EB]" fill="currentColor" viewBox="0 0 24 24">
        <path d="M12 0C5.37 0 0 5.37 0 12c0 5.3 3.44 9.8 8.21 11.39.6.11.82-.26.82-.58v-2.03c-3.34.73-4.04-1.61-4.04-1.61-.55-1.39-1.34-1.76-1.34-1.76-1.09-.75.08-.73.08-.73 1.21.08 1.85 1.24 1.85 1.24 1.07 1.84 2.81 1.31 3.5 1 .11-.78.42-1.31.76-1.61-2.67-.3-5.47-1.33-5.47-5.93 0-1.31.47-2.38 1.24-3.22-.12-.3-.54-1.52.12-3.18 0 0 1.01-.32 3.3 1.23a11.5 11.5 0 013-.4c1.02.005 2.04.14 3 .4 2.28-1.55 3.29-1.23 3.29-1.23.66 1.66.24 2.88.12 3.18.77.84 1.24 1.91 1.24 3.22 0 4.61-2.81 5.63-5.49 5.92.43.37.82 1.1.82 2.22v3.29c0 .32.22.7.83.58C20.57 21.8 24 17.3 24 12c0-6.63-5.37-12-12-12z" />
      </svg>
    ),
  },
  {
    title: 'Privacy by Design',
    description:
      'No database, no accounts, no telemetry. Your credentials touch only the Udemy API — never our servers.',
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
  },
  {
    title: 'Free Forever',
    description:
      'No subscriptions, no freemium gates, no paywalled scrapers. Learning should be accessible to everyone.',
    icon: (
      <svg className="w-4 h-4 text-[#2563EB]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
        />
      </svg>
    ),
  },
  {
    title: 'Community Driven',
    description:
      'New coupon scrapers, bug fixes, and feature ideas all come from the community. Star the repo to stay updated.',
    icon: (
      <svg className="w-4 h-4 text-[#2563EB]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z"
        />
      </svg>
    ),
  },
];

const facts = [
  { value: '100% Off', label: 'Udemy coupon rate targeted' },
  { value: 'Open Source', label: 'Fully auditable on GitHub' },
  { value: 'Free', label: 'No cost to use, ever' },
  { value: 'FastAPI', label: 'Lightweight Python backend' },
];

export default function AboutPage() {
  return (
    <div
      style={{ fontFamily: "'Inter', -apple-system, sans-serif" }}
      className="min-h-screen bg-white text-gray-900"
    >
      <SiteNav />

      <main>
        {/* Hero */}
        <section className="max-w-6xl mx-auto px-6 pt-14 pb-12" aria-labelledby="about-heading">
          <div className="max-w-2xl">
            <span className="inline-flex items-center gap-1.5 bg-[#EFF6FF] text-[#2563EB] rounded-full px-3 py-1 text-xs font-medium mb-4">
              About
            </span>
            <h1
              id="about-heading"
              className="text-3xl font-semibold text-gray-900 tracking-tight mb-3"
            >
              Built to democratise online learning
            </h1>
            <p className="text-sm text-gray-500 leading-relaxed">
              Udemy Enroller is an open-source automation tool created by{' '}
              <a
                href="https://madhudadi.in"
                target="_blank"
                rel="noopener noreferrer"
                className="text-[#2563EB] hover:underline font-medium"
              >
                Madhu Dadi
              </a>{' '}
              to solve a simple but frustrating problem: free Udemy coupons expire within hours, and
              manually hunting for them is a losing game. The enroller monitors coupon aggregator
              sites around the clock and claims courses the moment they appear — so your learning
              never depends on perfect timing.
            </p>
          </div>
        </section>

        {/* Facts bar — only verifiable facts */}
        <section className="border-y border-gray-200 bg-[#F9FAFB] py-5" aria-label="Project facts">
          <div className="max-w-6xl mx-auto px-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
              {facts.map(({ value, label }) => (
                <div key={label} className="text-center">
                  <p className="text-lg font-semibold text-gray-900 tracking-tight">{value}</p>
                  <p className="text-xs text-gray-500 mt-0.5">{label}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Mission + Creator */}
        <section className="max-w-6xl mx-auto px-6 py-16">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-12">
            {/* Mission */}
            <div>
              <h2 className="text-xl font-semibold text-gray-900 tracking-tight mb-4">
                The Mission
              </h2>
              <p className="text-sm text-gray-500 leading-relaxed mb-4">
                Quality education should not be gated behind price tags. Udemy instructors regularly
                publish their courses at 100% off for limited promotional windows — but those
                windows close within hours. The Udemy Enroller exists to level that playing field.
              </p>
              <p className="text-sm text-gray-500 leading-relaxed mb-4">
                By automating what would take a human hours of daily refreshing, the tool lets
                learners focus on what matters — actually studying the courses they have enrolled
                in, not hunting for the next coupon.
              </p>
              <p className="text-sm text-gray-500 leading-relaxed">
                The project is deliberately kept free, open source, and dependency-light so it can
                be audited, trusted, and run by anyone — from a personal laptop to a low-cost cloud
                server.
              </p>
            </div>

            {/* Creator */}
            <div>
              <h2 className="text-xl font-semibold text-gray-900 tracking-tight mb-4">
                The Creator
              </h2>
              <div className="bg-[#F9FAFB] rounded-xl border border-gray-200 p-6">
                <div className="flex items-center gap-4 mb-5">
                  <div className="w-12 h-12 rounded-full bg-[#2563EB] flex items-center justify-center text-white font-semibold text-lg">
                    M
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-gray-900">Madhu Dadi</p>
                    <a
                      href="https://madhudadi.in"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-[#2563EB] hover:underline"
                    >
                      madhudadi.in →
                    </a>
                  </div>
                </div>
                <p className="text-sm text-gray-500 leading-relaxed mb-4">
                  Madhu is a developer and open-source contributor passionate about automation,
                  developer tooling, and making quality learning resources accessible to everyone.
                </p>
                <p className="text-sm text-gray-500 leading-relaxed">
                  The Udemy Enroller started as a personal script to stop missing time-limited free
                  course coupons, and has since grown into an open-source project used by learners
                  worldwide.
                </p>
                <div className="mt-5 pt-5 border-t border-gray-200 flex items-center gap-3">
                  <a
                    href="https://github.com/madhu2456/udemy_enroller_fastapi"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 text-xs text-gray-600 hover:text-gray-900 transition-colors"
                  >
                    <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M12 0C5.37 0 0 5.37 0 12c0 5.3 3.44 9.8 8.21 11.39.6.11.82-.26.82-.58v-2.03c-3.34.73-4.04-1.61-4.04-1.61-.55-1.39-1.34-1.76-1.34-1.76-1.09-.75.08-.73.08-.73 1.21.08 1.85 1.24 1.85 1.24 1.07 1.84 2.81 1.31 3.5 1 .11-.78.42-1.31.76-1.61-2.67-.3-5.47-1.33-5.47-5.93 0-1.31.47-2.38 1.24-3.22-.12-.3-.54-1.52.12-3.18 0 0 1.01-.32 3.3 1.23a11.5 11.5 0 013-.4c1.02.005 2.04.14 3 .4 2.28-1.55 3.29-1.23 3.29-1.23.66 1.66.24 2.88.12 3.18.77.84 1.24 1.91 1.24 3.22 0 4.61-2.81 5.63-5.49 5.92.43.37.82 1.1.82 2.22v3.29c0 .32.22.7.83.58C20.57 21.8 24 17.3 24 12c0-6.63-5.37-12-12-12z" />
                    </svg>
                    View on GitHub
                  </a>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Values */}
        <section className="border-y border-gray-200 bg-[#F9FAFB]" aria-labelledby="values-heading">
          <div className="max-w-6xl mx-auto px-6 py-16">
            <h2
              id="values-heading"
              className="text-xl font-semibold text-gray-900 tracking-tight mb-8"
            >
              What we stand for
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {values.map((v) => (
                <div key={v.title} className="bg-white rounded-xl border border-gray-200 p-5">
                  <div className="inline-flex items-center justify-center w-8 h-8 rounded-lg bg-[#EFF6FF] border border-blue-100 mb-4">
                    {v.icon}
                  </div>
                  <h3 className="text-sm font-semibold text-gray-900 mb-2">{v.title}</h3>
                  <p className="text-xs text-gray-500 leading-relaxed">{v.description}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* How it's built */}
        <section className="max-w-6xl mx-auto px-6 py-16" aria-labelledby="tech-heading">
          <h2 id="tech-heading" className="text-xl font-semibold text-gray-900 tracking-tight mb-2">
            How it's built
          </h2>
          <p className="text-sm text-gray-500 mb-8">
            A lightweight, auditable stack — nothing you can't read and understand in an afternoon.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {[
              {
                label: 'FastAPI (Python)',
                desc: 'The backend engine that monitors coupon sites and talks to the Udemy API.',
              },
              {
                label: 'Coupon Scrapers',
                desc: 'Modular scrapers for each aggregator site — easy to add new sources via pull request.',
              },
              {
                label: 'Udemy API',
                desc: 'Direct integration using your session token. No third-party middleware, no data leakage.',
              },
            ].map(({ label, desc }) => (
              <div key={label} className="bg-[#F9FAFB] rounded-xl border border-gray-200 p-5">
                <p className="text-sm font-semibold text-gray-900 mb-1 font-mono">{label}</p>
                <p className="text-xs text-gray-500 leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>
        </section>

        {/* CTA */}
        <section className="border-t border-gray-200 bg-[#F9FAFB]">
          <div className="max-w-6xl mx-auto px-6 py-14 text-center">
            <h2 className="text-xl font-semibold text-gray-900 tracking-tight mb-2">
              Ready to start learning for free?
            </h2>
            <p className="text-sm text-gray-500 max-w-md mx-auto mb-6">
              Connect your Udemy account and let the engine do the rest.
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
              <Link
                href="/#connect"
                className="inline-flex items-center gap-2 bg-[#2563EB] text-white rounded-lg px-5 py-2.5 text-sm font-semibold hover:bg-blue-700 transition-colors duration-150"
              >
                Get Started Free
              </Link>
              <Link
                href="/guides"
                className="inline-flex items-center gap-2 bg-white border border-gray-200 text-gray-700 rounded-lg px-5 py-2.5 text-sm font-semibold hover:border-gray-300 hover:bg-gray-50 transition-colors duration-150"
              >
                Read the Guides
              </Link>
            </div>
          </div>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
