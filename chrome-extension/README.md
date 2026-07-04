# Udemy Enroller - Chrome Extension

A simple Chrome extension to extract Udemy session cookies for use with the [Udemy Enroller](https://udemyenroller.madhudadi.in) web application.

## Features

- ✅ One-click cookie extraction
- ✅ Copy to clipboard
- ✅ Live coupon count display
- ✅ Secure - no data exfiltration

## Installation

### From Source (Developer Mode)

1. Clone or download this repository
2. Open Chrome and go to `chrome://extensions/`
3. Enable "Developer mode" (top right)
4. Click "Load unpacked"
5. Select the `chrome-extension` folder

### From Chrome Web Store

*Coming soon*

## Usage

1. Log into [udemy.com](https://www.udemy.com) in your browser
2. Click the extension icon in your toolbar
3. Click "Copy Cookies"
4. Paste into the Udemy Enroller web app

## Permissions

- `cookies` - Access Udemy session cookies
- `host_permissions: https://*.udemy.com/*` - Limited to Udemy only

## Security

- **No data exfiltration** - Cookies are only copied to your clipboard
- **No remote code** - All code is bundled with the extension
- **Minimal permissions** - Only accesses Udemy cookies

## Privacy

This extension does not collect, store, or transmit any data. Cookie extraction happens entirely in your browser.

## License

MIT License - See [LICENSE](../LICENSE) for details.

## Contributing

Contributions welcome! Please open an issue or PR on [GitHub](https://github.com/madhu2456/udemy_enroller_fastapi).
