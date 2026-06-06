import type { Metadata } from 'next';
import SiteNav from '@/components/SiteNav';
import SiteFooter from '@/components/SiteFooter';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Guides – Udemy Enroller',
  description:
    'Step-by-step guides for setting up the Udemy Enroller — from connecting your account and extracting cookies to configuring smart filters and running on a server.',
  alternates: { canonical: 'https://udemyenroller.madhudadi.in/guides' },
};

type Step = { title: string; body: string; code?: string };

const guides: {
  slug: string;
  tag: string;
  title: string;
  description: string;
  readTime: string;
  steps: Step[];
}[] = [
  {
    slug: 'get-started',
    tag: 'Beginner',
    title: 'Get Started in 5 Minutes',
    description:
      'Connect your Udemy account and claim your first batch of free courses automatically.',
    readTime: '5 min read',
    steps: [
      {
        title: 'Open the Connect section',
        body: 'Scroll to the "Connect Your Account" section on the homepage, or click "Get Started" in the top nav.',
      },
      {
        title: 'Choose Email Login',
        body: 'For the quickest setup, enter your Udemy email and password. If you encounter a CAPTCHA or CSRF error, switch to Cookie Login (see the Cookie Login guide below).',
      },
      {
        title: 'Click Connect Account',
        body: 'The engine will authenticate with the Udemy API and begin monitoring coupon sites immediately. No further action is required.',
      },
      {
        title: 'Wait for the first enrollments',
        body: 'Within minutes, the engine will start finding and applying 100% off coupons. Check your Udemy dashboard to see new courses appearing in "My Learning".',
      },
    ],
  },
  {
    slug: 'cookie-login',
    tag: 'Authentication',
    title: 'How to Use Cookie Login',
    description:
      'The most reliable way to authenticate — bypasses CAPTCHA and works on any server environment.',
    readTime: '4 min read',
    steps: [
      {
        title: 'Log in to Udemy in your browser',
        body: 'Open Chrome or Firefox and sign in to udemy.com with your account.',
      },
      {
        title: 'Open DevTools',
        body: 'Press F12 (or Cmd+Option+I on Mac) to open Browser Developer Tools.',
      },
      {
        title: 'Navigate to the Cookies panel',
        body: 'Click the "Application" tab at the top of DevTools. In the left sidebar, expand "Cookies" and click on "https://www.udemy.com".',
      },
      {
        title: 'Copy the three cookie values',
        body: 'Find and copy the value (not the name) of each of these three cookies:',
        code: 'access_token\nclient_id\ncsrftoken',
      },
      {
        title: 'Paste into the Cookie Login form',
        body: 'Switch to the Cookie Login tab on the Connect form. Paste each value into its corresponding field and click Connect Account.',
      },
      {
        title: 'Refreshing cookies when they expire',
        body: 'Udemy cookies typically last 30–90 days. When you see authentication errors, repeat this process to get fresh cookies.',
      },
    ],
  },
  {
    slug: 'smart-filters',
    tag: 'Configuration',
    title: 'Configuring Smart Filters',
    description:
      'Control exactly which courses get enrolled — by rating, language, and instructor.',
    readTime: '3 min read',
    steps: [
      {
        title: 'Set a minimum course rating',
        body: 'Filter out low-quality courses by setting a minimum star rating. For example, setting 4.0 means only courses rated 4.0 stars or higher will be enrolled.',
      },
      {
        title: 'Choose preferred languages',
        body: 'Specify one or more languages (e.g. English, Hindi) to ensure you only enroll in courses you can understand. The engine will skip courses listed in other languages.',
      },
      {
        title: 'Block specific instructors',
        body: 'Add instructor names to your exclusion list. Any course published by a blocked instructor will be skipped, regardless of rating or language.',
      },
      {
        title: 'Save and apply your filters',
        body: 'Filters are applied in real time. All new coupon checks will honour your updated preferences immediately after saving.',
      },
    ],
  },
  {
    slug: 'run-on-server',
    tag: 'Advanced',
    title: 'Running on a Cloud Server',
    description:
      'Deploy the FastAPI backend on a VPS or cloud VM so the engine runs 24/7 without your computer.',
    readTime: '8 min read',
    steps: [
      {
        title: 'Clone the repository',
        body: 'SSH into your server and clone the project:',
        code: 'git clone https://github.com/madhu2456/udemy_enroller_fastapi.git\ncd udemy_enroller_fastapi',
      },
      {
        title: 'Install dependencies',
        body: 'Create a virtual environment and install the Python requirements:',
        code: 'python3 -m venv venv\nsource venv/bin/activate\npip install -r requirements.txt',
      },
      {
        title: 'Configure your credentials',
        body: 'Copy the example environment file and add your Udemy credentials (or cookies) and any filter preferences:',
        code: 'cp .env.example .env\nnano .env',
      },
      {
        title: 'Start the FastAPI server',
        body: 'Run the application with uvicorn:',
        code: 'uvicorn main:app --host 0.0.0.0 --port 8000',
      },
      {
        title: 'Keep it running with systemd or screen',
        body: 'To keep the process alive after you disconnect, use screen, tmux, or a systemd service file. See the GitHub README for a sample systemd config.',
      },
    ],
  },
  {
    slug: 'troubleshooting',
    tag: 'Troubleshooting',
    title: 'Common Issues & Fixes',
    description:
      'Solutions to the most common problems: CSRF errors, expired cookies, and enrollment failures.',
    readTime: '5 min read',
    steps: [
      {
        title: 'CSRF error with Email Login',
        body: "This happens when Udemy's anti-bot system flags the login from a server IP. Fix: switch to Cookie Login, which uses a token already issued by Udemy to your real browser session.",
      },
      {
        title: 'Cookies stopped working',
        body: 'Udemy session cookies expire after 30–90 days. Fix: log in to udemy.com again in your browser, re-extract the three cookie values (access_token, client_id, csrftoken), and update them in the form.',
      },
      {
        title: 'No courses being enrolled',
        body: 'Check that your smart filters are not too restrictive. If your minimum rating is set very high or your language filter only includes rare languages, there may be few matching courses on any given day. Try relaxing the filters temporarily.',
      },
      {
        title: 'Enrollment fails for specific courses',
        body: 'Some coupons expire between the moment the engine detects them and the time the API call completes. This is normal — the engine will continue checking and enrolling other valid coupons.',
      },
      {
        title: 'The engine is not starting',
        body: 'If running locally, ensure all dependencies are installed and your .env file contains valid credentials. If running on a server, check the process logs for Python errors and make sure the virtual environment is activated.',
      },
    ],
  },
];

const tagColors: Record<string, string> = {
  Beginner: 'bg-green-50 text-green-700 border-green-200',
  Authentication: 'bg-blue-50 text-blue-700 border-blue-200',
  Configuration: 'bg-purple-50 text-purple-700 border-purple-200',
  Advanced: 'bg-orange-50 text-orange-700 border-orange-200',
  Troubleshooting: 'bg-red-50 text-red-700 border-red-200',
};

export default function GuidesPage() {
  return (
    <div
      style={{ fontFamily: "'Inter', -apple-system, sans-serif" }}
      className="min-h-screen bg-white text-gray-900"
    >
      <SiteNav />

      <main>
        {/* Hero */}
        <section
          className="max-w-6xl mx-auto px-6 pt-14 pb-10"
          aria-labelledby="guides-hero-heading"
        >
          <div className="max-w-2xl">
            <span className="inline-flex items-center gap-1.5 bg-[#EFF6FF] text-[#2563EB] rounded-full px-3 py-1 text-xs font-medium mb-4">
              Documentation
            </span>
            <h1
              id="guides-hero-heading"
              className="text-3xl font-semibold text-gray-900 tracking-tight mb-3"
            >
              Guides & Walkthroughs
            </h1>
            <p className="text-sm text-gray-500 leading-relaxed">
              Step-by-step instructions for every part of the Udemy Enroller — from connecting your
              account in 5 minutes to deploying on a 24/7 cloud server.
            </p>
          </div>
        </section>

        {/* Guides list */}
        <section className="max-w-6xl mx-auto px-6 pb-20">
          <div className="space-y-16">
            {guides.map((guide, idx) => (
              <article key={guide.slug} id={guide.slug} aria-labelledby={`guide-${guide.slug}`}>
                {/* Guide header */}
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-6">
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-gray-400 font-mono">
                      {String(idx + 1).padStart(2, '0')}
                    </span>
                    <span
                      className={`inline-flex items-center text-[10px] font-semibold px-2 py-0.5 rounded-full border ${tagColors[guide.tag] ?? 'bg-gray-50 text-gray-600 border-gray-200'}`}
                    >
                      {guide.tag}
                    </span>
                  </div>
                  <span className="text-xs text-gray-400">{guide.readTime}</span>
                </div>

                <h2
                  id={`guide-${guide.slug}`}
                  className="text-xl font-semibold text-gray-900 tracking-tight mb-1"
                >
                  {guide.title}
                </h2>
                <p className="text-sm text-gray-500 mb-6">{guide.description}</p>

                {/* Steps */}
                <ol className="space-y-0">
                  {guide.steps.map((step, sIdx) => (
                    <li key={sIdx} className="flex gap-5 pb-6 relative">
                      {/* Connector line */}
                      {sIdx < guide.steps.length - 1 && (
                        <div className="absolute left-[13px] top-7 bottom-0 w-px bg-gray-200" />
                      )}
                      {/* Step number */}
                      <div className="relative z-10 flex-shrink-0 w-7 h-7 rounded-full border border-gray-200 bg-white flex items-center justify-center text-xs font-semibold text-gray-500">
                        {sIdx + 1}
                      </div>
                      <div className="flex-1 pt-0.5">
                        <p className="text-sm font-semibold text-gray-900 mb-1">{step.title}</p>
                        <p className="text-sm text-gray-500 leading-relaxed mb-2">{step.body}</p>
                        {step.code && (
                          <pre className="bg-gray-950 text-gray-100 rounded-lg px-4 py-3 text-xs font-mono overflow-x-auto leading-relaxed">
                            {step.code}
                          </pre>
                        )}
                      </div>
                    </li>
                  ))}
                </ol>

                {/* Divider between guides */}
                {idx < guides.length - 1 && <div className="border-b border-gray-200 mt-2" />}
              </article>
            ))}
          </div>

          {/* Still need help */}
          <div className="mt-14 bg-[#F9FAFB] rounded-xl border border-gray-200 p-8 text-center">
            <p className="text-sm font-semibold text-gray-900 mb-1">Still stuck?</p>
            <p className="text-sm text-gray-500 mb-5">
              Open an issue on GitHub or check the FAQ for quick answers.
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
                href="/faq"
                className="inline-flex items-center gap-2 bg-[#2563EB] text-white rounded-lg px-4 py-2 text-xs font-semibold hover:bg-blue-700 transition-colors duration-150"
              >
                Browse FAQ →
              </Link>
            </div>
          </div>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
