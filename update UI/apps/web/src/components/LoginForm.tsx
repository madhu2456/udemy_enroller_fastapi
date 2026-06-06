'use client';

import { useState } from 'react';

export default function LoginForm() {
  const [activeTab, setActiveTab] = useState<'email' | 'cookie'>('email');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [accessToken, setAccessToken] = useState('');
  const [clientId, setClientId] = useState('');
  const [csrfToken, setCsrfToken] = useState('');
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await new Promise((r) => setTimeout(r, 1200));
      setSuccess(true);
    } catch {
      setError('Connection failed. Please check your credentials and try again.');
    } finally {
      setLoading(false);
    }
  };

  const inputClass =
    'w-full px-3 py-2.5 text-sm text-gray-900 bg-white border border-gray-200 rounded-lg placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-1 focus:border-transparent transition-all duration-150';
  const labelClass = 'block text-xs font-medium text-gray-500 mb-1.5';

  if (success) {
    return (
      <div className="text-center py-8">
        <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-green-50 border border-green-200 mb-4">
          <svg
            className="w-5 h-5 text-green-600"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <p className="text-sm font-semibold text-gray-900 mb-1">Account Connected</p>
        <p className="text-xs text-gray-500">
          The enroller is now running and will claim free courses automatically.
        </p>
        <button
          onClick={() => {
            setSuccess(false);
            setEmail('');
            setPassword('');
            setAccessToken('');
            setClientId('');
            setCsrfToken('');
          }}
          className="mt-5 text-xs text-blue-600 font-medium hover:text-blue-700 transition-colors"
        >
          Connect another account
        </button>
      </div>
    );
  }

  return (
    <div>
      <style jsx global>{`
        @keyframes spin {
          from {
            transform: rotate(0deg);
          }
          to {
            transform: rotate(360deg);
          }
        }
        .lf-spinner {
          animation: spin 0.8s linear infinite;
        }
      `}</style>
      {/* Tab Navigation */}
      <div className="flex border-b border-gray-200 mb-6">
        {(['email', 'cookie'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => {
              setActiveTab(tab);
              setError(null);
            }}
            className={[
              'pb-3 text-sm font-medium mr-6 border-b-2 -mb-[1px] transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2',
              activeTab === tab
                ? 'text-gray-900 border-blue-600'
                : 'text-gray-500 border-transparent hover:text-gray-700',
            ].join(' ')}
          >
            {tab === 'email' ? 'Email Login' : 'Cookie Login'}
          </button>
        ))}
      </div>

      {activeTab === 'email' && (
        <div className="mb-5 px-4 py-3 bg-[#F9FAFB] border border-gray-200 rounded-lg">
          <p className="text-xs text-gray-500 leading-relaxed">
            Email login may trigger a CAPTCHA on some servers. If you see a CSRF error, switch to{' '}
            <button
              onClick={() => setActiveTab('cookie')}
              className="text-blue-600 font-medium hover:underline"
            >
              Cookie Login
            </button>
            .
          </p>
        </div>
      )}

      {activeTab === 'cookie' && (
        <div className="mb-5 px-4 py-3 bg-[#F9FAFB] border border-gray-200 rounded-lg">
          <p className="text-xs font-medium text-gray-700 mb-2">How to get your cookies:</p>
          <ol className="space-y-1">
            {[
              <>
                Log in to{' '}
                <a
                  href="https://www.udemy.com"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-600 hover:underline"
                >
                  udemy.com
                </a>
              </>,
              <>
                Press{' '}
                <kbd className="px-1.5 py-0.5 text-[10px] font-mono bg-white border border-gray-200 rounded text-gray-700">
                  F12
                </kbd>{' '}
                → <strong className="font-medium text-gray-700">Application</strong> →{' '}
                <strong className="font-medium text-gray-700">Cookies</strong>
              </>,
              'Copy the three values listed below',
            ].map((step, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="flex-shrink-0 w-4 h-4 rounded-full bg-gray-200 text-gray-600 text-[10px] font-semibold flex items-center justify-center mt-0.5">
                  {i + 1}
                </span>
                <span className="text-xs text-gray-500">{step}</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        {activeTab === 'email' ? (
          <>
            <div>
              <label className={labelClass} htmlFor="email">
                Email Address
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                required
                autoComplete="email"
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass} htmlFor="password">
                Password
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Your Udemy password"
                required
                autoComplete="current-password"
                className={inputClass}
              />
            </div>
          </>
        ) : (
          <>
            <div>
              <label className={labelClass} htmlFor="access_token">
                access_token
              </label>
              <input
                id="access_token"
                type="text"
                value={accessToken}
                onChange={(e) => setAccessToken(e.target.value)}
                placeholder="Paste your access_token cookie"
                required
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass} htmlFor="client_id">
                client_id
              </label>
              <input
                id="client_id"
                type="text"
                value={clientId}
                onChange={(e) => setClientId(e.target.value)}
                placeholder="Paste your client_id cookie"
                required
                className={inputClass}
              />
            </div>
            <div>
              <label className={labelClass} htmlFor="csrftoken">
                csrftoken
              </label>
              <input
                id="csrftoken"
                type="text"
                value={csrfToken}
                onChange={(e) => setCsrfToken(e.target.value)}
                placeholder="Paste your csrftoken cookie"
                required
                className={inputClass}
              />
            </div>
          </>
        )}

        {error && (
          <div className="px-3 py-2.5 bg-red-50 border border-red-200 rounded-lg">
            <p className="text-xs text-red-600">{error}</p>
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full py-2.5 px-4 bg-[#2563EB] text-white text-sm font-semibold rounded-lg hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2"
        >
          {loading ? (
            <span className="flex items-center justify-center gap-2">
              <svg className="lf-spinner w-4 h-4" fill="none" viewBox="0 0 24 24">
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                />
              </svg>
              Connecting…
            </span>
          ) : (
            'Connect Account'
          )}
        </button>
      </form>
    </div>
  );
}
