/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/templates/components/base.html",
    "./app/templates/pages/login.html",
  ],
  safelist: [
    "text-blue-400",
    "text-green-400",
    "text-red-400",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};
