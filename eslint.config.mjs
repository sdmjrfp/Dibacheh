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
    rules: {
      "no-unused-vars": ["error", { caughtErrors: "none" }],
      // هیچ متغیری نباید نام تابع ترجمه را بپوشاند
      "no-shadow": ["error", { allow: ["root", "fields", "label"] }],
    },
  },
];
