module.exports = {
  root: true,
  env: {
    browser: true,
    es2022: true,
    node: true
  },
  parser: "vue-eslint-parser",
  parserOptions: {
    parser: "@typescript-eslint/parser",
    ecmaVersion: "latest",
    sourceType: "module",
    extraFileExtensions: [".vue"]
  },
  extends: ["eslint:recommended", "plugin:vue/vue3-essential", "plugin:@typescript-eslint/recommended"],
  plugins: ["vue", "@typescript-eslint"],
  ignorePatterns: ["dist/", "node_modules/", "coverage/"],
  rules: {
    "no-console": "off",
    "no-debugger": "warn",
    "no-undef": "off",
    "no-constant-condition": [
      "error",
      {
        checkLoops: false
      }
    ],
    "vue/multi-word-component-names": "off",
    "vue/no-v-html": "off",
    "@typescript-eslint/no-explicit-any": "off",
    "@typescript-eslint/no-unused-vars": "off"
  }
};
