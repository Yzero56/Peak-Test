/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,jsx,ts,tsx}'],
  presets: [require('nativewind/preset')],
  theme: {
    extend: {
      colors: {
        // 냉장고 대시보드 v2 디자인의 Fresh 테마(그린 포인트) 팔레트
        accent: {
          100: '#eef3f2',
          200: '#dae7e4',
          300: '#b9cecb',
          400: '#93b3ae',
          500: '#749a94',
          600: '#5c8a82',
          700: '#4a6f69',
          800: '#3a5651',
          900: '#283b38',
        },
        canvas: '#fbfcfb',
        surface: '#f4f6f5',
        divider: '#e8ebe9',
      },
    },
  },
  plugins: [],
};
