import LoginForm from '@/components/LoginForm';
import SiteNav from '@/components/SiteNav';
import SiteFooter from '@/components/SiteFooter';

// ── Feature card ──────────────────────────────────────────────────────────────
function FeatureCard({
  icon,
  title,
  description,
  items,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  items: string[];
}) {
  return (
    <article className="bg-white rounded-xl border border-gray-200 p-6 hover:border-gray-300 transition-colors duration-150">
      <div className="mb-4">{icon}</div>
      <h3 className="text-base font-semibold text-gray-900 mb-1">{title}</h3>
      <p className="text-sm text-gray-500 mb-4 leading-relaxed">{description}</p>
      <ul className="space-y-1.5">
        {items.map((item) => (
          <li key={item} className="flex items-start text-sm text-gray-600">
            <span className="text-gray-400 mr-2 mt-px select-none">–</span>
            {item}
          </li>
        ))}
      </ul>
    </article>
  );
}

// ── Step card ─────────────────────────────────────────────────────────────────
function StepCard({ num, title, body }: { num: number; title: string; body: string }) {
  return (
    <div className="flex gap-4">
      <div className="flex-shrink-0 w-8 h-8 rounded-full border border-gray-200 bg-white flex items-center justify-center text-sm font-semibold text-gray-900">
        {num}
      </div>
      <div>
        <p className="text-sm font-semibold text-gray-900 mb-1">{title}</p>
        <p className="text-sm text-gray-500 leading-relaxed">{body}</p>
      </div>
    </div>
  );
}

// ── FAQ item ──────────────────────────────────────────────────────────────────
function FaqItem({ q, a }: { q: string; a: string }) {
  return (
    <div className="border-b border-gray-200 py-5 last:border-0">
      <h3 className="text-sm font-semibold text-gray-900 mb-2">{q}</h3>
      <p className="text-sm text-gray-500 leading-relaxed">{a}</p>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function Page() {
  const features = [
    {
      icon: (
        <div className="inline-flex items-center justify-center w-9 h-9 rounded-lg bg-[#EFF6FF] border border-blue-100">
          <svg
            className="w-4 h-4 text-[#2563EB]"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M13 10V3L4 14h7v7l9-11h-7z"
            />
          </svg>
        </div>
      ),
      title: 'Fully Automated Engine',
      description:
        'Set your filters once and let the engine do the rest. No manual monitoring, no copy-pasting coupon codes.',
      items: [
        'Monitors coupon aggregator sites',
        'Applies valid coupons instantly',
        'Runs continuously in the background',
      ],
    },
    {
      icon: (
        <div className="inline-flex items-center justify-center w-9 h-9 rounded-lg bg-[#EFF6FF] border border-blue-100">
          <svg
            className="w-4 h-4 text-[#2563EB]"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
            />
          </svg>
        </div>
      ),
      title: '100% Secure Authentication',
      description:
        'Your credentials are used only to generate a temporary API token. No data is ever stored on external servers.',
      items: [
        'Direct Udemy API integration',
        'Token-only, no credential storage',
        'Cookie-based login as alternative',
      ],
    },
    {
      icon: (
        <div className="inline-flex items-center justify-center w-9 h-9 rounded-lg bg-[#EFF6FF] border border-blue-100">
          <svg
            className="w-4 h-4 text-[#2563EB]"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2a1 1 0 01-.293.707L13 13.414V19a1 1 0 01-.553.894l-4 2A1 1 0 017 21v-7.586L3.293 6.707A1 1 0 013 6V4z"
            />
          </svg>
        </div>
      ),
      title: 'Smart Course Filters',
      description:
        'Target exactly the courses you want to learn. Skip low-quality or irrelevant content automatically.',
      items: [
        'Filter by minimum course rating',
        'Select preferred language',
        'Block specific instructors',
      ],
    },
    {
      icon: (
        <div className="inline-flex items-center justify-center w-9 h-9 rounded-lg bg-[#EFF6FF] border border-blue-100">
          <svg
            className="w-4 h-4 text-[#2563EB]"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
            />
          </svg>
        </div>
      ),
      title: 'Track Your Savings',
      description:
        'Watch your lifetime educational savings grow as the engine silently works in the background.',
      items: ['Live enrollment counter', 'Cumulative savings in USD', 'Course history log'],
    },
  ];

  const faqs = [
    {
      q: 'How does the automated Udemy course enroller work?',
      a: 'The tool monitors popular coupon aggregator websites in real time. When a valid 100% off Udemy coupon is detected, it automatically applies it to your account and enrolls you in the course — no manual steps required.',
    },
    {
      q: 'Is it safe to connect my Udemy account?',
      a: "Yes. The tool integrates directly with Udemy's API and only uses your credentials to generate a temporary authentication token. Your email and password are never stored on any server. Cookie Login is available as an alternative if you prefer not to share your password.",
    },
    {
      q: 'What is the difference between Email Login and Cookie Login?',
      a: 'Email Login uses your Udemy email and password to authenticate, but may trigger a CAPTCHA on server environments. Cookie Login uses three session cookies extracted from your browser (access_token, client_id, csrftoken), which bypasses CAPTCHA and is generally more reliable.',
    },
    {
      q: 'How do I get free Udemy courses with 100% off coupons?',
      a: 'Connect your Udemy account using Email or Cookie Login, configure your smart filters (minimum rating, language, excluded instructors), and start the engine. It will automatically find and apply 100% off coupons to enroll you in free courses.',
    },
    {
      q: 'Is the Udemy Enroller free and open source?',
      a: 'Yes. The Udemy Enroller is completely free and open source. The full source code is available on GitHub. Starring the repository helps support development and ensures you get new scraper updates.',
    },
    {
      q: 'Can I filter which Udemy courses are enrolled automatically?',
      a: 'Absolutely. The smart filter system lets you set a minimum course rating, preferred language, and a blocklist of instructors to skip. Only courses matching your criteria will be enrolled.',
    },
  ];

  const githubUrl = 'https://github.com/madhu2456/udemy_enroller_fastapi';

  const engineSteps = [
    {
      step: '01',
      title: 'Monitor coupon sites',
      desc: 'Continuously polls coupon aggregator sites for new 100% off Udemy listings.',
    },
    {
      step: '02',
      title: 'Validate the coupon',
      desc: 'Checks that the coupon is still active before attempting enrollment.',
    },
    {
      step: '03',
      title: 'Apply your filters',
      desc: "Skips courses that don't match your rating, language, or instructor preferences.",
    },
    {
      step: '04',
      title: 'Enroll via Udemy API',
      desc: 'Uses your session token to apply the coupon and enroll you directly.',
    },
  ];

  return (
    <div
      style={{ fontFamily: "'Inter', -apple-system, sans-serif" }}
      className="min-h-screen bg-white text-gray-900"
    >
      <SiteNav />

      <main>
        {/* ── HERO ──────────────────────────────────────────────────────────── */}
        <section
          className="max-w-6xl mx-auto px-6 pt-16 pb-14 text-center"
          aria-labelledby="hero-heading"
        >
          <div className="animate-fade-in-up">
            <span className="inline-flex items-center gap-1.5 bg-[#EFF6FF] text-[#2563EB] rounded-full px-3 py-1.5 text-xs font-medium mb-6">
              <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                <path
                  fillRule="evenodd"
                  d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z"
                  clipRule="evenodd"
                />
              </svg>
              Open-Source Automation Tool
            </span>
          </div>

          <h1
            id="hero-heading"
            className="animate-fade-in-up delay-100 text-4xl md:text-5xl font-semibold text-gray-900 tracking-tight max-w-3xl mx-auto leading-tight mb-5"
          >
            Claim Free Udemy Courses — <span className="text-[#2563EB]">Automatically</span>
          </h1>

          <p className="animate-fade-in-up delay-200 text-base text-gray-500 max-w-xl mx-auto leading-relaxed mb-8">
            Stop hunting for expired coupons. Our engine monitors coupon aggregator sites and
            enrolls you in{' '}
            <strong className="font-semibold text-gray-700">100% off Udemy courses</strong> the
            moment they appear.
          </p>

          <div className="animate-fade-in-up delay-300 flex flex-col sm:flex-row items-center justify-center gap-3 mb-10">
            <a
              href="#connect"
              className="inline-flex items-center gap-2 bg-[#2563EB] text-white rounded-lg px-5 py-2.5 text-sm font-semibold hover:bg-blue-700 transition-colors duration-150"
            >
              Start Automating Free
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M17 8l4 4m0 0l-4 4m4-4H3"
                />
              </svg>
            </a>
            <a
              href={githubUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 bg-white border border-gray-200 text-gray-700 rounded-lg px-5 py-2.5 text-sm font-semibold hover:border-gray-300 hover:bg-[#F9FAFB] transition-colors duration-150"
            >
              View Source Code
            </a>
          </div>

          <div className="inline-flex flex-wrap items-center justify-center gap-2">
            {[
              { dot: 'bg-green-500', text: 'Free & open source' },
              { dot: 'bg-blue-500', text: '100% off coupons only' },
              { dot: 'bg-orange-500', text: 'No credentials stored' },
            ].map(({ dot, text }) => (
              <span
                key={text}
                className="inline-flex items-center gap-1.5 bg-white border border-gray-200 rounded-full px-3 py-1 text-xs text-gray-700"
              >
                <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />
                {text}
              </span>
            ))}
          </div>
        </section>

        {/* ── FACTS BAR — verifiable only ───────────────────────────────────── */}
        <section className="border-y border-gray-200 bg-[#F9FAFB] py-4" aria-label="Platform facts">
          <div className="max-w-6xl mx-auto px-6">
            <div className="flex flex-wrap items-center justify-center gap-8 md:gap-16">
              {[
                { value: '100% Off', label: 'Udemy coupon rate targeted' },
                { value: 'Multiple', label: 'Coupon sources monitored' },
                { value: 'Open Source', label: 'Auditable on GitHub' },
                { value: '₹0', label: 'Cost to use' },
              ].map(({ value, label }) => (
                <div key={label} className="text-center">
                  <p className="text-lg font-semibold text-gray-900 tracking-tight">{value}</p>
                  <p className="text-xs text-gray-500 mt-0.5">{label}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── FEATURES ──────────────────────────────────────────────────────── */}
        <section className="max-w-6xl mx-auto px-6 py-16" aria-labelledby="features-heading">
          <div className="mb-10">
            <h2
              id="features-heading"
              className="text-2xl font-semibold text-gray-900 tracking-tight mb-2"
            >
              Everything you need to learn for free
            </h2>
            <p className="text-sm text-gray-500">
              A complete pipeline from coupon discovery to automatic Udemy enrollment.
            </p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {features.map((f) => (
              <FeatureCard key={f.title} {...f} />
            ))}
          </div>
        </section>

        {/* ── HOW IT WORKS ──────────────────────────────────────────────────── */}
        <section
          className="border-y border-gray-200 bg-[#F9FAFB]"
          aria-labelledby="how-it-works-heading"
        >
          <div className="max-w-6xl mx-auto px-6 py-16">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
              <div>
                <h2
                  id="how-it-works-heading"
                  className="text-2xl font-semibold text-gray-900 tracking-tight mb-2"
                >
                  Up and running in under 2 minutes
                </h2>
                <p className="text-sm text-gray-500 mb-8 leading-relaxed">
                  Connect once. The engine handles everything else — coupon discovery, validation,
                  and enrollment.
                </p>
                <ol className="space-y-6">
                  <StepCard
                    num={1}
                    title="Connect Your Udemy Account"
                    body="Authenticate via Email Login or Cookie Login. Your credentials are used only to generate a temporary API token."
                  />
                  <StepCard
                    num={2}
                    title="Configure Smart Filters"
                    body="Set your minimum course rating, preferred language, and any instructors you want to exclude."
                  />
                  <StepCard
                    num={3}
                    title="Activate the Engine"
                    body="The engine monitors coupon aggregator sites and enrolls you in matching free courses instantly."
                  />
                  <StepCard
                    num={4}
                    title="Track Your Savings"
                    body="Watch your cumulative educational savings grow as courses are claimed automatically."
                  />
                </ol>
              </div>

              {/* Factual pipeline — no made-up metrics */}
              <div className="bg-white rounded-xl border border-gray-200 p-8">
                <p className="text-sm font-semibold text-gray-900 mb-1">What the engine does</p>
                <p className="text-xs text-gray-500 mb-6">
                  A straightforward pipeline — no magic, just automation.
                </p>
                <div className="space-y-0">
                  {engineSteps.map(({ step, title, desc }, i) => (
                    <div
                      key={step}
                      className={`flex gap-4 py-4 ${i < engineSteps.length - 1 ? 'border-b border-gray-100' : ''}`}
                    >
                      <span className="flex-shrink-0 text-xs font-mono font-semibold text-gray-300 mt-0.5 w-5">
                        {step}
                      </span>
                      <div>
                        <p className="text-xs font-semibold text-gray-900 mb-0.5">{title}</p>
                        <p className="text-xs text-gray-500 leading-relaxed">{desc}</p>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="mt-5 pt-5 border-t border-gray-200 flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-green-500" />
                  <span className="text-xs text-gray-500">
                    Engine runs continuously once connected
                  </span>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ── CONNECT ACCOUNT ───────────────────────────────────────────────── */}
        <section
          id="connect"
          className="max-w-6xl mx-auto px-6 py-16"
          aria-labelledby="connect-heading"
        >
          <div className="max-w-md mx-auto">
            <div className="mb-8 text-center">
              <h2
                id="connect-heading"
                className="text-2xl font-semibold text-gray-900 tracking-tight mb-2"
              >
                Connect Your Account
              </h2>
              <p className="text-sm text-gray-500">
                Choose your preferred authentication method below to start claiming free courses.
              </p>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <LoginForm />
            </div>
            <p className="mt-4 text-center text-xs text-gray-400">
              By connecting, you agree that your credentials are used solely to interact with the
              Udemy API on your behalf.{' '}
              <a
                href={githubUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 hover:underline"
              >
                Review the source code.
              </a>
            </p>
          </div>
        </section>

        {/* ── FAQ ───────────────────────────────────────────────────────────── */}
        <section className="border-t border-gray-200 bg-[#F9FAFB]" aria-labelledby="faq-heading">
          <div className="max-w-6xl mx-auto px-6 py-16">
            <div className="max-w-2xl mx-auto">
              <div className="mb-8">
                <h2
                  id="faq-heading"
                  className="text-2xl font-semibold text-gray-900 tracking-tight mb-2"
                >
                  Frequently Asked Questions
                </h2>
                <p className="text-sm text-gray-500">
                  Everything you need to know about the Udemy Enroller tool.
                </p>
              </div>
              <div className="bg-white rounded-xl border border-gray-200 px-6">
                {faqs.map((faq) => (
                  <FaqItem key={faq.q} q={faq.q} a={faq.a} />
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* ── OPEN SOURCE CTA ───────────────────────────────────────────────── */}
        <section className="border-t border-gray-200 bg-white" aria-labelledby="oss-heading">
          <div className="max-w-6xl mx-auto px-6 py-16 text-center">
            <h2
              id="oss-heading"
              className="text-xl font-semibold text-gray-900 tracking-tight mb-2"
            >
              Open Source & Community Driven
            </h2>
            <p className="text-sm text-gray-500 max-w-lg mx-auto mb-6 leading-relaxed">
              New coupon scrapers are added regularly. Star the GitHub repository to stay updated
              and help the project grow.
            </p>
            <a
              href={githubUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 bg-[#EFF6FF] text-[#2563EB] rounded-full px-5 py-2.5 text-sm font-semibold hover:bg-blue-100 transition-colors duration-150"
            >
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 0C5.37 0 0 5.37 0 12c0 5.3 3.44 9.8 8.21 11.39.6.11.82-.26.82-.58v-2.03c-3.34.73-4.04-1.61-4.04-1.61-.55-1.39-1.34-1.76-1.34-1.76-1.09-.75.08-.73.08-.73 1.21.08 1.85 1.24 1.85 1.24 1.07 1.84 2.81 1.31 3.5 1 .11-.78.42-1.31.76-1.61-2.67-.3-5.47-1.33-5.47-5.93 0-1.31.47-2.38 1.24-3.22-.12-.3-.54-1.52.12-3.18 0 0 1.01-.32 3.3 1.23a11.5 11.5 0 013-.4c1.02.005 2.04.14 3 .4 2.28-1.55 3.29-1.23 3.29-1.23.66 1.66.24 2.88.12 3.18.77.84 1.24 1.91 1.24 3.22 0 4.61-2.81 5.63-5.49 5.92.43.37.82 1.1.82 2.22v3.29c0 .32.22.7.83.58C20.57 21.8 24 17.3 24 12c0-6.63-5.37-12-12-12z" />
              </svg>
              Star on GitHub
            </a>
          </div>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
