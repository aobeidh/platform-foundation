// Generates registry.json from the source tree, so @platform/web-kit installs with the shadcn CLI:
//   npx shadcn add @platform/kpi-tile
// One item per component file; files that only work together ship as one item. Every file keeps its source path
// as its target, so @/ui/... imports stay valid in the consumer. Local imports become registry dependencies,
// packages become npm dependencies pinned to this project's versions.
import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const pkg = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
const versions = { ...pkg.dependencies, ...pkg.devDependencies };
const rel = (p) => path.relative(root, p).split(path.sep).join('/');
const read = (f) => fs.readFileSync(path.join(root, f), 'utf8');
const list = (dir) => fs.readdirSync(path.join(root, dir)).filter((f) => /\.tsx?$/.test(f) && !f.includes('.test.')).map((f) => `${dir}/${f}`);

const groups = {
  theme: ['src/styles/tokens.css', 'src/styles/globals.css'],
  utils: ['src/lib/utils.ts'], format: ['src/lib/format.ts'], prefs: ['src/lib/prefs.tsx'],
  i18n: ['src/i18n/index.ts', 'src/i18n/strings.ts'],
  echart: ['src/ui/charts/echarts.ts', 'src/ui/charts/theme.ts', 'src/ui/charts/tooltip.ts', 'src/ui/charts/echart.tsx'],
  'viz-utils': ['src/ui/viz/use-width.ts'],
  'api-kit': [...list('src/kit/api'), 'src/kit/api/simulated/server.ts'],
  'governed-kit': list('src/kit/governed'),
};
const grouped = new Set(Object.values(groups).flat());
for (const dir of ['src/ui/atoms', 'src/ui/molecules', 'src/ui/organisms', 'src/ui/charts', 'src/ui/viz', 'src/ui/templates']) {
  for (const f of list(dir)) if (!grouped.has(f)) groups[path.basename(f).replace(/\.tsx?$/, '')] = [f];
}
const owner = new Map(Object.entries(groups).flatMap(([name, files]) => files.map((f) => [f, name])));

function resolveLocal(from, spec) {
  const base = spec.startsWith('@/') ? path.join(root, 'src', spec.slice(2)) : path.resolve(path.dirname(path.join(root, from)), spec);
  for (const ext of ['', '.ts', '.tsx', '/index.ts']) if (fs.existsSync(base + ext) && fs.statSync(base + ext).isFile()) return rel(base + ext);
  return null;
}

const items = Object.entries(groups).map(([name, files]) => {
  const deps = new Set(); const reg = new Set(name === 'theme' ? [] : ['@platform/theme']);
  for (const f of files) {
    for (const [, spec] of read(f).matchAll(/from ['"]([^'"]+)['"]/g)) {
      if (spec.startsWith('.') || spec.startsWith('@/')) {
        const target = resolveLocal(f, spec);
        const o = target && owner.get(target);
        if (o && o !== name) reg.add(`@platform/${o}`);
      } else {
        const p = spec.startsWith('@') ? spec.split('/').slice(0, 2).join('/') : spec.split('/')[0];
        if (versions[p]) deps.add(`${p}@${versions[p].replace(/^[\^~]/, '')}`);
      }
      if (spec === 'react-i18next' && name !== 'i18n') reg.add('@platform/i18n');
    }
  }
  if (name === 'theme') ['tw-animate-css', '@fontsource-variable/geist', '@fontsource/ibm-plex-sans-arabic'].forEach((p) => deps.add(`${p}@${versions[p].replace(/^[\^~]/, '')}`));
  return {
    name, type: name === 'theme' ? 'registry:style' : 'registry:ui', title: name,
    description: `@platform/web-kit ${name} (${files.map((f) => f.replace('src/', '')).join(', ')})`,
    dependencies: [...deps].sort(), registryDependencies: [...reg].sort(),
    files: files.map((f) => ({ path: f, type: 'registry:file', target: f })),
  };
});

const registry = { $schema: 'https://ui.shadcn.com/schema/registry.json', name: 'platform', homepage: 'https://github.com/aobeidh/platform-foundation/tree/main/web', items };
fs.writeFileSync(path.join(root, 'registry.json'), JSON.stringify(registry, null, 2) + '\n');
console.log(`registry.json: ${items.length} items`);
