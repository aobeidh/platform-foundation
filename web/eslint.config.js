import js from '@eslint/js';
import globals from 'globals';
import reactHooks from 'eslint-plugin-react-hooks';
import tseslint from 'typescript-eslint';

// Atomic layers, enforced (F3 for the web): a layer imports only from layers below it.
const g = (name, ...extra) => ({ group: [`@/${name}/*`, `@/${name}`, `../${name}/*`, `../../${name}/*`, ...extra], message: `This layer may not import ${name}.` });
const atoms = g('ui/atoms'); const molecules = g('ui/molecules'); const organisms = g('ui/organisms');
const charts = g('ui/charts'); const viz = g('ui/viz'); const templates = g('ui/templates');
const kit = g('kit'); const pages = g('pages'); const data = g('data'); const app = g('app'); const ui = g('ui');
const restrict = (groups, { echarts = false } = {}) => ['error', { patterns: [...groups,
  ...(echarts ? [] : [{ group: ['echarts', 'echarts/*'], message: 'Only src/ui/charts may import echarts.' }]),
  { group: ['recharts', 'chart.js', '@nivo/*', 'victory', 'highcharts', 'plotly.js'], message: 'ECharts is the only chart library.' }] }];

export default tseslint.config(
  { ignores: ['dist', 'dist-single', 'public', 'scripts', 'node_modules'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: { ecmaVersion: 2022, globals: globals.browser },
    plugins: { 'react-hooks': reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_', destructuredArrayIgnorePattern: '^_' }],
      'no-restricted-imports': restrict([]),
    },
  },
  { files: ['src/lib/**'], rules: { 'no-restricted-imports': restrict([ui, kit, pages, data, app]) } },
  { files: ['src/ui/atoms/**'], rules: { 'no-restricted-imports': restrict([molecules, organisms, charts, viz, templates, kit, pages, data, app]) } },
  { files: ['src/ui/molecules/**'], rules: { 'no-restricted-imports': restrict([organisms, { group: ['@/ui/charts/*', '!@/ui/charts/sparkline'], message: 'Molecules may use charts only through sparkline.' }, viz, templates, kit, pages, data, app]) } },
  { files: ['src/ui/organisms/**', 'src/ui/viz/**'], rules: { 'no-restricted-imports': restrict([templates, kit, pages, data, app]) } },
  { files: ['src/ui/charts/**'], rules: { 'no-restricted-imports': restrict([organisms, templates, kit, pages, data, app], { echarts: true }) } },
  { files: ['src/ui/templates/**'], rules: { 'no-restricted-imports': restrict([kit, pages, data, app]) } },
  { files: ['src/kit/**'], rules: { 'no-restricted-imports': restrict([templates, pages, data, app]) } },
  { files: ['src/i18n/**'], rules: { 'no-restricted-imports': restrict([ui, kit, pages, data, app]) } },
  // Tests may load fixtures from any layer.
  { files: ['src/**/*.test.ts', 'src/**/*.test.tsx'], rules: { 'no-restricted-imports': restrict([]) } },
);
