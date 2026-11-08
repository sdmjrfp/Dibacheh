import js from "@eslint/js";
import globals from "globals";

export default [
  js.configs.recommended,
  {
    files: ["static/js/**/*.js"],
    languageOptions: {
      sourceType: "module",
      globals: { ...globals.browser, Jalali: "readonly" },
    },
    rules: { "no-unused-vars": ["error", { caughtErrors: "none" }] },
  },
];
