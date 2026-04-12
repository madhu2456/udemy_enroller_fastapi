/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/templates/**/*.html",
    "./app/static/js/**/*.js",
  ],
  safelist: [
    "text-blue-400",
    "text-green-400",
    "text-red-400",
    "bg-green-900",
    "text-green-300",
    "bg-red-900",
    "text-red-300",
    "bg-yellow-900",
    "text-yellow-300",
    "bg-cyan-900",
    "text-cyan-300",
    "bg-gray-600",
    "text-gray-300",
    "bg-blue-900",
    "text-blue-300",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};
