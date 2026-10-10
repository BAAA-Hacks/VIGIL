import parser from "@babel/eslint-parser";
import reactHooks from "eslint-plugin-react-hooks";
export default [
  {
    files: ["src/**/*.ts", "src/**/*.tsx"],
    languageOptions: {
      parser,
      parserOptions: {
        requireConfigFile: false,
        babelOptions: {
          parserOpts: { plugins: ["jsx"] },
          plugins: [["@babel/plugin-syntax-typescript", { isTSX: true }]],
        },
      },
    },
    plugins: { "react-hooks": reactHooks },
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
    },
  },
];
