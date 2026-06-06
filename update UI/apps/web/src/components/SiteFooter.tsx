import Link from 'next/link';

const GITHUB_URL = 'https://github.com/madhu2456/udemy_enroller_fastapi';

export default function SiteFooter() {
  return (
    <footer className="border-t border-gray-200 bg-white">
      <div className="max-w-6xl mx-auto px-6 py-8">
        <div className="flex flex-col sm:flex-row items-center justify-between gap-6">
          {/* Brand */}
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 rounded-md bg-[#2563EB] flex items-center justify-center">
              <svg
                className="w-3 h-3 text-white"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2.5}
                  d="M13 10V3L4 14h7v7l9-11h-7z"
                />
              </svg>
            </div>
            <span className="text-xs font-semibold text-gray-700">Udemy Enroller</span>
          </div>

          {/* Links */}
          <nav
            className="flex items-center flex-wrap justify-center gap-x-6 gap-y-2"
            aria-label="Footer navigation"
          >
            <Link
              href="/guides"
              className="text-xs text-gray-500 hover:text-gray-700 transition-colors"
            >
              Guides
            </Link>
            <Link
              href="/faq"
              className="text-xs text-gray-500 hover:text-gray-700 transition-colors"
            >
              FAQ
            </Link>
            <Link
              href="/about"
              className="text-xs text-gray-500 hover:text-gray-700 transition-colors"
            >
              About
            </Link>
            <a
              href="https://madhudadi.in"
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-gray-500 hover:text-gray-700 transition-colors"
            >
              Madhu Dadi
            </a>
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-gray-500 hover:text-gray-700 transition-colors"
            >
              GitHub
            </a>
          </nav>

          {/* Disclaimer */}
          <p className="text-xs text-gray-400">Not affiliated with Udemy, Inc.</p>
        </div>
      </div>
    </footer>
  );
}
