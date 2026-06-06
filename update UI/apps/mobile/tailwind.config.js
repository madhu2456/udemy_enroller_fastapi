import config from '@anythingai/app/tailwind.config';

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./node_modules/@anythingai/app/**/*.{js,ts,jsx,tsx}'],
  ...config,
};
