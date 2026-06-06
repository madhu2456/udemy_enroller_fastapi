import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';

function getBuildScript() {
  try {
    const packageJson = JSON.parse(readFileSync('./package.json', 'utf8'));
    return typeof packageJson.scripts?.build === 'string'
      ? packageJson.scripts.build
      : '';
  } catch {
    return '';
  }
}

const buildScript = getBuildScript();
const shouldForceWebpack =
  /\bnext\s+build\b/.test(buildScript) &&
  !/\s--(?:webpack|turbopack)(?:\s|$)/.test(buildScript);
const args = shouldForceWebpack ? ['build', '--webpack'] : ['build'];

const result = spawnSync('yarn', args, {
  stdio: 'inherit',
});

if (result.error) {
  console.error(result.error);
  process.exit(1);
}

if (result.signal) {
  console.error(`Build command terminated by ${result.signal}`);
  process.exit(1);
}

process.exit(result.status ?? 1);
